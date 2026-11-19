"""笔记：分区树 + 正文编辑。

导航区是「分区 > 文档」的折叠树，深色主题；右侧正文边写边存。
纯明文，没有任何加密/锁定。
"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import config
from ..core import paths
from .icons import folder_icon, note_icon
from .selection import GlowDelegate, ensure_animating

DEFAULT_FOLDER = "未分类"

DARK_QSS = """
QWidget {
    background: #0f1113;
    color: #e7e9ec;
    font-family: "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
    font-size: 10.5pt;
}
QLabel { background: transparent; color: #e7e9ec; }
QLabel#NoteMuted { color: #8b929c; font-size: 9pt; }

QLineEdit, QPlainTextEdit, QComboBox {
    background: #16191d;
    border: 1px solid #24282e;
    border-radius: 6px;
    padding: 6px 9px;
    color: #e7e9ec;
    selection-background-color: #33507f;
    selection-color: #ffffff;
}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border: 1px solid #5b8cff; }
QLineEdit#NoteTitle {
    font-size: 14pt; font-weight: 600; background: transparent;
    border: none; border-bottom: 1px solid #24282e; border-radius: 0; padding: 4px 0;
}
QComboBox QAbstractItemView {
    background: #16191d; color: #e7e9ec;
    border: 1px solid #24282e; selection-background-color: #1d2734;
    selection-color: #ffffff; outline: none;
}

QTreeWidget { background: #101215; border: none; outline: none; }
QTreeWidget::item {
    color: #d7dbe0; padding: 5px 2px; border-radius: 6px; margin: 1px 2px;
}
QTreeWidget::item:hover { background: #171b20; }
QTreeWidget::item:selected { background: #1d2734; color: #ffffff; }
QTreeView::branch { background: #101215; }
QTreeView::branch:selected { background: #101215; }
QTreeView::branch:hover { background: #101215; }

QPushButton {
    background: #1a1e23; border: 1px solid #2a2f36; border-radius: 6px;
    padding: 6px 13px; color: #e7e9ec;
}
QPushButton:hover { background: #22272e; }
QPushButton:pressed { background: #14171b; }
QPushButton#NotePrimary {
    background: #2f6feb; border: 1px solid #2f6feb; color: #ffffff; font-weight: 600;
}
QPushButton#NotePrimary:hover { background: #3d7bf5; }
QPushButton#NoteDanger { color: #ff8a80; border-color: #3a2a2a; }
QPushButton#NoteDanger:hover { background: #2a1c1c; }
QPushButton#NoteGhost {
    background: transparent; border: none; color: #8b929c; text-align: left;
    padding: 6px 8px;
}
QPushButton#NoteGhost:hover { background: #171b20; color: #e7e9ec; }

QDialog, QMessageBox { background: #0f1113; color: #e7e9ec; }
QMessageBox QLabel { color: #e7e9ec; background: transparent; }

QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #2b3138; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #3a424b; }
QScrollBar::add-line, QScrollBar::sub-line { height: 0; width: 0; }

QSplitter::handle { background: #191c20; }
"""


class TextPromptDialog(QDialog):
    """深色输入框，用于新建分区。"""

    def __init__(self, parent: QWidget | None, title: str, label: str, default: str = "") -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(360)
        self.setStyleSheet(DARK_QSS)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(10)
        tip = QLabel(label)
        tip.setWordWrap(True)
        layout.addWidget(tip)
        self.edit = QLineEdit(default)
        self.edit.setPlaceholderText("输入名称")
        self.edit.returnPressed.connect(self.accept)
        layout.addWidget(self.edit)

        row = QHBoxLayout()
        row.addStretch(1)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        ok = QPushButton("确定")
        ok.setObjectName("NotePrimary")
        ok.setDefault(True)
        ok.clicked.connect(self.accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        layout.addLayout(row)

    def value(self) -> str:
        return self.edit.text().strip()

    def accept(self) -> None:
        if self.value():
            super().accept()


class NotesWindow(QDialog):
    def __init__(self, parent: QWidget | None, repo, note_id: str | None = None) -> None:
        super().__init__(parent)
        self.repo = repo
        self._current_id: str | None = None
        self._loading = False
        self._folder_icons: dict[str, QIcon] = {}

        self.setWindowTitle(f"{config.APP_NAME} · 笔记")
        self.resize(1080, 720)
        self.setModal(False)
        self.setStyleSheet(DARK_QSS)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(500)
        self._save_timer.timeout.connect(self._save_current)

        self._build()
        self.refresh(note_id)

    # ---------------- 构建 ----------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        splitter = QHBoxLayout()
        splitter.setSpacing(12)
        root.addLayout(splitter, 1)

        # 左侧：分区树
        left = QWidget()
        left.setFixedWidth(230)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(6)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索笔记…")
        self.search_edit.textChanged.connect(self._rebuild_tree)
        left_layout.addWidget(self.search_edit)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(16)
        self.tree.setAnimated(True)
        self.tree.setRootIsDecorated(False)
        self.tree.setIconSize(QSize(36, 18))
        self.tree.setItemDelegate(GlowDelegate(self.tree))
        ensure_animating(self.tree)
        self.tree.itemClicked.connect(self._on_item_clicked)
        self.tree.itemExpanded.connect(self._on_folder_toggle)
        self.tree.itemCollapsed.connect(self._on_folder_toggle)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        left_layout.addWidget(self.tree, 1)

        self.new_folder_btn = QPushButton("＋ 新建分区")
        self.new_folder_btn.setObjectName("NoteGhost")
        self.new_folder_btn.clicked.connect(self._create_folder)
        left_layout.addWidget(self.new_folder_btn)
        splitter.addWidget(left)

        # 右侧：编辑器
        right = QWidget()
        editor = QVBoxLayout(right)
        editor.setContentsMargins(0, 0, 0, 0)
        editor.setSpacing(8)

        top_row = QHBoxLayout()
        self.title_edit = QLineEdit()
        self.title_edit.setObjectName("NoteTitle")
        self.title_edit.setPlaceholderText("无标题")
        self.title_edit.textChanged.connect(self._schedule_save)
        top_row.addWidget(self.title_edit, 1)
        self.folder_combo = QComboBox()
        self.folder_combo.setEditable(True)
        self.folder_combo.setFixedWidth(150)
        self.folder_combo.setToolTip("所在分区（可以直接输入新名字）")
        self.folder_combo.currentTextChanged.connect(self._on_folder_combo)
        top_row.addWidget(self.folder_combo)
        editor.addLayout(top_row)

        self.content_edit = QPlainTextEdit()
        self.content_edit.setPlaceholderText("在这里写…（停手即保存）")
        self.content_edit.textChanged.connect(self._schedule_save)
        editor.addWidget(self.content_edit, 1)

        bottom = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setObjectName("NoteMuted")
        bottom.addWidget(self.status_label)
        bottom.addStretch(1)
        self.copy_btn = QPushButton("复制正文")
        self.copy_btn.clicked.connect(self._copy)
        self.delete_btn = QPushButton("删除")
        self.delete_btn.setObjectName("NoteDanger")
        self.delete_btn.clicked.connect(self._delete)
        self.new_note_btn = QPushButton("新建笔记")
        self.new_note_btn.setObjectName("NotePrimary")
        self.new_note_btn.clicked.connect(self._create_note)
        for button in (self.copy_btn, self.delete_btn, self.new_note_btn):
            bottom.addWidget(button)
        editor.addLayout(bottom)

        splitter.addWidget(right, 1)
        self._set_editor_enabled(False)

    def _set_editor_enabled(self, enabled: bool) -> None:
        for widget in (self.title_edit, self.content_edit, self.folder_combo):
            widget.setEnabled(enabled)
        for button in (self.copy_btn, self.delete_btn):
            button.setEnabled(enabled)

    # ---------------- 树 ----------------

    def _icon_for(self, folder: str, expanded: bool = True) -> QIcon:
        key = (folder, expanded)
        if key not in self._folder_icons:
            self._folder_icons[key] = folder_icon(folder, expanded, dark=True)
        return self._folder_icons[key]

    def refresh(self, note_id: str | None = None) -> None:
        self._rebuild_tree(note_id)

    def _on_folder_toggle(self, item: QTreeWidgetItem) -> None:
        data = item.data(0, Qt.UserRole)
        if data and data[0] == "folder":
            item.setIcon(0, self._icon_for(data[1], item.isExpanded()))

    def _rebuild_tree(self, note_id: str | None = None) -> None:
        target = note_id or self._current_id
        query = self.search_edit.text().strip() or None

        expanded = set()
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            data = item.data(0, Qt.UserRole)
            if data and data[0] == "folder" and item.isExpanded():
                expanded.add(data[1])

        self.tree.blockSignals(True)
        self.tree.clear()
        selected_item = None

        if query:
            root = QTreeWidgetItem(["搜索结果"])
            root.setIcon(0, self._icon_for("搜索结果", True))
            self.tree.addTopLevelItem(root)
            for note in self.repo.list_notes(query=query):
                child = self._note_item(note)
                root.addChild(child)
                if note.id == target:
                    selected_item = child
            root.setExpanded(True)
        else:
            for folder, _count in self.repo.note_folders():
                is_open = folder in expanded or target is not None or \
                    self.tree.topLevelItemCount() == 0
                node = QTreeWidgetItem([folder])
                node.setIcon(0, self._icon_for(folder, is_open))
                node.setData(0, Qt.UserRole, ("folder", folder))
                font = node.font(0)
                font.setBold(True)
                node.setFont(0, font)
                self.tree.addTopLevelItem(node)
                for note in self.repo.list_notes(folder=folder):
                    child = self._note_item(note)
                    node.addChild(child)
                    if note.id == target:
                        selected_item = child
                node.setExpanded(is_open)

        self.tree.blockSignals(False)
        if selected_item is not None:
            self.tree.setCurrentItem(selected_item)

        if self._current_id is None and self.tree.topLevelItemCount():
            first_note = self._first_note_item()
            if first_note is not None:
                self.tree.setCurrentItem(first_note)
                self._load_note(first_note.data(0, Qt.UserRole)[1])

    def _note_item(self, note) -> QTreeWidgetItem:
        title = note.title.strip() or "无标题"
        item = QTreeWidgetItem([title])
        item.setIcon(0, note_icon(title))
        item.setData(0, Qt.UserRole, ("note", note.id))
        item.setToolTip(0, f"更新于 {paths.human_time(note.updated_at, with_year=True)}")
        return item

    def _first_note_item(self) -> QTreeWidgetItem | None:
        for index in range(self.tree.topLevelItemCount()):
            node = self.tree.topLevelItem(index)
            if node.childCount():
                return node.child(0)
        return None

    def _on_item_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        data = item.data(0, Qt.UserRole)
        if not data:
            item.setExpanded(not item.isExpanded())
            return
        kind, value = data
        if kind == "note":
            self._save_current()
            self._load_note(value)

    # ---------------- 右键菜单 ----------------

    def _on_context_menu(self, pos) -> None:  # noqa: ANN001 - Qt 回调
        item = self.tree.itemAt(pos)
        if item is None:
            return
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        kind, value = data

        menu = QMenu(self)
        if kind == "folder":
            menu.addAction("新建笔记", lambda: self._new_note_in(value))
            menu.addAction("重命名分区…", lambda: self._rename_folder(value))
            menu.addSeparator()
            menu.addAction("删除分区…", lambda: self._delete_folder(value))
        else:
            menu.addAction("重命名笔记…", lambda: self._rename_note(value))
            move_menu = menu.addMenu("移动到分区")
            folders = [name for name, _count in self.repo.note_folders()]
            for name in folders:
                move_menu.addAction(name, lambda n=name: self._move_note(value, n))
            if not folders:
                move_menu.setEnabled(False)
            menu.addSeparator()
            menu.addAction("删除笔记…", lambda: self._delete_note(value))

        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _prompt(self, title: str, label: str, default: str = "") -> str | None:
        from .dialogs import TextPromptDialog

        dialog = TextPromptDialog(self, title, label, default)
        dialog.setStyleSheet(DARK_QSS)
        if not dialog.exec():
            return None
        return dialog.value() or None

    def _rename_note(self, note_id: str) -> None:
        note = self.repo.get_note(note_id)
        if note is None:
            return
        name = self._prompt("重命名笔记", "新的标题", note.title)
        if not name:
            return
        self.repo.rename_note(note_id, name)
        self._rebuild_tree(note_id)

    def _rename_folder(self, folder: str) -> None:
        name = self._prompt("重命名分区", "新的分区名", folder)
        if not name or name == folder:
            return
        moved = self.repo.rename_folder(folder, name)
        self._rebuild_tree(self._current_id)
        if self._current_id:
            note = self.repo.get_note(self._current_id)
            if note is not None:
                self._sync_folder_combo(note.folder)
        elif moved:
            self.status_label.setText(f"已重命名，{moved} 篇笔记归到「{name}」")

    def _delete_note(self, note_id: str) -> None:
        note = self.repo.get_note(note_id)
        if note is None:
            return
        confirm = QMessageBox.question(
            self, "删除笔记",
            f"确定删除「{note.title.strip() or '无标题'}」？\n会进回收站，30 天内可恢复。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self.repo.delete_note(note_id)
        if self._current_id == note_id:
            self._current_id = None
        self._rebuild_tree()

    def _delete_folder(self, folder: str) -> None:
        _name, count = next(
            ((name, n) for name, n in self.repo.note_folders() if name == folder),
            (folder, 0),
        )
        if count == 0:
            return
        confirm = QMessageBox.question(
            self, "删除分区",
            f"「{folder}」里有 {count} 篇笔记，全部移进回收站？\n30 天内可以恢复。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self.repo.delete_folder(folder)
        if self._current_id:
            note = self.repo.get_note(self._current_id)
            if note is None or note.folder == folder:
                self._current_id = None
        self._rebuild_tree()

    def _move_note(self, note_id: str, folder: str) -> None:
        self.repo.move_note(note_id, folder)
        self._rebuild_tree(note_id)

    def _new_note_in(self, folder: str) -> None:
        note = self.repo.create_note(folder=folder, title="", content="")
        self._rebuild_tree(note.id)
        self.title_edit.setFocus()

    # ---------------- 编辑器 ----------------

    def _load_note(self, note_id: str) -> None:
        note = self.repo.get_note(note_id)
        if note is None:
            return
        self._current_id = note_id
        self._set_editor_enabled(True)
        self._loading = True
        self.title_edit.setText(note.title)
        self.content_edit.setPlainText(note.content)
        self._sync_folder_combo(note.folder)
        self._loading = False
        self.status_label.setText(f"更新于 {paths.human_time(note.updated_at)}")

    def _sync_folder_combo(self, folder: str) -> None:
        self.folder_combo.blockSignals(True)
        self.folder_combo.clear()
        names = [name for name, _ in self.repo.note_folders()]
        if folder not in names:
            names.insert(0, folder)
        self.folder_combo.addItems(names)
        index = self.folder_combo.findText(folder)
        if index >= 0:
            self.folder_combo.setCurrentIndex(index)
        else:
            self.folder_combo.setEditText(folder)
        self.folder_combo.blockSignals(False)

    def _schedule_save(self) -> None:
        if self._loading or not self._current_id:
            return
        self.status_label.setText("正在保存…")
        self._save_timer.start()

    def _save_current(self) -> None:
        if not self._current_id:
            return
        note = self.repo.get_note(self._current_id)
        if note is None:
            return
        title = self.title_edit.text()
        content = self.content_edit.toPlainText()
        folder = self.folder_combo.currentText().strip() or DEFAULT_FOLDER
        if title == note.title and content == note.content and folder == note.folder:
            return
        self.repo.update_note(self._current_id, title=title, content=content, folder=folder)
        self.status_label.setText("已保存")
        self._rebuild_tree(self._current_id)

    def _on_folder_combo(self, text: str) -> None:
        if self._loading or not self._current_id:
            return
        folder = text.strip()
        if not folder:
            return
        self.repo.update_note(self._current_id, folder=folder)
        self._rebuild_tree(self._current_id)

    # ---------------- 操作 ----------------

    def _current_folder(self) -> str:
        item = self.tree.currentItem()
        if item is not None:
            data = item.data(0, Qt.UserRole)
            if data and data[0] == "folder":
                return data[1]
            parent = item.parent()
            if parent is not None and parent.data(0, Qt.UserRole):
                return parent.data(0, Qt.UserRole)[1]
        folders = self.repo.note_folders()
        return folders[0][0] if folders else DEFAULT_FOLDER

    def _create_folder(self) -> None:
        dialog = TextPromptDialog(self, "新建分区", "给新分区起个名字，例如：灵感 / 配置 / 账号")
        if not dialog.exec():
            return
        name = dialog.value()
        note = self.repo.create_note(folder=name, title="", content="")
        self._current_id = None
        self._rebuild_tree(note.id)
        self.title_edit.setFocus()

    def _create_note(self) -> None:
        self._save_current()
        folder = self._current_folder()
        note = self.repo.create_note(folder=folder, title="", content="")
        self._rebuild_tree(note.id)
        self.title_edit.setFocus()
        self.title_edit.selectAll()

    def _delete(self) -> None:
        if not self._current_id:
            return
        note = self.repo.get_note(self._current_id)
        if note is None:
            return
        confirm = QMessageBox.question(
            self, "删除笔记",
            f"确定删除「{note.title.strip() or '无标题'}」？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self.repo.delete_note(self._current_id)
        self._current_id = None
        self._rebuild_tree()

    def _copy(self) -> None:
        text = self.content_edit.toPlainText()
        if text:
            QGuiApplication.clipboard().setText(text)
            self.status_label.setText("正文已复制")

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if self._save_timer.isActive():
            self._save_timer.stop()
            self._save_current()
        super().closeEvent(event)