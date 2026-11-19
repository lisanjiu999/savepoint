"""快速记录小窗：全局热键唤起，回车即存。"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import config


class QuickCaptureDialog(QDialog):
    saved = Signal(str, str)  # project_id, body

    def __init__(self, parent: QWidget | None, repo) -> None:
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle("快速记录")
        self.setWindowFlag(Qt.WindowStaysOnTopHint, True)
        self.setModal(False)
        self.resize(520, 170)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)

        head = QHBoxLayout()
        title = QLabel("记一笔")
        title.setObjectName("CardTitle")
        head.addWidget(title)
        head.addStretch(1)
        self.project_combo = QComboBox()
        self.project_combo.setMinimumWidth(180)
        head.addWidget(self.project_combo)
        layout.addLayout(head)

        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText("今天做了什么 / 卡在哪 / 下一步…（回车保存，Esc 取消）")
        self.text_edit.returnPressed.connect(self._save)
        layout.addWidget(self.text_edit)

        foot = QHBoxLayout()
        hint = QLabel("只追加不改写，记完就能关")
        hint.setObjectName("Muted")
        foot.addWidget(hint)
        foot.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.close)
        save = QPushButton("记下")
        save.setObjectName("Primary")
        save.clicked.connect(self._save)
        foot.addWidget(cancel)
        foot.addWidget(save)
        layout.addLayout(foot)

    # ---------------- 数据 ----------------

    def reload_projects(self) -> None:
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        projects = [p for p in self.repo.list_projects() if p.status != "archived"]
        if not projects:
            projects = self.repo.list_projects()
        for project in projects:
            self.project_combo.addItem(project.name, project.id)
        self.project_combo.blockSignals(False)

        last = config.get_setting("last_project_id")
        if last:
            index = self.project_combo.findData(last)
            if index >= 0:
                self.project_combo.setCurrentIndex(index)

    def popup(self) -> None:
        self.reload_projects()
        self.text_edit.clear()
        self.show()
        self.raise_()
        self.activateWindow()
        self.text_edit.setFocus(Qt.OtherFocusReason)

    def _save(self) -> None:
        text = self.text_edit.text().strip()
        project_id = self.project_combo.currentData()
        if not text or not project_id:
            return
        self.repo.add_entry(project_id, text)
        config.set_setting("last_project_id", project_id)
        self.saved.emit(project_id, text)
        self.text_edit.clear()
        self.close()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)