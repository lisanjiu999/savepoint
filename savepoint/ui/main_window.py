"""主窗口：筛选栏 + 项目列表 + 详情。"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFontMetrics, QGuiApplication, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import config
from ..core import backup as backup_mod
from ..core.paths import human_size, parse_iso
from ..core.repo import Project, Repo
from ..core.storage import ShotStore
from .dialogs import ProjectDialog, TextPromptDialog, show_open_failure
from .document_library import DocumentLibraryWindow
from .hotkey import GlobalHotkey
from .icons import folder_icon, note_icon
from .maintenance import RestoreDialog, TrashDialog
from .notes import NotesWindow
from .project_detail import ProjectDetail
from .quick_capture import QuickCaptureDialog
from .search import ActivityWindow, GlobalSearchDialog
from .selection import GlowDelegate, ensure_animating, glow_color
from .settings_dialog import SettingsDialog
from .style import STATUS_COLORS

STATE_FILE_NAME = "ui_state.json"


class ProjectCard(QWidget):
    """左侧列表里的紧凑卡片。"""

    def __init__(self, project: Project, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ProjectCardRoot")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.project = project
        self._selected = False
        self.setFixedHeight(66)
        self._texts: list[tuple[QLabel, str]] = []
        self.setStyleSheet(
            "#ProjectCardRoot { background: transparent;"
            " border: 2px solid transparent; border-radius: 7px; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(3)

        top = QHBoxLayout()
        top.setSpacing(7)
        dot = QLabel()
        dot.setFixedSize(8, 8)
        color = STATUS_COLORS.get(project.status, "#9ca3af")
        dot.setStyleSheet(f"background:{color}; border-radius:4px;")
        top.addWidget(dot, 0, Qt.AlignVCenter)

        name = QLabel(project.name)
        name.setStyleSheet("font-weight:600; font-size:10.5pt;")
        top.addWidget(name, 1)

        delta = self._stale_badge(project)
        if delta:
            badge = QLabel(delta)
            badge.setStyleSheet(
                "color:#d97706; font-size:8.5pt; background:#fef3c7;"
                " border-radius:8px; padding:1px 7px;"
            )
            top.addWidget(badge, 0, Qt.AlignVCenter)

        layout.addLayout(top)

        summary_text = project.summary or (
            f"# {' '.join(project.tags)}" if project.tags else "还没写描述"
        )
        summary = QLabel(summary_text)
        summary.setObjectName("Muted")
        summary.setStyleSheet("color:#6b7280; font-size:9pt;")
        layout.addWidget(summary)
        self._texts.append((summary, summary_text))

        self._summary_label = summary

    @staticmethod
    def _stale_badge(project: Project) -> str:
        if project.status != "active":
            return ""
        updated = parse_iso(project.updated_at)
        if updated is None:
            return ""
        days = (datetime.now() - updated).days
        if days >= config.STALE_DAYS:
            return f"{days} 天未动"
        return ""

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        super().resizeEvent(event)
        label, text = self._texts[0]
        available = max(40, label.width() - 4)
        metrics = QFontMetrics(label.font())
        label.setText(metrics.elidedText(text, Qt.ElideRight, available))

    def set_selected(self, selected: bool) -> None:
        self._selected = selected
        if selected:
            self.set_glow(glow_color())
        else:
            self.setStyleSheet(
                "#ProjectCardRoot { background: transparent;"
                " border: 2px solid transparent; border-radius: 7px; }"
            )

    def set_glow(self, color: QColor) -> None:
        self.setStyleSheet(
            "#ProjectCardRoot { background: #f7faff;"
            f" border: 2px solid {color.name()}; border-radius: 7px; }}"
        )


class MainWindow(QMainWindow):
    def __init__(self, repo: Repo, store: ShotStore, doc_store=None) -> None:
        super().__init__()
        self.repo = repo
        self.store = store
        self.doc_store = doc_store
        self.notes_window: NotesWindow | None = None
        self.documents_window = None
        self.search_dialog: GlobalSearchDialog | None = None
        self.activity_window: ActivityWindow | None = None
        self.trash_dialog: TrashDialog | None = None
        self.tray: QSystemTrayIcon | None = None
        self.hotkey: GlobalHotkey | None = None
        self.capture_dialog: QuickCaptureDialog | None = None
        self._force_quit = False
        self._tray_hint_shown = False
        self._selected_id: str | None = None
        self._cards: dict[str, ProjectCard] = {}
        self._selected_card: ProjectCard | None = None

        self._glow_timer = QTimer(self)
        self._glow_timer.setInterval(60)
        self._glow_timer.timeout.connect(self._tick_card_glow)
        self._glow_timer.start()

        self.setWindowTitle(config.APP_NAME)
        self.resize(1180, 760)
        self.setMinimumSize(980, 620)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(180)
        self._search_timer.timeout.connect(self.refresh_projects)

        self._build()
        self._install_shortcuts()
        self._restore_state()
        self.refresh_all()
        self._setup_tray()
        self._setup_hotkey()

    # ---------------- 构建 ----------------

    def _build(self) -> None:
        central = QWidget()
        central.setObjectName("Root")
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_topbar())

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())
        body.addWidget(self._build_listpane(), 1)
        body.addWidget(self._build_detail(), 2)
        root.addLayout(body, 1)

    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(56)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 8, 16, 8)
        layout.setSpacing(8)

        title = QLabel("项目管理")
        title.setObjectName("AppTitle")
        layout.addWidget(title)

        self.total_label = QLabel("")
        self.total_label.setObjectName("Muted")
        layout.addWidget(self.total_label)
        layout.addStretch(1)

        docs_btn = QPushButton("📄 文档库")
        docs_btn.setToolTip("收纳桌面上的 Word / PDF / Excel 等文件（Ctrl+Shift+D）")
        docs_btn.clicked.connect(self.open_documents)
        layout.addWidget(docs_btn)

        new_btn = QPushButton("+ 新建项目")
        new_btn.setObjectName("Primary")
        new_btn.clicked.connect(self.new_project)
        layout.addWidget(new_btn)

        more_btn = QPushButton("⋯")
        more_btn.setFixedWidth(38)
        more_btn.clicked.connect(self._show_app_menu)
        layout.addWidget(more_btn)
        return bar

    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(196)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(8, 14, 8, 14)
        layout.setSpacing(6)

        views_label = QLabel("视图")
        views_label.setObjectName("SectionTitle")
        views_label.setContentsMargins(8, 0, 0, 2)
        layout.addWidget(views_label)

        self.views_list = QListWidget()
        self.views_list.setFocusPolicy(Qt.NoFocus)
        self.views_list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.views_list.setItemDelegate(GlowDelegate(self.views_list))
        ensure_animating(self.views_list)
        self.views_list.currentItemChanged.connect(lambda *_: self.refresh_projects())
        layout.addWidget(self.views_list)

        tags_label = QLabel("标签")
        tags_label.setObjectName("SectionTitle")
        tags_label.setContentsMargins(8, 12, 0, 2)
        layout.addWidget(tags_label)

        self.tags_list = QListWidget()
        self.tags_list.setFocusPolicy(Qt.NoFocus)
        self.tags_list.setMaximumHeight(150)
        self.tags_list.setItemDelegate(GlowDelegate(self.tags_list))
        ensure_animating(self.tags_list)
        self.tags_list.currentItemChanged.connect(lambda *_: self.refresh_projects())
        layout.addWidget(self.tags_list)

        notes_label = QLabel("笔记")
        notes_label.setObjectName("SectionTitle")
        notes_label.setContentsMargins(8, 12, 0, 2)
        layout.addWidget(notes_label)

        self.notes_tree = QTreeWidget()
        self.notes_tree.setHeaderHidden(True)
        self.notes_tree.setFocusPolicy(Qt.NoFocus)
        self.notes_tree.setIndentation(14)
        self.notes_tree.setRootIsDecorated(False)
        self.notes_tree.setIconSize(QSize(36, 18))
        self.notes_tree.setItemDelegate(GlowDelegate(self.notes_tree))
        ensure_animating(self.notes_tree)
        self.notes_tree.itemClicked.connect(self._on_note_tree_clicked)
        self.notes_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.notes_tree.customContextMenuRequested.connect(self._on_note_tree_menu)
        layout.addWidget(self.notes_tree, 1)
        return side

    def _refresh_notes_tree(self) -> None:
        """侧栏「笔记」：分区下面挂文档，点开直接读。"""
        self.notes_tree.blockSignals(True)
        self.notes_tree.clear()
        total = self.repo.count_notes()
        root = QTreeWidgetItem([f"全部笔记　{total}"])
        root.setIcon(0, folder_icon("全部笔记", True, dark=False))
        root.setData(0, Qt.UserRole, ("all", None))
        self.notes_tree.addTopLevelItem(root)
        for name, count in self.repo.note_folders():
            node = QTreeWidgetItem([f"{name}　{count}"])
            node.setIcon(0, folder_icon(name, True, dark=False))
            node.setData(0, Qt.UserRole, ("folder", name))
            root.addChild(node)
            for note in self.repo.list_notes(folder=name):
                title = note.title.strip() or "无标题"
                child = QTreeWidgetItem([title])
                child.setIcon(0, note_icon(title))
                child.setData(0, Qt.UserRole, ("note", note.id))
                node.addChild(child)
            node.setExpanded(True)
        root.setExpanded(True)
        self.notes_tree.blockSignals(False)

    def _on_note_tree_clicked(self, item, _column) -> None:  # noqa: ANN001 - Qt 回调
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        kind, value = data
        if kind == "folder":
            item.setExpanded(not item.isExpanded())
            item.setIcon(0, folder_icon(value, item.isExpanded(), dark=False))
        elif kind == "note":
            self.open_notes(value)
        else:
            self.open_notes()

    def _on_note_tree_menu(self, pos) -> None:  # noqa: ANN001 - Qt 回调
        item = self.notes_tree.itemAt(pos)
        if item is None:
            return
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        kind, value = data
        menu = QMenu(self)

        if kind == "folder":
            menu.addAction("打开笔记", lambda: self.open_notes())
            menu.addAction("新建笔记", lambda: self._new_note_in(value))
            menu.addAction("重命名分区…", lambda: self._rename_folder(value))
            menu.addSeparator()
            menu.addAction("删除分区…", lambda: self._delete_folder(value))
        elif kind == "note":
            menu.addAction("打开", lambda: self.open_notes(value))
            menu.addAction("重命名笔记…", lambda: self._rename_note(value))
            move_menu = menu.addMenu("移动到分区")
            folders = [name for name, _count in self.repo.note_folders()]
            for name in folders:
                move_menu.addAction(name, lambda n=name: self._move_note(value, n))
            if not folders:
                move_menu.setEnabled(False)
            menu.addSeparator()
            menu.addAction("删除笔记…", lambda: self._delete_note(value))
        else:
            menu.addAction("打开笔记", lambda: self.open_notes())

        menu.exec(self.notes_tree.viewport().mapToGlobal(pos))

    def _prompt_text(self, title: str, label: str, default: str = "") -> str | None:
        dialog = TextPromptDialog(self, title, label, default)
        if not dialog.exec():
            return None
        return dialog.value() or None

    def _rename_note(self, note_id: str) -> None:
        note = self.repo.get_note(note_id)
        if note is None:
            return
        name = self._prompt_text("重命名笔记", "新的标题", note.title)
        if not name:
            return
        self.repo.rename_note(note_id, name)
        self.refresh_all()
        if self.notes_window is not None:
            self.notes_window.refresh(note_id)

    def _rename_folder(self, folder: str) -> None:
        name = self._prompt_text("重命名分区", "新的分区名", folder)
        if not name or name == folder:
            return
        self.repo.rename_folder(folder, name)
        self.refresh_all()
        if self.notes_window is not None:
            self.notes_window.refresh()

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
        self.refresh_all()
        if self.notes_window is not None:
            self.notes_window.refresh()

    def _delete_folder(self, folder: str) -> None:
        count = dict(self.repo.note_folders()).get(folder, 0)
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
        self.refresh_all()
        if self.notes_window is not None:
            self.notes_window.refresh()

    def _move_note(self, note_id: str, folder: str) -> None:
        self.repo.move_note(note_id, folder)
        self.refresh_all()
        if self.notes_window is not None:
            self.notes_window.refresh(note_id)

    def _new_note_in(self, folder: str) -> None:
        note = self.repo.create_note(folder=folder, title="", content="")
        self.refresh_all()
        self.open_notes(note.id)

    def _build_listpane(self) -> QWidget:
        pane = QWidget()
        pane.setObjectName("Sidebar")
        pane.setFixedWidth(330)
        layout = QVBoxLayout(pane)
        layout.setContentsMargins(10, 12, 8, 12)
        layout.setSpacing(8)

        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("SearchBox")
        self.search_edit.setPlaceholderText("搜索项目 / 备注 / 记录…  Ctrl+F")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(lambda _: self._search_timer.start())
        layout.addWidget(self.search_edit)

        self.project_list = QListWidget()
        self.project_list.setSpacing(2)
        self.project_list.currentItemChanged.connect(self._on_project_selected)
        self.project_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.project_list.customContextMenuRequested.connect(self._project_context_menu)
        layout.addWidget(self.project_list, 1)

        self.list_hint = QLabel("")
        self.list_hint.setObjectName("Muted")
        self.list_hint.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.list_hint)
        return pane

    def _build_detail(self) -> QWidget:
        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_empty_state())

        self.detail = ProjectDetail(self.repo, self.store)
        self.detail.documents_requested.connect(self._import_into_library)
        self.detail.changed.connect(self._on_detail_changed)
        self.detail.deleted.connect(self._on_project_deleted)
        self.stack.addWidget(self.detail)
        return self.stack

    def _build_empty_state(self) -> QWidget:
        page = QWidget()
        page.setObjectName("Root")
        layout = QVBoxLayout(page)
        layout.addStretch(1)
        title = QLabel("三个月后，你还记得当时在做什么吗？")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("font-size:14pt; font-weight:600; color:#374151;")
        layout.addWidget(title)
        hint = QLabel(
            "左边选一个项目，或点右上角「新建项目」。\n"
            "记录会自动保存；截图可以拖进来，也可以按 Ctrl+V 粘贴。"
        )
        hint.setAlignment(Qt.AlignCenter)
        hint.setObjectName("Muted")
        layout.addWidget(hint)
        layout.addStretch(1)
        return page

    def _install_shortcuts(self) -> None:
        bindings = [
            ("Ctrl+N", self.new_project),
            ("Ctrl+F", self._focus_search),
            ("Ctrl+K", self.open_search),
            ("Ctrl+Shift+V", self.open_notes),
            ("Ctrl+Shift+D", lambda: self.open_documents()),
            ("Ctrl+Shift+B", self.run_backup),
            ("Ctrl+Shift+T", self.open_trash),
        ]
        for sequence, slot in bindings:
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(slot)

    # ---------------- 刷新 ----------------

    def _current_view(self) -> str:
        item = self.views_list.currentItem()
        if item is None:
            return "all"
        return item.data(Qt.UserRole) or "all"

    def _current_tag(self) -> str | None:
        item = self.tags_list.currentItem()
        if item is None:
            return None
        return item.data(Qt.UserRole)

    def refresh_all(self) -> None:
        self._refresh_views()
        self._refresh_tags()
        self._refresh_notes_tree()
        self.refresh_projects()

    def _refresh_views(self) -> None:
        counts = self.repo.status_counts()
        stale = len(self.repo.stale_projects(config.STALE_DAYS))
        recent = len(self.repo.recent_projects(config.RECENT_DAYS))
        entries: list[tuple[str, str, int, bool]] = [
            ("all", "全部", counts.get("all", 0), True),
            ("recent", "最近更新", recent, True),
            ("stale", "长期未动", stale, True),
            ("sep", "", 0, False),
            ("active", "进行中", counts.get("active", 0), True),
            ("paused", "暂停", counts.get("paused", 0), True),
            ("done", "完成", counts.get("done", 0), True),
            ("archived", "归档", counts.get("archived", 0), True),
        ]
        keep = self._current_view()
        self.views_list.blockSignals(True)
        self.views_list.clear()
        for key, label, count, enabled in entries:
            if key == "sep":
                row = QListWidgetItem("按状态")
                row.setFlags(Qt.NoItemFlags)
                row.setForeground(QColor("#9ca3af"))
                font = row.font()
                font.setPointSize(8)
                row.setFont(font)
                row.setSizeHint(QSize(0, 26))
                self.views_list.addItem(row)
                continue
            row = QListWidgetItem(f"{label}　{count}")
            row.setData(Qt.UserRole, key)
            if not enabled:
                row.setFlags(Qt.NoItemFlags)
            self.views_list.addItem(row)
            if key == keep:
                self.views_list.setCurrentItem(row)
        self.views_list.blockSignals(False)
        if self.views_list.currentItem() is None:
            self.views_list.setCurrentRow(0)

    def _refresh_tags(self) -> None:
        keep = self._current_tag()
        self.tags_list.blockSignals(True)
        self.tags_list.clear()
        all_row = QListWidgetItem("全部标签")
        all_row.setData(Qt.UserRole, None)
        self.tags_list.addItem(all_row)
        for name, count in self.repo.all_tags():
            row = QListWidgetItem(f"#{name}　{count}")
            row.setData(Qt.UserRole, name)
            self.tags_list.addItem(row)
        self.tags_list.blockSignals(False)
        self.tags_list.setCurrentRow(0)
        if keep:
            for index in range(1, self.tags_list.count()):
                if self.tags_list.item(index).data(Qt.UserRole) == keep:
                    self.tags_list.setCurrentRow(index)
                    break

    def _collect_projects(self) -> list[Project]:
        view = self._current_view()
        tag = self._current_tag()
        query = self.search_edit.text().strip() or None

        status = view if view in config.STATUS_ORDER else None
        projects = self.repo.list_projects(status=status, tag=tag, query=query)

        if view == "recent":
            cutoff = (datetime.now() - timedelta(days=config.RECENT_DAYS)).strftime(
                "%Y-%m-%dT%H:%M:%S"
            )
            projects = [p for p in projects if p.updated_at >= cutoff]
        elif view == "stale":
            cutoff = (datetime.now() - timedelta(days=config.STALE_DAYS)).strftime(
                "%Y-%m-%dT%H:%M:%S"
            )
            projects = [p for p in projects if p.status == "active" and p.updated_at < cutoff]
            projects.sort(key=lambda p: p.updated_at)
        return projects

    def refresh_projects(self) -> None:
        projects = self._collect_projects()
        self._selected_card = None
        self.project_list.blockSignals(True)
        self.project_list.clear()
        self._cards.clear()
        for project in projects:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, project.id)
            card = ProjectCard(project)
            item.setSizeHint(QSize(300, 66))
            self.project_list.addItem(item)
            self.project_list.setItemWidget(item, card)
            self._cards[project.id] = card
        self.project_list.blockSignals(False)

        total = self.repo.status_counts().get("all", 0)
        self.total_label.setText(f"{total} 个项目")
        self.list_hint.setText("" if projects else ("没有匹配的项目" if total else "还没有项目，点右上角新建"))

        target = self._selected_id
        row = -1
        if target:
            for index in range(self.project_list.count()):
                if self.project_list.item(index).data(Qt.UserRole) == target:
                    row = index
                    break
        if row < 0 and self.project_list.count():
            row = 0
        if row >= 0:
            self.project_list.setCurrentRow(row)
            self._select_in_detail(self.project_list.item(row).data(Qt.UserRole))
        else:
            self._selected_id = None
            self.detail.clear()
            self.stack.setCurrentIndex(0)

    def _on_project_selected(self, current, previous) -> None:  # noqa: ANN001 - Qt 回调
        if current is None:
            return
        selected_id = current.data(Qt.UserRole)
        for pid, card in self._cards.items():
            card.set_selected(pid == selected_id)
        self._selected_card = self._cards.get(selected_id)
        self._select_in_detail(selected_id)

    def _tick_card_glow(self) -> None:
        card = self._selected_card
        if card is None:
            return
        try:
            card.set_glow(glow_color())
        except RuntimeError:  # 卡片已被重建
            self._selected_card = None

    def _select_in_detail(self, project_id: str | None) -> None:
        if not project_id:
            return
        if self._selected_id and self._selected_id != project_id:
            self.detail.flush()
        self._selected_id = project_id
        self.detail.bind_project(project_id)
        self.stack.setCurrentIndex(1)

    # ---------------- 事件 ----------------

    def _on_detail_changed(self) -> None:
        self.refresh_all()

    def _on_project_deleted(self, project_id: str) -> None:
        self._selected_id = None
        self.stack.setCurrentIndex(0)
        self.refresh_all()

    def _focus_search(self) -> None:
        self.search_edit.setFocus()
        self.search_edit.selectAll()

    # ---------------- 操作 ----------------

    def new_project(self) -> None:
        dialog = ProjectDialog(self)
        if not dialog.exec():
            return
        values = dialog.values()
        project = self.repo.create_project(
            values["name"],
            path=values["path"],
            summary=values["summary"],
            status=values["status"],
            tags=values["tags"],
        )
        self._selected_id = project.id
        self.views_list.setCurrentRow(0)
        self.tags_list.setCurrentRow(0)
        self.refresh_all()

    def open_notes(self, note_id: str | None = None) -> None:
        if self.notes_window is None:
            self.notes_window = NotesWindow(self, self.repo, note_id)
        else:
            self.notes_window.refresh(note_id)
        self.notes_window.show()
        self.notes_window.raise_()
        self.notes_window.activateWindow()

    # ---------------- 文档库 ----------------

    def open_documents(self, folder: str | None = None) -> None:
        if self.doc_store is None:
            QMessageBox.information(self, "文档库", "文档存储没有初始化。")
            return
        if self.documents_window is None:
            self.documents_window = DocumentLibraryWindow(self, self.repo, self.doc_store)
            self.documents_window.changed.connect(self.refresh_all)
        if folder:
            self.documents_window._folder = folder  # noqa: SLF001 - 内部定位
        self.documents_window.refresh()
        self.documents_window.show()
        self.documents_window.raise_()
        self.documents_window.activateWindow()

    def _import_into_library(self, files: list[str]) -> None:
        """项目里拖进非图片文件时，转给文档库。"""
        if self.doc_store is None:
            return
        self.open_documents()
        self.documents_window.import_files(files)

    # ---------------- 搜索 / 活动流 / 回收站 / 恢复 ----------------

    def open_search(self) -> None:
        if self.search_dialog is None:
            self.search_dialog = GlobalSearchDialog(self, self.repo)
            self.search_dialog.opened.connect(self._on_search_result)
        self.search_dialog.popup()

    def _on_search_result(self, result: dict) -> None:
        if result.get("kind") == "note":
            self.open_notes(result["id"])
            return
        if result.get("kind") == "document":
            self.open_documents()
            self.documents_window.view_document(result["id"])
            return
        project_id = result.get("project_id") or (
            result["id"] if result.get("kind") == "project" else None
        )
        if project_id:
            self.focus_project(project_id)

    def _row_of_project(self, project_id: str) -> int:
        for index in range(self.project_list.count()):
            if self.project_list.item(index).data(Qt.UserRole) == project_id:
                return index
        return -1

    def focus_project(self, project_id: str) -> None:
        """选中某个项目；当前筛选里看不到就先清筛选。"""
        row = self._row_of_project(project_id)
        if row < 0:
            self.search_edit.clear()
            self.views_list.setCurrentRow(0)
            self.tags_list.setCurrentRow(0)
            self.refresh_projects()
            row = self._row_of_project(project_id)
        if row >= 0:
            self.project_list.setCurrentRow(row)
            self.show_window()

    def open_activity(self) -> None:
        if self.activity_window is None:
            self.activity_window = ActivityWindow(self, self.repo)
            self.activity_window.project_requested.connect(self.focus_project)
        self.activity_window.refresh()
        self.activity_window.show()
        self.activity_window.raise_()
        self.activity_window.activateWindow()

    def open_trash(self) -> None:
        if self.trash_dialog is None:
            self.trash_dialog = TrashDialog(self, self.repo, self.store, self.doc_store)
            self.trash_dialog.changed.connect(self.refresh_all)
        self.trash_dialog.refresh()
        self.trash_dialog.show()
        self.trash_dialog.raise_()
        self.trash_dialog.activateWindow()

    def open_restore(self) -> None:
        dialog = RestoreDialog(self)
        dialog.restore_requested.connect(self._do_restore)
        dialog.exec()

    def _do_restore(self, zip_path) -> None:  # noqa: ANN001
        try:
            self.repo.conn.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            safety = backup_mod.restore_snapshot(zip_path)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(
                self, "恢复失败", f"{exc}\n\n当前数据没有被改动。"
            )
            return
        QMessageBox.information(
            self,
            "恢复完成",
            f"已恢复。恢复前的数据放在：\n{safety}\n\n程序即将退出，请重新打开。",
        )
        self.prepare_quit()
        QApplication.quit()

    def _project_context_menu(self, pos) -> None:
        item = self.project_list.itemAt(pos)
        if item is None:
            return
        project = self.repo.get_project(item.data(Qt.UserRole))
        if project is None:
            return
        menu = QMenu(self)
        open_action = menu.addAction("打开项目文件夹")
        copy_action = menu.addAction("复制路径")
        menu.addSeparator()
        status_menu = menu.addMenu("修改状态")
        status_actions = {}
        for key in config.STATUS_ORDER:
            action = status_menu.addAction(config.STATUS_LABELS[key])
            status_actions[action] = key
        menu.addSeparator()
        archive_action = menu.addAction("移出归档" if project.status == "archived" else "归档")
        delete_action = menu.addAction("删除项目…")

        chosen = menu.exec(self.project_list.viewport().mapToGlobal(pos))
        if chosen is None:
            return
        if chosen == open_action:
            from ..core import paths as paths_mod

            exists, hint = paths_mod.folder_state(project.path)
            if not exists:
                QMessageBox.information(self, "打不开", f"文件夹{hint}：\n{project.path}")
            else:
                try:
                    paths_mod.open_in_explorer(project.path)
                except OSError as exc:
                    show_open_failure(self, project.path, exc)
        elif chosen == copy_action:
            QGuiApplication.clipboard().setText(project.path)
        elif chosen in status_actions:
            self.repo.set_status(project.id, status_actions[chosen])
            self.refresh_all()
        elif chosen == archive_action:
            new_status = "active" if project.status == "archived" else "archived"
            self.repo.set_status(project.id, new_status)
            self.refresh_all()
        elif chosen == delete_action:
            self._delete_project(project)

    def _delete_project(self, project: Project) -> None:
        confirm = QMessageBox.question(
            self, "删除项目",
            f"确定删除「{project.name}」？\n记录、截图会一起删除，无法恢复。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self.repo.delete_project(project.id)
        self.repo.prune_orphan_tags()
        self.store.remove_project(project.id)
        if self.doc_store is not None:
            self.doc_store.remove_project(project.id)
        if self._selected_id == project.id:
            self._selected_id = None
            self.detail.clear()
        self.refresh_all()

    def _show_app_menu(self) -> None:
        menu = QMenu(self)
        settings_action = menu.addAction("设置…")
        backup_action = menu.addAction("立即备份")
        restore_action = menu.addAction("从备份恢复…")
        menu.addSeparator()
        activity_action = menu.addAction("活动流…")
        documents_action = menu.addAction("文档库…")
        trash_action = menu.addAction("回收站…")
        menu.addSeparator()
        folder_action = menu.addAction("打开数据目录")
        menu.addSeparator()
        about_action = menu.addAction("关于")
        button = self.sender()
        anchor = button.mapToGlobal(button.rect().bottomLeft()) if button else self.mapToGlobal(self.rect().topLeft())
        chosen = menu.exec(anchor)
        if chosen == settings_action:
            self.open_settings()
        elif chosen == restore_action:
            self.open_restore()
        elif chosen == activity_action:
            self.open_activity()
        elif chosen == documents_action:
            self.open_documents()
        elif chosen == trash_action:
            self.open_trash()
        elif chosen == backup_action:
            self.run_backup()
        elif chosen == folder_action:
            import os

            os.startfile(str(config.DATA_DIR))  # noqa: S606
        elif chosen == about_action:
            self._show_about()

    def _show_about(self) -> None:
        shots = len(list(config.SHOT_DIR.rglob("*.*"))) if config.SHOT_DIR.is_dir() else 0
        size = 0
        if config.SHOT_DIR.is_dir():
            for path in config.SHOT_DIR.rglob("*"):
                if path.is_file():
                    size += path.stat().st_size
        QMessageBox.information(
            self, "关于",
            f"{config.APP_NAME} {config.APP_VERSION}\n\n"
            f"数据目录：{config.DATA_DIR}\n"
            f"截图：{shots} 个文件，{human_size(size)}\n"
            f"备份目录：{config.BACKUP_DIR}\n\n"
            "全部数据在本地，不联网。\n\n"
            "开源许可：MIT License",
        )

    def run_backup(self) -> None:
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            path = backup_mod.make_snapshot(min_interval_hours=0)
        except Exception as exc:  # noqa: BLE001 - 备份失败不该让程序崩
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "备份失败", str(exc))
            return
        QApplication.restoreOverrideCursor()
        if path is None:
            QMessageBox.information(self, "备份", "刚刚备份过了，这次跳过。")
        else:
            QMessageBox.information(self, "备份完成", f"已保存到：\n{path}")

    def start_background_backup(self) -> None:
        def worker() -> None:
            try:
                backup_mod.make_snapshot()
            except Exception:  # noqa: BLE001 - 后台任务静默失败
                pass

        threading.Thread(target=worker, daemon=True, name="savepoint-backup").start()

    # ---------------- 托盘与全局热键 ----------------

    def _tray_icon(self) -> QIcon:
        for name in ("app.ico", "app-256.png"):
            path = config.asset(name)
            if path.is_file():
                return QIcon(str(path))
        return QIcon()

    def _setup_tray(self) -> None:
        if self.tray is not None:
            return
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        if not config.get_bool("tray_enabled", True):
            return
        icon = self._tray_icon()
        if icon.isNull():
            return

        tray = QSystemTrayIcon(icon, self)
        tray.setToolTip(f"{config.APP_NAME} · {config.get_setting('hotkey')} 快速记录")
        menu = QMenu()
        menu.addAction("打开主窗口", self.show_window)
        menu.addAction("快速记录", self.quick_capture)
        menu.addAction("笔记", lambda: self.open_notes())
        menu.addSeparator()
        menu.addAction("立即备份", self.run_backup)
        menu.addAction("设置", self.open_settings)
        menu.addSeparator()
        menu.addAction("退出", self._quit_app)
        tray.setContextMenu(menu)
        tray.activated.connect(self._on_tray_activated)
        tray.show()
        self.tray = tray

    def _on_tray_activated(self, reason) -> None:  # noqa: ANN001 - Qt 回调
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self.show_window()

    def show_window(self) -> None:
        """从托盘/最小化状态把窗口叫回来，并尽量拿到前台焦点。"""
        if self.isMinimized():
            self.setWindowState(
                (self.windowState() & ~Qt.WindowState.WindowMinimized)
                | Qt.WindowState.WindowActive
            )
        self.show()
        self.raise_()
        self.activateWindow()
        try:
            import ctypes

            ctypes.windll.user32.SetForegroundWindow(int(self.winId()))
        except Exception:  # noqa: BLE001 - 拿不到焦点也不算失败
            pass

    def _setup_hotkey(self) -> None:
        if self.hotkey is not None:
            return
        spec = config.get_setting("hotkey") or "Ctrl+Alt+N"
        hotkey = GlobalHotkey(self.quick_capture)
        if hotkey.register(spec):
            self.hotkey = hotkey
        else:
            logging.getLogger("savepoint").warning("全局热键注册失败：%s（可能被其他程序占用）", spec)

    def _reload_hotkey(self) -> None:
        if self.hotkey is not None:
            self.hotkey.unregister()
            self.hotkey = None
        self._setup_hotkey()

    def quick_capture(self) -> None:
        if self.capture_dialog is None:
            self.capture_dialog = QuickCaptureDialog(self, self.repo)
            self.capture_dialog.saved.connect(self._on_capture_saved)
        self.capture_dialog.popup()

    def _on_capture_saved(self, project_id: str, body: str) -> None:  # noqa: ARG002
        self.refresh_projects()
        if self.stack.currentIndex() == 1 and self.detail.current_project_id() == project_id:
            self.detail.refresh()
        if self.tray is not None:
            project = self.repo.get_project(project_id)
            name = project.name if project else "项目"
            self.tray.showMessage(
                config.APP_NAME,
                f"已记到「{name}」",
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )

    def open_settings(self) -> None:
        dialog = SettingsDialog(self)
        dialog.changed.connect(self._on_settings_changed)
        dialog.exec()

    def _on_settings_changed(self) -> None:
        self._refresh_tray_visibility()
        self._reload_hotkey()

    def _refresh_tray_visibility(self) -> None:
        want = config.get_bool("tray_enabled", True) and QSystemTrayIcon.isSystemTrayAvailable()
        if want and self.tray is None:
            self._setup_tray()
        elif not want and self.tray is not None:
            self.tray.hide()
            self.tray.setParent(None)
            self.tray = None

    def prepare_quit(self) -> None:
        """退出前释放全局资源。"""
        self._force_quit = True
        if self.hotkey is not None:
            self.hotkey.unregister()
            self.hotkey = None
        if self.tray is not None:
            self.tray.hide()

    def _quit_app(self) -> None:
        self.prepare_quit()
        QApplication.quit()

    # ---------------- 窗口状态 ----------------

    def _state_path(self) -> Path:
        return config.DATA_DIR / STATE_FILE_NAME

    def _restore_state(self) -> None:
        path = self._state_path()
        if not path.is_file():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        geometry = data.get("geometry")
        if isinstance(geometry, list) and len(geometry) == 4:
            try:
                rect = QRect(*(int(value) for value in geometry))
            except (TypeError, ValueError):
                rect = None
            if rect is not None and self._title_reachable(rect):
                self.setGeometry(rect)
            else:
                self._place_in_view()
        self._selected_id = data.get("selected_id")

    @staticmethod
    def _title_reachable(rect: QRect) -> bool:
        """标题栏得落在某块屏幕的可用区域里，否则窗口拖不动。"""
        for screen in QGuiApplication.screens():
            area = screen.availableGeometry()
            if rect.y() < area.y():
                continue
            if rect.y() > area.bottom() - 100:
                continue
            overlap = min(rect.right(), area.right()) - max(rect.left(), area.left())
            if overlap >= 200:
                return True
        return False

    def _place_in_view(self) -> None:
        """把窗口摆到主屏中央，尺寸不超过屏幕。"""
        screen = QGuiApplication.primaryScreen()
        area = screen.availableGeometry() if screen is not None else QRect(0, 0, 1280, 800)
        width = min(1180, max(900, area.width() - 120))
        height = min(760, max(600, area.height() - 120))
        self.resize(width, height)
        self.move(
            area.x() + (area.width() - width) // 2,
            area.y() + (area.height() - height) // 2,
        )

    def _save_state(self) -> None:
        # 只在窗口位于可见区域时保存，避免把跑偏的坐标存下来
        if not self.isVisible() or not self._title_reachable(self.geometry()):
            return
        try:
            self._state_path().write_text(
                json.dumps(
                    {
                        "geometry": [self.x(), self.y(), self.width(), self.height()],
                        "selected_id": self._selected_id,
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self.detail.flush()
        self._save_state()

        keep_in_tray = (
            not self._force_quit
            and self.tray is not None
            and self.tray.isVisible()
            and config.get_bool("close_to_tray", True)
        )
        if keep_in_tray:
            event.ignore()
            self.hide()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                hotkey = config.get_setting("hotkey")
                self.tray.showMessage(
                    config.APP_NAME,
                    f"已最小化到托盘。右键图标可退出，{hotkey} 随时记录。",
                    QSystemTrayIcon.MessageIcon.Information,
                    4000,
                )
            return

        if self.hotkey is not None:
            self.hotkey.unregister()
            self.hotkey = None
        if self.tray is not None:
            self.tray.hide()
        super().closeEvent(event)
        QApplication.quit()