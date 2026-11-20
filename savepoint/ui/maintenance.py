"""回收站与备份恢复窗口。"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .. import config
from ..core import backup as backup_mod
from ..core import paths

KIND_LABELS = {"entry": "记录", "screenshot": "截图", "note": "笔记", "document": "文档"}


class TrashDialog(QDialog):
    changed = Signal()

    def __init__(self, parent: QWidget | None, repo, store, doc_store=None) -> None:
        super().__init__(parent)
        self.repo = repo
        self.store = store
        self.doc_store = doc_store

        self.setWindowTitle("回收站")
        self.resize(720, 520)
        self.setModal(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        tip = QLabel("删除的内容会在这里保留 30 天，之后自动清理。")
        tip.setObjectName("Muted")
        layout.addWidget(tip)

        self.list_widget = QListWidget()
        self.list_widget.currentItemChanged.connect(self._sync_buttons)
        layout.addWidget(self.list_widget, 1)

        bottom = QHBoxLayout()
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        bottom.addWidget(self.count_label)
        bottom.addStretch(1)
        self.restore_btn = QPushButton("恢复")
        self.restore_btn.clicked.connect(self._restore)
        self.purge_btn = QPushButton("彻底删除")
        self.purge_btn.setObjectName("Danger")
        self.purge_btn.clicked.connect(self._purge)
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.close)
        for button in (self.restore_btn, self.purge_btn, close_btn):
            bottom.addWidget(button)
        layout.addLayout(bottom)

        self.refresh()

    def refresh(self) -> None:
        self.list_widget.clear()
        items = self.repo.trash_items()
        for item in items:
            label = KIND_LABELS.get(item["kind"], "?")
            text = f"[{label}] {item['title']}　·　{item['sub']}　·　删除于 {paths.human_time(item['deleted_at'])}"
            row = QListWidgetItem(text)
            row.setData(Qt.UserRole, item)
            self.list_widget.addItem(row)
        self.count_label.setText(f"{len(items)} 项" if items else "回收站是空的")
        self._sync_buttons()

    def _current(self) -> dict | None:
        row = self.list_widget.currentItem()
        return None if row is None else row.data(Qt.UserRole)

    def _sync_buttons(self, *args) -> None:  # noqa: ANN002 - Qt 回调
        has = self._current() is not None
        self.restore_btn.setEnabled(has)
        self.purge_btn.setEnabled(has)

    def _restore(self) -> None:
        item = self._current()
        if item is None:
            return
        self.repo.restore_item(item["kind"], item["id"])
        self.refresh()
        self.changed.emit()

    def _purge(self) -> None:
        item = self._current()
        if item is None:
            return
        confirm = QMessageBox.question(
            self, "彻底删除", f"确定永久删除「{item['title']}」？无法恢复。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        files = self.repo.purge_item(item["kind"], item["id"])
        if files:
            if item["kind"] == "document" and self.doc_store is not None:
                self.doc_store.remove(files)
            else:
                self.store.remove_files(files)
        self.refresh()
        self.changed.emit()


class RestoreDialog(QDialog):
    """从快照恢复。"""

    restore_requested = Signal(Path)

    def __init__(self, parent: QWidget | None) -> None:
        super().__init__(parent)
        self.setWindowTitle("从备份恢复")
        self.resize(680, 460)
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        tip = QLabel(
            "选择一份快照恢复。恢复前会自动把当前数据备份到 backups\\pre-restore-…，"
            "恢复完成后程序会退出，重新打开即可。"
        )
        tip.setObjectName("Muted")
        tip.setWordWrap(True)
        layout.addWidget(tip)

        self.list_widget = QListWidget()
        layout.addWidget(self.list_widget, 1)

        bottom = QHBoxLayout()
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        bottom.addWidget(self.count_label)
        bottom.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("恢复选中的快照")
        ok.setObjectName("Primary")
        ok.clicked.connect(self._confirm)
        bottom.addWidget(cancel)
        bottom.addWidget(ok)
        layout.addLayout(bottom)

        self.refresh()

    def refresh(self) -> None:
        self.list_widget.clear()
        snapshots = backup_mod.list_snapshots()
        for path, size in snapshots:
            label = f"{path.stem.replace('snapshot-', '')}　·　{size / 1024 / 1024:.1f} MB"
            row = QListWidgetItem(label)
            row.setData(Qt.UserRole, str(path))
            self.list_widget.addItem(row)
        if snapshots:
            self.list_widget.setCurrentRow(0)
        self.count_label.setText(
            f"{len(snapshots)} 份快照" if snapshots else "还没有快照（启动后会自动生成）"
        )

    def _confirm(self) -> None:
        row = self.list_widget.currentItem()
        if row is None:
            return
        path = Path(row.data(Qt.UserRole))
        confirm = QMessageBox.question(
            self,
            "确认恢复",
            f"将用这份快照覆盖当前数据：\n{path.name}\n\n"
            f"当前数据目录：{config.DATA_DIR}\n"
            "（恢复前会自动备份当前数据）\n\n继续吗？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self.restore_requested.emit(path)
        self.accept()