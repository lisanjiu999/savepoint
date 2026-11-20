"""文档相关对话框：入库确认、内容查看。"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core import paths
from ..core.documents import DocumentError

KIND_COLORS = {
    "PDF": "#e05c5c",
    "Word": "#4a7fd4",
    "Excel": "#3f9e6a",
    "PPT": "#d4763a",
    "文本": "#8a8f99",
    "Markdown": "#8a8f99",
    "代码": "#9a7bd4",
}


def kind_color(kind: str) -> str:
    return KIND_COLORS.get(kind, "#8a8f99")


class DocumentImportDialog(QDialog):
    """拖进文档后询问：存进项目，还是只读取？"""

    KEEP = "keep"
    READ_ONLY = "read"

    def __init__(
        self,
        parent: QWidget | None,
        *,
        name: str,
        kind: str,
        size: int,
        text: str,
        warning: str,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("导入文档")
        self.setMinimumWidth(620)
        self._choice = self.READ_ONLY

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        title = QLabel(name)
        title.setStyleSheet("font-size:13pt; font-weight:600;")
        title.setWordWrap(True)
        layout.addWidget(title)

        meta = QLabel(
            f"{kind} · {paths.human_size(size)} · "
            + (f"提取到 {len(text)} 字" if text else "未提取到文本")
        )
        meta.setObjectName("Muted")
        layout.addWidget(meta)

        if warning:
            warn = QLabel(warning)
            warn.setObjectName("Muted")
            warn.setWordWrap(True)
            warn.setStyleSheet("color:#d97706;")
            layout.addWidget(warn)

        question = QLabel("要把这份文件保存到当前项目里吗？")
        layout.addWidget(question)

        hint = QLabel(
            "保存后文件会复制进程序的数据目录，桌面上的原件可以删掉，"
            "以后在这里直接看内容。"
        )
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        if text:
            preview = QPlainTextEdit()
            preview.setReadOnly(True)
            preview.setFont(QFont("Microsoft YaHei UI", 9))
            preview.setPlainText(text[:1200] + ("\n…" if len(text) > 1200 else ""))
            preview.setMinimumHeight(200)
            layout.addWidget(preview, 1)
        else:
            layout.addStretch(1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        read_btn = QPushButton("只看不存")
        read_btn.setToolTip("这次只是读一下内容，不留副本")
        read_btn.clicked.connect(self._choose_read)
        keep_btn = QPushButton("保存到项目")
        keep_btn.setObjectName("Primary")
        keep_btn.setDefault(True)
        keep_btn.clicked.connect(self._choose_keep)
        buttons.addWidget(cancel)
        buttons.addWidget(read_btn)
        buttons.addWidget(keep_btn)
        layout.addLayout(buttons)

    def _choose_keep(self) -> None:
        self._choice = self.KEEP
        super().accept()

    def _choose_read(self) -> None:
        self._choice = self.READ_ONLY
        super().accept()

    def choice(self) -> str:
        return self._choice


class DocumentViewer(QDialog):
    """查看已入库文档的提取内容，并可打开原文件。"""

    def __init__(self, parent: QWidget | None, doc, file_path: Path) -> None:
        super().__init__(parent)
        self.setWindowTitle(doc.orig_name or "文档")
        self.resize(820, 640)
        self.setModal(False)
        self._path = file_path

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)

        title = QLabel(doc.orig_name or "文档")
        title.setStyleSheet("font-size:13pt; font-weight:600;")
        title.setWordWrap(True)
        layout.addWidget(title)

        meta = QLabel(
            f"{paths.human_size(doc.size)} · 入库于 "
            f"{paths.human_time(doc.created_at, with_year=True)}"
        )
        meta.setObjectName("Muted")
        layout.addWidget(meta)

        if doc.text_content:
            body = QPlainTextEdit()
            body.setReadOnly(True)
            body.setFont(QFont("Microsoft YaHei UI", 9))
            body.setPlainText(doc.text_content)
            layout.addWidget(body, 1)
            self._body = body
        else:
            empty = QLabel("这份文件没有可显示的文字内容。可以点下面的按钮用系统默认程序打开原件。")
            empty.setObjectName("Muted")
            empty.setWordWrap(True)
            layout.addWidget(empty, 1)
            self._body = None

        actions = QHBoxLayout()
        actions.addStretch(1)
        open_btn = QPushButton("打开原文件")
        open_btn.clicked.connect(self._open_file)
        copy_btn = QPushButton("复制文本")
        copy_btn.setEnabled(bool(doc.text_content))
        copy_btn.clicked.connect(self._copy)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        actions.addWidget(open_btn)
        actions.addWidget(copy_btn)
        actions.addWidget(close_btn)
        layout.addLayout(actions)

    def _open_file(self) -> None:
        if not self._path.is_file():
            QMessageBox.warning(self, "文件不见了", f"找不到：\n{self._path}")
            return
        try:
            paths.open_in_explorer(self._path.parent)
        except OSError as exc:
            QMessageBox.warning(self, "打不开", str(exc))

    def _copy(self) -> None:
        if self._body is None:
            return
        QGuiApplication.clipboard().setText(self._body.toPlainText())


def notify_import_failed(parent: QWidget | None, name: str, error: Exception) -> None:
    QMessageBox.warning(
        parent,
        "没能导入",
        f"{name}\n\n{error}",
    )


__all__ = [
    "DocumentError",
    "DocumentImportDialog",
    "DocumentViewer",
    "kind_color",
    "notify_import_failed",
    "Qt",
]