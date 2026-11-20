"""生成界面预览图（离屏渲染）。

用法：.venv\\Scripts\\python.exe -m savepoint.tests_preview
产物：.preview/*.png
"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import shutil
import sys

from savepoint.console import ensure_utf8_console
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / ".preview-data"
if DATA.exists():
    shutil.rmtree(DATA, ignore_errors=True)
DATA.mkdir(parents=True, exist_ok=True)
os.environ["SAVEPOINT_DATA_DIR"] = str(DATA)
OUT = BASE / ".preview"
OUT.mkdir(exist_ok=True)

_APP = None
_WINDOW = None


def main() -> int:
    global _APP, _WINDOW
    ensure_utf8_console()
    from PySide6.QtWidgets import QApplication

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

    repo.create_note(
        folder="密钥与账号", title="OpenAI Key", content="sk-demo-1234567890", project_id=ids[0]
    )
    repo.create_note(folder="提示词", title="代码 review 模板", content="请按以下维度审查…")
    repo.create_note(folder="提示词", title="周报模板", content="本周完成：…")
    repo.create_note(folder="配置片段", title="nginx 反代", content="server {\n  listen 80;\n}")

    app = QApplication.instance() or QApplication(sys.argv)
    _APP = app
    app.setStyle("Fusion")
    app.setPalette(light_palette())
    app.setStyleSheet(QSS)

    window = MainWindow(repo, store)
    _WINDOW = window
    window.resize(1240, 820)
    window.show()
    app.processEvents()
    window.refresh_all()
    window.detail.bind_project(ids[0])
    app.processEvents()
    path = OUT / "main.png"
    window.grab().save(str(path))
    print("saved", path)

    window.open_notes()
    window.notes_window.resize(980, 660)
    window.notes_window.show()
    app.processEvents()
    notes_path = OUT / "notes.png"
    window.notes_window.grab().save(str(notes_path))
    print("saved", notes_path)

    conn.close()
    return 0


if __name__ == "__main__":
    code = main()
    from savepoint.shutdown import hard_exit

    hard_exit(code)