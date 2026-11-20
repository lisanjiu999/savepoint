"""真实窗口运行检查：启动、渲染、布局度量，然后自动退出。

用法：.venv\\Scripts\\python.exe -m savepoint.tests_runtime
"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import os
import shutil
import sys

from savepoint.console import ensure_utf8_console
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / ".runtime-data"
if DATA.exists():
    shutil.rmtree(DATA, ignore_errors=True)
DATA.mkdir(parents=True, exist_ok=True)
os.environ["SAVEPOINT_DATA_DIR"] = str(DATA)

# 故意写一个标题栏跑到屏幕外的旧坐标，验证启动时会被拉回来
(DATA / "ui_state.json").write_text(
    json.dumps({"geometry": [264, -50, 1180, 760], "selected_id": None}),
    encoding="utf-8",
)

problems: list[str] = []
_APP = None
_WINDOW = None


def report(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'OK  ' if ok else 'BAD '} {name} {detail}")
    if not ok:
        problems.append(f"{name} {detail}")


def main() -> int:
    global _APP, _WINDOW
    ensure_utf8_console()
    from PySide6.QtCore import QTimer
    from PySide6.QtGui import QFontInfo, QGuiApplication
    from PySide6.QtWidgets import QApplication, QLabel, QScrollArea

    from savepoint import config
    from savepoint.core.db import open_database
    from savepoint.core.repo import Repo
    from savepoint.core.storage import ShotStore
    from savepoint.demo_data import seed
    from savepoint.ui.main_window import MainWindow
    from savepoint.ui.style import QSS, light_palette

    config.ensure_dirs()
    conn = open_database(config.DB_PATH)
    repo = Repo(conn)
    store = ShotStore()
    ids = seed(repo, store)

    app = QApplication.instance() or QApplication(sys.argv)
    _APP = app
    app.setStyle("Fusion")
    app.setPalette(light_palette())
    app.setStyleSheet(QSS)

    print(f"[平台] {QGuiApplication.platformName()}  配色方案={QGuiApplication.styleHints().colorScheme()}")
    info = QFontInfo(app.font())
    report("字体可用", bool(info.family()) and info.pointSizeF() > 0,
           f"{info.family()} {info.pointSizeF()}pt")

    print("[配色]")
    from PySide6.QtWidgets import QMessageBox

    box = QMessageBox()
    box.setWindowTitle("提示")
    box.setText("这是一条测试提示，文字必须看得清。")
    box.setIcon(QMessageBox.Information)
    box.show()
    app.processEvents()
    box_image = box.grab().toImage()
    top_pixel = box_image.pixelColor(box_image.width() // 2, 4)
    background = top_pixel.red() * 0.299 + top_pixel.green() * 0.587 + top_pixel.blue() * 0.114
    darkest = 255.0
    has_dark = False
    for y in range(0, box_image.height(), 2):
        for x in range(0, box_image.width(), 2):
            pixel = box_image.pixelColor(x, y)
            lum = pixel.red() * 0.299 + pixel.green() * 0.587 + pixel.blue() * 0.114
            darkest = min(darkest, lum)
            if lum < 110:
                has_dark = True
    report("提示框底色够亮", background > 200, f"{top_pixel.name()} 亮度={background:.0f}")
    report("提示框文字够深", has_dark, f"最暗={darkest:.0f}")
    report("文字/底色对比度足够",
           background > 200 and darkest < 110,
           f"估算 {background / max(darkest, 1):.1f}:1")
    box.close()
    box.deleteLater()
    app.processEvents()

    window = MainWindow(repo, store)
    _WINDOW = window
    window.resize(1240, 820)
    window.show()
    app.processEvents()

    print("[布局]")
    detail = window.detail
    sidebar = window.views_list.parentWidget()
    report("窗口可见", window.isVisible())
    report(
        "窗口在屏幕内",
        window.y() >= 0 and window.x() >= 0,
        f"位置=({window.x()}, {window.y()})",
    )
    report("侧栏宽度", 190 <= sidebar.width() <= 200, str(sidebar.width()))
    report("项目列表有卡片", window.project_list.count() == 5, str(window.project_list.count()))
    report("条目渲染", detail.entries_layout.count() == 3, str(detail.entries_layout.count()))
    report("截图渲染", detail.shots_layout.count() == 3, str(detail.shots_layout.count()))
    report("详情宽度合理", detail.width() > 500, str(detail.width()))

    card = detail.shots_layout.itemAt(0).widget()
    report("截图卡片不越界", card.width() <= detail.width(), f"{card.width()} <= {detail.width()}")

    first_card = window._cards[ids[0]]  # noqa: SLF001
    report("列表卡片有摘要", bool(first_card._summary_label.text()))  # noqa: SLF001

    print("[细节]")
    scroll = detail.findChild(QScrollArea)
    if scroll is not None:
        content = scroll.widget()
        report("详情无横向滚动", scroll.horizontalScrollBar().maximum() == 0,
               f"max={scroll.horizontalScrollBar().maximum()}")
        report("内容宽度贴合视口", abs(content.width() - scroll.viewport().width()) <= 2,
               f"{content.width()} vs {scroll.viewport().width()}")
    clipped = []
    for label in detail.findChildren(QLabel):
        text = label.text()
        if not text or label.wordWrap() or "\n" in text:
            continue
        need = label.fontMetrics().horizontalAdvance(text)
        if need > label.width() + 2:
            clipped.append(f"{text[:10]}(需{need}/有{label.width()})")
    report("详情文字未被裁切", not clipped, "; ".join(clipped[:4]))
    report("状态标签可见", bool(detail.status_pill.text()), detail.status_pill.text())

    print("[交互]")
    from PySide6.QtGui import QColor, QImage
    from PySide6.QtWidgets import QLineEdit

    import savepoint.ui.project_detail as detail_module

    class _StubCaptionDialog:  # 避免模态弹窗阻塞
        def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
            self.caption_edit = QLineEdit()

        def exec(self) -> int:
            return 0

    detail_module.CaptionDialog = _StubCaptionDialog

    sample = DATA / "extra.png"
    QImage(320, 200, QImage.Format_RGB32).save(str(sample))
    before = len(repo.list_screenshots(ids[0]))
    detail._add_files([str(sample)])  # noqa: SLF001
    report("拖入图片入库", len(repo.list_screenshots(ids[0])) == before + 1,
           f"{before} -> {len(repo.list_screenshots(ids[0]))}")

    clipboard_image = QImage(240, 140, QImage.Format_RGB32)
    clipboard_image.fill(QColor("#3366cc"))
    QApplication.clipboard().setImage(clipboard_image)
    before = len(repo.list_screenshots(ids[0]))
    detail._paste_image()  # noqa: SLF001
    report("粘贴图片入库", len(repo.list_screenshots(ids[0])) == before + 1,
           f"{before} -> {len(repo.list_screenshots(ids[0]))}")

    before = len(repo.list_screenshots(ids[0]))
    detail._paste_image()  # noqa: SLF001
    report("同一张图不重复入库", len(repo.list_screenshots(ids[0])) == before,
           f"仍为 {before}")

    from PySide6.QtCore import Qt as QtCore_Qt

    note = repo.create_note(folder="提示词", title="常用 Prompt", content="你是一个助手")
    window.refresh_all()
    window.open_notes()
    notes = window.notes_window
    report("分区树有分区", notes.tree.topLevelItemCount() >= 1,
           str(notes.tree.topLevelItemCount()))
    from PySide6.QtCore import Qt as _Qt

    report(
        "笔记窗口支持右键菜单",
        notes.tree.contextMenuPolicy() == _Qt.ContextMenuPolicy.CustomContextMenu,
    )
    report(
        "侧栏笔记树支持右键菜单",
        window.notes_tree.contextMenuPolicy() == _Qt.ContextMenuPolicy.CustomContextMenu,
    )
    report("分区下挂文档", notes.tree.topLevelItem(0).childCount() >= 1,
           str(notes.tree.topLevelItem(0).childCount()))
    # 选中"常用 Prompt"这条
    target_item = None
    for index in range(notes.tree.topLevelItemCount()):
        node = notes.tree.topLevelItem(index)
        for child_index in range(node.childCount()):
            data = node.child(child_index).data(0, QtCore_Qt.UserRole)
            if data and data[1] == note.id:
                target_item = node.child(child_index)
    if target_item is not None:
        notes._on_item_clicked(target_item, 0)  # noqa: SLF001
    app.processEvents()
    notes._copy()  # noqa: SLF001
    report("笔记可复制", QApplication.clipboard().text() == "你是一个助手",
           QApplication.clipboard().text()[:20])

    notes.title_edit.setText("改过的标题")
    notes.content_edit.setPlainText("改过的正文")
    notes._save_current()  # noqa: SLF001
    saved = repo.get_note(note.id)
    report("就地编辑自动保存", saved.title == "改过的标题" and saved.content == "改过的正文",
           saved.title)

    created_before = repo.count_notes()
    notes._create_note()  # noqa: SLF001
    report("新建笔记", repo.count_notes() == created_before + 1,
           f"{created_before} -> {repo.count_notes()}")
    notes.close()

    window.search_edit.setText("代理池")
    window.refresh_projects()
    report("搜索筛选生效", window.project_list.count() == 1, str(window.project_list.count()))
    window.search_edit.clear()
    window.refresh_projects()

    print("[区域截图]")
    from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
    from PySide6.QtGui import QMouseEvent
    from PySide6.QtWidgets import QPushButton

    from savepoint.ui.capture import ScreenCaptureOverlay, grab_virtual_desktop

    buttons = [b.text() for b in detail.drop_zone.findChildren(QPushButton)]
    report("截图按钮存在", any("截图" in text for text in buttons), str(buttons))

    desktop = grab_virtual_desktop()
    report("能抓取桌面", not desktop.isNull(), f"{desktop.width()}x{desktop.height()}")

    overlay = ScreenCaptureOverlay()
    captured: dict = {}
    overlay.captured.connect(lambda pix: captured.setdefault("pix", pix))
    overlay.show()
    app.processEvents()

    def send(kind, point) -> None:  # noqa: ANN001
        position = QPointF(point)
        event = QMouseEvent(
            kind, position, position, Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier,
        )
        QApplication.sendEvent(overlay, event)

    send(QEvent.Type.MouseButtonPress, QPoint(80, 80))
    send(QEvent.Type.MouseMove, QPoint(360, 260))
    send(QEvent.Type.MouseButtonRelease, QPoint(360, 260))
    app.processEvents()

    pixmap = captured.get("pix")
    report("框选后产出图像", pixmap is not None and not pixmap.isNull())
    if pixmap is not None:
        ratio = pixmap.devicePixelRatio() or 1.0
        report(
            "裁剪尺寸正确",
            abs(pixmap.width() - int(280 * ratio)) <= 2,
            f"{pixmap.width()}x{pixmap.height()}",
        )
        before = len(repo.list_screenshots(ids[0]))
        detail._on_captured(pixmap)  # noqa: SLF001
        app.processEvents()
        after = len(repo.list_screenshots(ids[0]))
        report("截图直接入库", after == before + 1, f"{before} -> {after}")

    print("[文档导入]")
    from savepoint.core.documents import DocStore, extract_text
    from savepoint.testdata_docs import build_docx, build_pdf

    docs_src = DATA / "drop"
    docs_src.mkdir(parents=True, exist_ok=True)
    build_docx(docs_src / "接口设计.docx")
    build_pdf(docs_src / "使用手册.pdf")

    doc_store = DocStore(DATA / "documents")
    for name in ("接口设计.docx", "使用手册.pdf"):
        src = docs_src / name
        rel, size, digest = doc_store.save(src)
        text, _warn = extract_text(src)
        repo.add_document(
            rel_path=rel, orig_name=name, ext=src.suffix,
            size=size, sha256=digest, text_content=text, folder="工作",
        )
    report("文档存储目录存在", doc_store.doc_dir.is_dir())
    report("文档入库", repo.count_documents() == 2, str(repo.count_documents()))

    window.doc_store = doc_store
    window.open_documents()
    app.processEvents()
    library = window.documents_window
    report("文档库窗口打开", library is not None and library.isVisible())
    report("文档库分区树", library.folder_tree.topLevelItemCount() == 2,
           str(library.folder_tree.topLevelItemCount()))
    report("文档库列出文档", library.docs_layout.count() == 3,
           str(library.docs_layout.count()))

    library.search_edit.setText("手册")
    app.processEvents()
    report("文档库搜索", library.docs_layout.count() == 2,
           str(library.docs_layout.count()))
    library.search_edit.clear()
    app.processEvents()

    from savepoint.ui.document_dialog import DocumentViewer

    doc = repo.list_documents()[0]
    viewer = DocumentViewer(window, doc, doc_store.abs_path(doc.rel_path))
    viewer.show()
    app.processEvents()
    report("文档查看器可打开", viewer.isVisible())
    viewer.close()
    library.close()

    print("[状态切换]")
    detail.status_combo.setCurrentIndex(detail.status_combo.findData("paused"))
    app.processEvents()
    reloaded = repo.get_project(ids[0])
    report("用下拉改状态", reloaded.status == "paused", reloaded.status)
    detail.status_combo.setCurrentIndex(detail.status_combo.findData("active"))
    app.processEvents()

    print("[新功能]")
    window.open_search()
    app.processEvents()
    report("全局搜索窗口", window.search_dialog is not None and window.search_dialog.isVisible())
    window.search_dialog.input.setText("代理")
    window.search_dialog._search()  # noqa: SLF001
    report("搜索有结果", window.search_dialog.list_widget.count() >= 1,
           str(window.search_dialog.list_widget.count()))
    window.search_dialog.close()

    window.open_activity()
    app.processEvents()
    report("活动流窗口", window.activity_window is not None)
    window.activity_window.refresh()
    report("活动流有内容", window.activity_window.list_widget.count() >= 2,
           str(window.activity_window.list_widget.count()))
    window.activity_window.close()

    window.open_trash()
    app.processEvents()
    report("回收站窗口", window.trash_dialog is not None and window.trash_dialog.isVisible())
    window.trash_dialog.close()

    report("托盘图标", window.tray is not None and window.tray.isVisible())
    report(
        "全局热键已注册",
        window.hotkey is not None and window.hotkey.is_registered(),
        config.get_setting("hotkey"),
    )

    window.quick_capture()
    app.processEvents()
    dialog = window.capture_dialog
    report("快速记录窗口弹出", dialog is not None and dialog.isVisible())
    if dialog is not None:
        index = dialog.project_combo.findData(ids[0])
        dialog.project_combo.setCurrentIndex(max(0, index))
        before = len(repo.list_entries(ids[0]))
        dialog.text_edit.setText("热键记的一条")
        dialog._save()  # noqa: SLF001
        app.processEvents()
        after = len(repo.list_entries(ids[0]))
        report("快速记录写入", after == before + 1, f"{before} -> {after}")
        report("记录后自动关闭", not dialog.isVisible())

    from savepoint.ui.onboard import OnboardDialog
    from savepoint.ui.settings_dialog import SettingsDialog

    settings_dialog = SettingsDialog(window)
    report("设置窗口可构建", settings_dialog.backup_keep.value() >= 0)
    settings_dialog.close()

    onboard = OnboardDialog(window)
    report("引导窗口可构建", bool(onboard.dir_edit.text()))
    onboard.close()

    shot = window.grab()
    image = shot.toImage()
    colors = set()
    ink = 0
    total = 0
    for y in range(0, image.height(), 3):
        for x in range(0, image.width(), 3):
            pixel = image.pixelColor(x, y)
            colors.add((pixel.red(), pixel.green(), pixel.blue()))
            if min(pixel.red(), pixel.green(), pixel.blue()) < 180:
                ink += 1
            total += 1
    report("渲染出多种颜色", len(colors) > 80, f"{len(colors)} 色")
    report(
        "有文字/图形像素",
        ink / max(total, 1) > 0.010,
        f"{ink / max(total, 1) * 100:.1f}%",
    )

    (BASE / ".preview").mkdir(exist_ok=True)
    window.grab().save(str(BASE / ".preview" / "runtime.png"))

    errors: list[str] = []
    original_hook = sys.excepthook
    sys.excepthook = lambda t, v, tb: errors.append(str(v))  # noqa: ARG005

    QTimer.singleShot(1200, app.quit)
    app.exec()
    sys.excepthook = original_hook
    report("运行期无异常", not errors, "; ".join(errors))

    conn.close()
    print()
    if problems:
        print(f"发现 {len(problems)} 个问题")
        return 1
    print("界面检查通过")
    return 0


if __name__ == "__main__":
    code = main()
    from savepoint.shutdown import hard_exit

    hard_exit(code)