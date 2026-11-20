"""截图时间线组件：缩略图卡片 + 拖拽区。"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ..core import paths
from ..core.repo import Screenshot


class ClickableLabel(QLabel):
    clicked = Signal()

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


class ScreenshotCard(QFrame):
    """一条记录：左边缩略图，右边时间 + 可就地编辑的说明。"""

    opened = Signal(str)
    caption_changed = Signal(str, str)
    removed = Signal(str)

    def __init__(
        self,
        shot: Screenshot,
        thumb_path: Path,
        shot_path: Path,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("ShotCard")
        self._shot = shot

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(14)

        thumb = ClickableLabel()
        thumb.setFixedSize(236, 148)
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setStyleSheet("background:#f2f4f8; border-radius:6px;")
        pixmap = QPixmap(str(thumb_path)) if thumb_path and thumb_path.is_file() else QPixmap()
        if pixmap.isNull() and shot_path.is_file():
            pixmap = QPixmap(str(shot_path))
        if pixmap.isNull():
            thumb.setText("图片丢失")
            thumb.setStyleSheet(
                "background:#f2f4f8; border-radius:6px; color:#9ca3af; font-size:9pt;"
            )
        else:
            thumb.setPixmap(pixmap.scaled(236, 148, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        thumb.clicked.connect(lambda: self.opened.emit(self._shot.id))
        thumb.setToolTip("点击查看大图")
        layout.addWidget(thumb, 0, Qt.AlignTop)

        right = QVBoxLayout()
        right.setSpacing(6)

        stamp = QLabel(paths.human_time(shot.taken_at, with_year=True))
        stamp.setObjectName("Muted")
        stamp.setToolTip(shot.taken_at)
        right.addWidget(stamp)

        self.caption_edit = QLineEdit(shot.caption)
        self.caption_edit.setPlaceholderText("在这里写一句说明…")
        self.caption_edit.setStyleSheet(
            "QLineEdit { border: none; background: transparent; padding: 2px 0;"
            " font-size: 10pt; }"
            "QLineEdit:focus { border-bottom: 1px solid #2f6feb; }"
        )
        self.caption_edit.editingFinished.connect(self._emit_caption)
        right.addWidget(self.caption_edit)

        right.addStretch(1)

        actions = QHBoxLayout()
        actions.setSpacing(2)
        delete_btn = QPushButton("删除")
        delete_btn.setObjectName("Link")
        delete_btn.setStyleSheet("color:#c0392b; font-size:9pt;")
        delete_btn.clicked.connect(lambda: self.removed.emit(self._shot.id))
        actions.addWidget(delete_btn)
        actions.addStretch(1)
        right.addLayout(actions)

        layout.addLayout(right, 1)

    def _emit_caption(self) -> None:
        text = self.caption_edit.text().strip()
        if text != self._shot.caption:
            self._shot.caption = text
            self.caption_changed.emit(self._shot.id, text)


class DropZone(QFrame):
    """拖入图片 / 区域截图 / 聚焦后 Ctrl+V 粘贴。"""

    files_dropped = Signal(list)
    paste_requested = Signal()
    capture_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumHeight(62)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(8)
        hint = QLabel("拖文件到这里：图片进时间线，文档会读出内容再问你要不要保存")
        hint.setWordWrap(True)
        layout.addWidget(hint)
        layout.addStretch(1)

        capture_btn = QPushButton("截图")
        capture_btn.setToolTip("框选屏幕区域，松手自动保存")
        capture_btn.clicked.connect(self.capture_requested.emit)
        layout.addWidget(capture_btn)

        paste_btn = QPushButton("粘贴截图")
        paste_btn.clicked.connect(self.paste_requested.emit)
        layout.addWidget(paste_btn)

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setObjectName("DropZoneActive")
            self.setStyleSheet("")
            self.style().unpolish(self)
            self.style().polish(self)
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self.setObjectName("DropZone")
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self.setObjectName("DropZone")
        self.style().unpolish(self)
        self.style().polish(self)
        files = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.isLocalFile() and url.toLocalFile()
        ]
        if files:
            self.files_dropped.emit(files)
            event.acceptProposedAction()
            return
        event.ignore()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.matches(QKeySequence.StandardKey.Paste):
            self.paste_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self.setFocus(Qt.MouseFocusReason)
        super().mousePressEvent(event)