"""全局搜索与跨项目活动流。"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import config
from ..core import paths

KIND_LABELS = {
    "project": "项目",
    "entry": "记录",
    "note": "笔记",
    "screenshot": "截图",
}


class GlobalSearchDialog(QDialog):
    opened = Signal(dict)

    def __init__(self, parent: QWidget | None, repo) -> None:
        super().__init__(parent)
        self.repo = repo
        self._results: list[dict] = []

        self.setWindowTitle("搜索")
        self.resize(680, 480)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        self.input = QLineEdit()
        self.input.setPlaceholderText("搜项目、记录、笔记、截图说明…（Esc 关闭，回车打开第一条）")
        self.input.textChanged.connect(self._on_text)
        self.input.returnPressed.connect(self._open_first)
        layout.addWidget(self.input)

        self.list_widget = QListWidget()
        self.list_widget.itemActivated.connect(self._open_item)
        layout.addWidget(self.list_widget, 1)

        self.hint = QLabel("输入关键字开始搜索")
        self.hint.setObjectName("Muted")
        layout.addWidget(self.hint)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(180)
        self._timer.timeout.connect(self._search)

    def popup(self) -> None:
        self.input.clear()
        self.list_widget.clear()
        self.hint.setText("输入关键字开始搜索")
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus(Qt.FocusReason.OtherFocusReason)

    def _on_text(self, _text: str) -> None:
        self._timer.start()

    def _search(self) -> None:
        query = self.input.text().strip()
        self.list_widget.clear()
        self._results = self.repo.search_all(query) if query else []
        for result in self._results:
            label = KIND_LABELS.get(result["kind"], "?")
            sub = result.get("sub") or ""
            row = QListWidgetItem(f"[{label}] {result['title']}" + (f"　·　{sub}" if sub else ""))
            row.setData(Qt.UserRole, result)
            self.list_widget.addItem(row)
        if not query:
            self.hint.setText("输入关键字开始搜索")
        elif not self._results:
            self.hint.setText("没有找到匹配的内容")
        else:
            self.hint.setText(f"{len(self._results)} 条结果")
            self.list_widget.setCurrentRow(0)

    def _open_first(self) -> None:
        if self.list_widget.count():
            self._open_item(self.list_widget.item(0))

    def _open_item(self, item: QListWidgetItem) -> None:
        result = item.data(Qt.UserRole)
        if not result:
            return
        self.opened.emit(result)
        self.close()

    def keyPressEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)


class ActivityWindow(QDialog):
    """把全部项目的记录合成一条按日期分组的流。"""

    project_requested = Signal(str)

    def __init__(self, parent: QWidget | None, repo) -> None:
        super().__init__(parent)
        self.repo = repo
        self.setWindowTitle(f"{config.APP_NAME} · 活动流")
        self.resize(760, 640)
        self.setModal(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        top = QHBoxLayout()
        top.addWidget(QLabel("范围"))
        self.range_combo = QComboBox()
        self.range_combo.addItem("最近 7 天", 7)
        self.range_combo.addItem("最近 30 天", 30)
        self.range_combo.addItem("最近 90 天", 90)
        self.range_combo.addItem("全部", None)
        self.range_combo.currentIndexChanged.connect(self.refresh)
        top.addWidget(self.range_combo)
        top.addStretch(1)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        top.addWidget(self.count_label)
        layout.addLayout(top)

        self.list_widget = QListWidget()
        self.list_widget.itemActivated.connect(self._on_activated)
        layout.addWidget(self.list_widget, 1)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)

    def refresh(self) -> None:
        days = self.range_combo.currentData()
        rows = self.repo.activity(days=days, limit=400)
        self.list_widget.clear()
        current_day = None
        for row in rows:
            day = row["created_at"][:10]
            if day != current_day:
                current_day = day
                header = QListWidgetItem(day)
                header.setFlags(Qt.ItemFlag.NoItemFlags)
                font = header.font()
                font.setBold(True)
                header.setFont(font)
                header.setForeground(Qt.GlobalColor.gray)
                self.list_widget.addItem(header)
            stamp = row["created_at"][11:16]
            item = QListWidgetItem(f"{stamp}　{row['project']}　{row['body'][:70]}")
            item.setData(Qt.UserRole, row["project_id"])
            item.setToolTip(row["body"])
            self.list_widget.addItem(item)
        self.count_label.setText(f"{len(rows)} 条记录")

    def _on_activated(self, item: QListWidgetItem) -> None:
        project_id = item.data(Qt.UserRole)
        if not project_id:
            return
        self.project_requested.emit(project_id)
        self.close()