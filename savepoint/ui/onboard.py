"""首次启动引导。"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import config


class OnboardDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"欢迎使用{config.APP_NAME}")
        self.setMinimumWidth(600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 22, 26, 18)
        layout.setSpacing(12)

        title = QLabel("三个月后，你还记得当时在做什么吗？")
        title.setStyleSheet("font-size:15pt; font-weight:600;")
        title.setWordWrap(True)
        layout.addWidget(title)

        intro = QLabel(
            "这个工具只做一件事：让你在做项目时顺手记一笔，过几个月翻出来还能看懂。"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        points = QLabel(
            "·  中间栏底下打字回车，就是一条带时间的记录，只追加不改写\n"
            "·  截图拖进右侧，或者点一下虚线框按 Ctrl+V，都能存进时间线\n"
            "·  Ctrl+Alt+N 随时唤起快速记录，不用先找窗口\n"
            "·  数据全在本地，从不上传"
        )
        points.setObjectName("Muted")
        layout.addWidget(points)

        layout.addSpacing(6)
        dir_label = QLabel("数据放在哪里")
        dir_label.setObjectName("SectionTitle")
        layout.addWidget(dir_label)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        self.dir_edit = QLineEdit(str(config.default_data_dir()))
        row.addWidget(self.dir_edit, 1)
        browse = QPushButton("更改…")
        browse.clicked.connect(self._pick_dir)
        row.addWidget(browse)
        layout.addLayout(row)

        dir_hint = QLabel(
            "默认放在程序旁边的 savepoint-data 文件夹。可以挪到别的盘，以后在设置里也能改。"
        )
        dir_hint.setObjectName("Muted")
        dir_hint.setWordWrap(True)
        layout.addWidget(dir_hint)

        layout.addSpacing(6)
        note_hint = QLabel(
            "侧栏「笔记」下按目录存灵感、Prompt、配置片段，点开直接写，自动保存。"
        )
        note_hint.setObjectName("Muted")
        note_hint.setWordWrap(True)
        layout.addWidget(note_hint)

        layout.addSpacing(8)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        start = QPushButton("开始使用")
        start.setObjectName("Primary")
        start.setDefault(True)
        start.clicked.connect(self.accept)
        buttons.addWidget(start)
        layout.addLayout(buttons)

    def _pick_dir(self) -> None:
        start = self.dir_edit.text().strip() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "选择数据目录", start)
        if folder:
            self.dir_edit.setText(folder.replace("/", "\\"))

    def apply(self) -> None:
        chosen = self.dir_edit.text().strip()
        default = str(config.default_data_dir())
        config.save_settings(
            {
                "data_dir": "" if Path(chosen) == Path(default) else chosen,
                "onboarded": "1",
            }
        )
        config.reload_paths()

    def reject(self) -> None:  # 直接关掉也算看过，不再反复弹
        config.save_settings({"onboarded": "1"})
        super().reject()