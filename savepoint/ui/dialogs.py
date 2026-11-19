"""各类对话框。"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import config
from ..core.repo import Project


def _buttons(dialog: QDialog, ok_text: str = "确定", cancel_text: str = "取消") -> QHBoxLayout:
    row = QHBoxLayout()
    row.addStretch(1)
    cancel = QPushButton(cancel_text)
    cancel.clicked.connect(dialog.reject)
    ok = QPushButton(ok_text)
    ok.setObjectName("Primary")
    ok.setDefault(True)
    ok.clicked.connect(dialog.accept)
    row.addWidget(cancel)
    row.addWidget(ok)
    return row


class TextPromptDialog(QDialog):
    """单行输入（新建分区、重命名等）。"""

    def __init__(self, parent: QWidget | None, title: str, label: str, default: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        tip = QLabel(label)
        tip.setWordWrap(True)
        layout.addWidget(tip)
        self.edit = QLineEdit(default)
        self.edit.returnPressed.connect(self.accept)
        layout.addWidget(self.edit)
        layout.addLayout(_buttons(self, "确定"))

    def value(self) -> str:
        return self.edit.text().strip()


class EntryEditDialog(QDialog):
    """编辑一条记录，保留原始时间。"""

    def __init__(self, parent: QWidget | None, text: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑记录")
        self.setMinimumWidth(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        self.edit = QPlainTextEdit()
        self.edit.setPlainText(text)
        self.edit.setMinimumHeight(120)
        layout.addWidget(self.edit)
        hint = QLabel("只改内容，时间保持原样。")
        hint.setObjectName("Muted")
        layout.addWidget(hint)
        layout.addLayout(_buttons(self, "保存"))

    def text(self) -> str:
        return self.edit.toPlainText().strip()


def show_open_failure(parent: QWidget | None, path: str, error: Exception) -> None:
    """打开文件夹失败时的提示：说清原因，并给可操作的出口。"""
    from ..core import paths as paths_mod

    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle("打不开文件夹")
    box.setText("没能打开资源管理器。")
    box.setInformativeText(f"{error}\n\n路径：{path}")
    copy_btn = box.addButton("复制路径", QMessageBox.ButtonRole.ActionRole)
    fix_btn = None
    if paths_mod.is_low_integrity():
        fix_btn = box.addButton("复制修复命令", QMessageBox.ButtonRole.ActionRole)
    box.addButton("关闭", QMessageBox.ButtonRole.AcceptRole)
    box.exec()

    clicked = box.clickedButton()
    if clicked is copy_btn:
        from PySide6.QtGui import QGuiApplication

        QGuiApplication.clipboard().setText(path)
    elif fix_btn is not None and clicked is fix_btn:
        from PySide6.QtGui import QGuiApplication

        QGuiApplication.clipboard().setText(paths_mod.integrity_fix_command())


class ProjectDialog(QDialog):
    def __init__(self, parent: QWidget | None = None, project: Project | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("编辑项目" if project else "新建项目")
        self.setMinimumWidth(520)
        self._project = project

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setSpacing(10)

        self.name_edit = QLineEdit(project.name if project else "")
        self.name_edit.setPlaceholderText("比如：爬虫工具集")
        form.addRow("项目名称", self.name_edit)

        self.path_edit = QLineEdit(project.path if project else "")
        self.path_edit.setPlaceholderText(r"比如：C:\Projects\my-app（可留空）")
        path_row = QHBoxLayout()
        path_row.setContentsMargins(0, 0, 0, 0)
        path_row.addWidget(self.path_edit, 1)
        browse = QPushButton("浏览…")
        browse.clicked.connect(self._pick_folder)
        path_row.addWidget(browse)
        form.addRow("项目路径", path_row)

        self.summary_edit = QLineEdit(project.summary if project else "")
        self.summary_edit.setPlaceholderText("30 字内，给未来的自己看")
        self.summary_edit.setMaxLength(80)
        form.addRow("一句话描述", self.summary_edit)

        self.status_combo = QComboBox()
        for key in config.STATUS_ORDER:
            self.status_combo.addItem(config.STATUS_LABELS[key], key)
        if project:
            index = self.status_combo.findData(project.status)
            self.status_combo.setCurrentIndex(max(0, index))
        form.addRow("状态", self.status_combo)

        self.tags_edit = QLineEdit(" ".join(project.tags) if project else "")
        self.tags_edit.setPlaceholderText("用空格或逗号分隔，比如：Python 爬虫 副业")
        form.addRow("标签", self.tags_edit)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(14)
        layout.addLayout(form)
        hint = QLabel("一句话描述和标签以后是最快找回记忆的线索。")
        hint.setObjectName("Muted")
        layout.addWidget(hint)
        layout.addLayout(_buttons(self, "保存"))

    def _pick_folder(self) -> None:
        start = self.path_edit.text().strip() or str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "选择项目文件夹", start)
        if folder:
            self.path_edit.setText(folder.replace("/", "\\"))

    def accept(self) -> None:
        if not self.name_edit.text().strip():
            self.name_edit.setFocus()
            self.name_edit.setPlaceholderText("名称不能为空")
            return
        super().accept()

    def values(self) -> dict:
        raw = self.tags_edit.text().replace("，", " ").replace(",", " ")
        tags = [part for part in raw.split() if part]
        return {
            "name": self.name_edit.text().strip(),
            "path": self.path_edit.text().strip(),
            "summary": self.summary_edit.text().strip(),
            "status": self.status_combo.currentData(),
            "tags": tags,
        }


class CaptionDialog(QDialog):
    """添加截图后补一句说明。"""

    def __init__(self, parent: QWidget | None, pixmap: QPixmap, index: int, total: int) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"给截图加一句说明（{index}/{total}）")
        self.setMinimumWidth(460)

        preview = QLabel()
        preview.setAlignment(Qt.AlignCenter)
        preview.setPixmap(
            pixmap.scaled(420, 260, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )

        self.caption_edit = QLineEdit()
        self.caption_edit.setPlaceholderText("完成了登录页面 / 卡在这个报错上…（可留空）")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        layout.addWidget(preview)
        layout.addWidget(self.caption_edit)
        layout.addLayout(_buttons(self, "保存"))

    def caption(self) -> str:
        return self.caption_edit.text().strip()


class ImageViewer(QDialog):
    """大图查看。"""

    def __init__(self, parent: QWidget | None, image_path: Path, title: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(title or "查看截图")
        self.resize(1000, 720)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.label = QLabel()
        self.label.setAlignment(Qt.AlignCenter)
        self.scroll.setWidget(self.label)

        self._pixmap = QPixmap(str(image_path)) if Path(image_path).is_file() else QPixmap()

        bottom = QHBoxLayout()
        info = QLabel(str(image_path))
        info.setObjectName("Muted")
        info.setTextInteractionFlags(Qt.TextSelectableByMouse)
        bottom.addWidget(info, 1)
        copy_btn = QPushButton("复制路径")
        copy_btn.clicked.connect(lambda: self._copy(str(image_path)))
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.accept)
        bottom.addWidget(copy_btn)
        bottom.addWidget(close_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 10)
        layout.addWidget(self.scroll, 1)
        layout.addLayout(bottom)

        if self._pixmap.isNull():
            self.label.setText("图片文件已丢失")
        else:
            self._apply_scale()

    def _copy(self, text: str) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(text)

    def _apply_scale(self) -> None:
        area = self.scroll.viewport().size()
        scaled = self._pixmap.scaled(area, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.label.setPixmap(scaled)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().resizeEvent(event)
        if not self._pixmap.isNull():
            self._apply_scale()
