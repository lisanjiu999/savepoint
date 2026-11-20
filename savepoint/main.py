"""入口：单实例 + 首次引导 + 主窗口。

退出时做确定性收尾再直接结束进程：PySide6 在解释器 finalize 阶段销毁
Qt 对象的顺序不确定，曾观察到偶发访问违例（0xC0000005）。
"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

import ctypes
import logging
import os
import sys
import traceback

from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from . import config
from .console import ensure_utf8_console
from .core.db import open_database
from .core.documents import DocStore
from .core.repo import Repo
from .core.single_instance import SingleInstance
from .core.storage import ShotStore
from .shutdown import hard_exit
from .ui.onboard import OnboardDialog
from .ui.style import QSS, light_palette


def _set_app_user_model_id() -> None:
    """让任务栏把窗口归到自己图标下，而不是 python 那一组。"""
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(config.APP_ID)
    except Exception:  # noqa: BLE001 - 非 Windows 或调用失败都无妨
        pass


def _setup_logging() -> None:
    config.ensure_dirs()
    handlers: list[logging.Handler] = [
        logging.FileHandler(config.LOG_PATH, encoding="utf-8")
    ]
    # pythonw 下没有控制台，sys.stderr 为 None
    if sys.stderr is not None:
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
    )


def _install_excepthook() -> None:
    def hook(exc_type, exc_value, exc_tb) -> None:
        text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        logging.getLogger("savepoint").error("未处理异常\n%s", text)
        app = QApplication.instance()
        if app is not None:
            QMessageBox.critical(
                None,
                "出错了",
                f"程序遇到一个错误，详情已写入日志：\n{config.LOG_PATH}\n\n{exc_value}",
            )

    sys.excepthook = hook


def _teardown(app: QApplication, window, conn) -> None:  # noqa: ANN001
    """在进程退出前，按可控顺序释放 Qt 资源。"""
    try:
        window.prepare_quit()
        detail = getattr(window, "detail", None)
        if detail is not None:
            detail.flush()
        window.close()
        window.deleteLater()
    except Exception:  # noqa: BLE001 - 收尾阶段不再抛错
        logging.getLogger("savepoint").exception("关闭窗口时出错")
    try:
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
    except Exception:  # noqa: BLE001
        pass
    try:
        conn.close()
    except Exception:  # noqa: BLE001
        pass


_APP: QApplication | None = None
_WINDOW: object | None = None
_INSTANCE: SingleInstance | None = None


def _create_window(repo, store, doc_store):  # noqa: ANN001, ANN202
    """原生控件界面。"""
    from .ui.main_window import MainWindow

    return MainWindow(repo, store, doc_store)


def main() -> int:
    global _APP, _WINDOW, _INSTANCE

    ensure_utf8_console()
    _set_app_user_model_id()

    app = QApplication(sys.argv)
    _APP = app
    # 系统深色模式下 Qt 会给深色底，配合写死的深色文字会看不清，
    # 所以固定浅色外观。
    app.setStyle("Fusion")
    app.setPalette(light_palette())
    app.setApplicationName(config.APP_NAME)
    app.setApplicationDisplayName(config.APP_NAME)
    app.setStyleSheet(QSS)
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setQuitOnLastWindowClosed(False)

    icon = QIcon(str(config.asset("app.ico")))
    if icon.isNull():
        icon = QIcon(str(config.asset("app-256.png")))
    if not icon.isNull():
        app.setWindowIcon(icon)

    if config.is_first_run():
        onboard = OnboardDialog()
        if onboard.exec():
            onboard.apply()
        else:
            config.save_settings({"onboarded": "1"})
        config.reload_paths()

    _setup_logging()
    _install_excepthook()

    # 单实例：已有实例在跑就唤起它，然后自己安静退出
    instance = SingleInstance(str(config.DATA_DIR))
    _INSTANCE = instance
    if instance.notify_existing():
        return 0
    if not instance.listen():
        logging.getLogger("savepoint").warning("单实例保护不可用，继续启动")

    conn = open_database(config.DB_PATH)
    repo = Repo(conn)
    store = ShotStore()
    doc_store = DocStore()

    # 清掉回收站里超过 30 天的内容（连同截图与文档文件）
    try:
        stale = repo.purge_expired_trash(30)
        for kind, rel in stale:
            if kind == "document":
                doc_store.remove([rel])
            else:
                store.remove_files([rel])
    except Exception:  # noqa: BLE001 - 清理失败不该挡住启动
        logging.getLogger("savepoint").exception("清理回收站失败")

    window = _create_window(repo, store, doc_store)
    _WINDOW = window
    instance.activated.connect(window.show_window)
    if not icon.isNull():
        window.setWindowIcon(icon)
    window.show()
    window.start_background_backup()

    auto_quit = os.environ.get("SAVEPOINT_AUTO_QUIT_MS", "").strip()
    if auto_quit.isdigit():
        QTimer.singleShot(int(auto_quit), app.quit)

    exit_code = app.exec()
    _teardown(app, window, conn)
    return exit_code


def run() -> None:
    """真实入口：跑完 main() 后统一收尾再结束进程。"""
    code = 1
    try:
        code = main()
    except SystemExit as exc:
        code = int(exc.code or 0)
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        code = 1
    finally:
        try:
            logging.shutdown()
        except Exception:  # noqa: BLE001
            pass
    hard_exit(code)


if __name__ == "__main__":
    run()