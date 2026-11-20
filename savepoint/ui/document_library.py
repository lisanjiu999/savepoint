"""文档库窗口：把散落在桌面的文件收进来。

左侧分区，右侧文档列表；拖文件进窗口即可导入，导入前会先读正文给用户看。
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .. import config
from ..core import paths
from ..core.documents import DocStore, DocumentError, extract_text, is_document, kind_of
from .document_dialog import DocumentImportDialog, DocumentViewer, kind_color
from .icons import folder_icon, note_icon
from .selection import GlowDelegate, ensure_animating

DEFAULT_FOLDER = "未分类"


class DocumentLibraryWindow(QWidget):
    changed = Signal()

    def __init__(self, parent: QWidget | None, repo, doc_store: DocStore) -> None:
        super().__init__(parent, Qt.Window)
        self.repo = repo
        self.doc_store = doc_store
        self._folder: str | None = None
        self._type: str | None = None
        self._current_id: str | None = None

        self.setWindowTitle(f"{config.APP_NAME} · 文档库")
        self.resize(1000, 680)
        self.setAcceptDrops(True)

        self._build()
        self.refresh()

    # ---------------- 构建 ----------------

    def _build(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 12, 14, 12)
        root.setSpacing(8)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.search_edit = QLineEdit()
        self.search_edit.setObjectName("SearchBox")
        self.search_edit.setPlaceholderText("搜索文件名 / 正文…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(lambda _: self._reload_docs())
        top.addWidget(self.search_edit, 1)

        import_btn = QPushButton("导入文件…")
        import_btn.setObjectName("Primary")
        import_btn.clicked.connect(self.pick_files)
        top.addWidget(import_btn)
        root.addLayout(top)

        body = QHBoxLayout()
        body.setSpacing(12)
        root.addLayout(body, 1)

        # 左：分区
        left = QVBoxLayout()
        left.setSpacing(6)
        hint = QLabel("按类型")
        hint.setObjectName("SectionTitle")
        left.addWidget(hint)

        self.type_list = QListWidget()
        self.type_list.setFixedWidth(190)
        self.type_list.setItemDelegate(GlowDelegate(self.type_list))
        ensure_animating(self.type_list)
        self.type_list.currentItemChanged.connect(self._on_type_changed)
        left.addWidget(self.type_list)

        folder_hint = QLabel("分区")
        folder_hint.setObjectName("SectionTitle")
        left.addWidget(folder_hint)

        self.folder_tree = QTreeWidget()
        self.folder_tree.setHeaderHidden(True)
        self.folder_tree.setFixedWidth(190)
        self.folder_tree.setIconSize(QSize(36, 18))
        self.folder_tree.setRootIsDecorated(False)
        self.folder_tree.setItemDelegate(GlowDelegate(self.folder_tree))
        ensure_animating(self.folder_tree)
        self.folder_tree.itemClicked.connect(self._on_folder_clicked)
        self.folder_tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.folder_tree.customContextMenuRequested.connect(self._on_folder_menu)
        left.addWidget(self.folder_tree, 1)
        body.addLayout(left)

        # 右：文档列表
        right = QVBoxLayout()
        right.setSpacing(6)
        self.count_label = QLabel("")
        self.count_label.setObjectName("Muted")
        right.addWidget(self.count_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        holder = QWidget()
        self.docs_layout = QVBoxLayout(holder)
        self.docs_layout.setContentsMargins(0, 0, 0, 0)
        self.docs_layout.setSpacing(8)
        self.docs_layout.addStretch(1)
        scroll.setWidget(holder)
        right.addWidget(scroll, 1)

        self.drop_hint = QLabel("把文件拖进这个窗口即可导入")
        self.drop_hint.setObjectName("Muted")
        self.drop_hint.setAlignment(Qt.AlignCenter)
        right.addWidget(self.drop_hint)
        body.addLayout(right, 1)

    # ---------------- 数据 ----------------

    def refresh(self) -> None:
        self._reload_types()
        self._reload_folders()
        self._reload_docs()

    def _reload_types(self) -> None:
        self.type_list.blockSignals(True)
        self.type_list.clear()

        total = self.repo.count_documents()
        all_item = QListWidgetItem(f"全部文档　{total}")
        all_item.setData(Qt.UserRole, None)
        self.type_list.addItem(all_item)

        for name, count in self.repo.document_types():
            item = QListWidgetItem(f"{name}　{count}")
            item.setData(Qt.UserRole, name)
            self.type_list.addItem(item)

        target = 0
        for index in range(self.type_list.count()):
            if self.type_list.item(index).data(Qt.UserRole) == self._type:
                target = index
                break
        self.type_list.setCurrentRow(target)
        self.type_list.blockSignals(False)

    def _on_type_changed(self, current, previous) -> None:  # noqa: ANN001 - Qt 回调
        if current is None:
            return
        self._type = current.data(Qt.UserRole)
        # 类型和分区可以叠加：类型决定看哪些格式，分区决定看哪一块
        self._reload_folders()
        self._reload_docs()

    def _type_suffixes(self) -> list[str] | None:
        if self._type is None:
            return None
        from ..core.documents import suffixes_of_group

        return suffixes_of_group(self._type)

    def _reload_folders(self) -> None:
        # 记住哪些分区是展开的，重建后恢复
        expanded: set[str] = set()
        for index in range(self.folder_tree.topLevelItemCount()):
            node = self.folder_tree.topLevelItem(index)
            data = node.data(0, Qt.UserRole)
            if isinstance(data, tuple) and data[0] == "folder" and node.isExpanded():
                expanded.add(data[1])

        suffixes = self._type_suffixes()
        visible = self.repo.list_documents(suffixes=suffixes)

        self.folder_tree.blockSignals(True)
        self.folder_tree.clear()

        all_item = QTreeWidgetItem([f"全部分区　{len(visible)}"])
        all_item.setIcon(0, folder_icon("全部分区", True, dark=False))
        all_item.setData(0, Qt.UserRole, ("all", None))
        self.folder_tree.addTopLevelItem(all_item)

        by_folder: dict[str, list] = {}
        for doc in visible:
            by_folder.setdefault(doc.folder, []).append(doc)

        for name, _count in self.repo.document_folders():
            docs = by_folder.get(name, [])
            node = QTreeWidgetItem([f"{name}　{len(docs)}"])
            node.setIcon(0, folder_icon(name, True, dark=False))
            node.setData(0, Qt.UserRole, ("folder", name))
            font = node.font(0)
            font.setBold(True)
            node.setFont(0, font)
            for doc in docs:
                child = QTreeWidgetItem([doc.orig_name])
                child.setIcon(0, note_icon(doc.orig_name))
                child.setData(0, Qt.UserRole, ("doc", doc.id))
                child.setToolTip(0, f"{paths.human_size(doc.size)} · "
                                    f"{paths.human_time(doc.created_at)}")
                node.addChild(child)
            self.folder_tree.addTopLevelItem(node)
            node.setExpanded(name in expanded or name == self._folder)

        target = 0
        for index in range(self.folder_tree.topLevelItemCount()):
            data = self.folder_tree.topLevelItem(index).data(0, Qt.UserRole)
            if isinstance(data, tuple) and data[1] == self._folder:
                target = index
                break
        self.folder_tree.setCurrentItem(self.folder_tree.topLevelItem(target))
        self.folder_tree.blockSignals(False)

    def _reload_docs(self) -> None:
        while self.docs_layout.count() > 1:
            item = self.docs_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        suffixes = None
        if self._type is not None:
            from ..core.documents import suffixes_of_group

            suffixes = suffixes_of_group(self._type)

        docs = self.repo.list_documents(
            folder=self._folder,
            query=self.search_edit.text().strip() or None,
            suffixes=suffixes,
        )
        for doc in docs:
            self.docs_layout.insertWidget(self.docs_layout.count() - 1, self._card(doc))

        scope = self._type or self._folder or "全部"
        self.count_label.setText(f"{scope} · {len(docs)} 份文档")
        self.drop_hint.setVisible(not docs)

    def _card(self, doc) -> QWidget:
        card = QFrame()
        card.setObjectName("EntryCard")
        row = QHBoxLayout(card)
        row.setContentsMargins(12, 9, 12, 9)
        row.setSpacing(12)

        kind = kind_of(doc.ext)
        color = kind_color(kind)
        badge = QLabel(kind)
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedWidth(56)
        badge.setStyleSheet(
            f"color:{color}; border:1px solid {color}55; background:{color}14;"
            " border-radius:5px; padding:3px 0; font-size:8.5pt; font-weight:600;"
        )
        row.addWidget(badge)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        name = QLabel(doc.orig_name)
        name.setStyleSheet("font-weight:600;")
        name.setWordWrap(True)
        text_box.addWidget(name)

        bits = [doc.folder, paths.human_size(doc.size)]
        bits.append(f"{len(doc.text_content)} 字" if doc.text_content else "无文本")
        bits.append(paths.human_time(doc.created_at))
        meta = QLabel(" · ".join(bits))
        meta.setObjectName("Muted")
        text_box.addWidget(meta)
        row.addLayout(text_box, 1)

        view_btn = QPushButton("查看")
        view_btn.setObjectName("Link")
        view_btn.clicked.connect(lambda _=False, d=doc.id: self.view_document(d))
        row.addWidget(view_btn)

        del_btn = QPushButton("删除")
        del_btn.setObjectName("Link")
        del_btn.setStyleSheet("color:#c0392b; font-size:9pt;")
        del_btn.clicked.connect(lambda _=False, d=doc.id: self.delete_document(d))
        row.addWidget(del_btn)
        return card

    # ---------------- 分区 ----------------

    def _on_folder_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        data = item.data(0, Qt.UserRole)
        if not isinstance(data, tuple):
            return
        kind, value = data
        if kind == "doc":
            # 点文档名直接打开
            self.view_document(value)
            return
        # 点分区：右侧切到这个分区，同时展开
        self._folder = value
        item.setExpanded(True)
        self._reload_folders()
        self._reload_docs()

    def _on_folder_menu(self, pos) -> None:  # noqa: ANN001 - Qt 回调
        item = self.folder_tree.itemAt(pos)
        data = item.data(0, Qt.UserRole) if item is not None else None
        kind, folder = ("", None)
        if isinstance(data, tuple):
            kind, folder = data

        menu = QMenu(self)
        if kind == "doc":
            doc_id = folder
            menu.addAction("打开", lambda: self.view_document(doc_id))
            menu.addSeparator()
            menu.addAction("删除文档…", lambda: self.delete_document(doc_id))
        elif kind == "folder":
            menu.addAction("导入文件到此分区…", lambda: self.pick_files(folder))
            menu.addAction("重命名分区…", lambda: self.rename_folder(folder))
            menu.addSeparator()
            menu.addAction("删除分区…", lambda: self.delete_folder(folder))
            menu.addSeparator()
            menu.addAction("新建分区…", self.create_folder)
        else:
            menu.addAction("新建分区…", self.create_folder)
        menu.exec(self.folder_tree.viewport().mapToGlobal(pos))

    def _prompt(self, title: str, label: str, default: str = "") -> str | None:
        from .dialogs import TextPromptDialog

        dialog = TextPromptDialog(self, title, label, default)
        if not dialog.exec():
            return None
        return dialog.value() or None

    def create_folder(self) -> None:
        name = self._prompt("新建分区", "给分区起个名字，例如：合同 / 报表 / 学习资料")
        if not name:
            return
        saved = self.repo.create_document_folder(name)
        if not saved:
            return
        self._folder = saved
        self._reload_folders()
        self._reload_docs()
        self.changed.emit()

    def rename_folder(self, folder: str) -> None:
        name = self._prompt("重命名分区", "新的分区名", folder)
        if not name or name == folder:
            return
        self.repo.rename_document_folder(folder, name)
        if self._folder == folder:
            self._folder = name
        self.refresh()
        self.changed.emit()

    def delete_folder(self, folder: str) -> None:
        count = dict(self.repo.document_folders()).get(folder, 0)
        if count:
            question = (
                f"「{folder}」里有 {count} 份文档，全部移进回收站？\n30 天内可以恢复。"
            )
        else:
            question = f"「{folder}」是空分区，确定删除？"
        confirm = QMessageBox.question(
            self, "删除分区", question,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self.repo.delete_document_folder(folder)
        if self._folder == folder:
            self._folder = None
        self.refresh()
        self.changed.emit()

    # ---------------- 导入 ----------------

    def pick_files(self, folder: str | None = None) -> None:
        dialog = QFileDialog(self, "选择要收纳的文件")
        dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        dialog.setNameFilter(
            "支持的文件 (*.pdf *.docx *.doc *.xlsx *.xls *.pptx *.ppt "
            "*.txt *.md *.csv *.json *.log *.xml *.yml *.yaml *.py *.js *.html);;所有文件 (*.*)"
        )
        if not dialog.exec():
            return
        self.import_files(dialog.selectedFiles(), folder)

    def import_files(self, files: list[str], folder: str | None = None) -> int:
        target_folder = (folder or self._folder or DEFAULT_FOLDER).strip() or DEFAULT_FOLDER
        added = 0
        skipped: list[str] = []

        for text in files:
            path = Path(text)
            if not path.is_file():
                continue
            if not is_document(path):
                skipped.append(path.name)
                continue

            try:
                data = path.read_bytes()
            except OSError as exc:
                QMessageBox.warning(self, "读取失败", f"{path.name}\n{exc}")
                continue

            from ..core.documents import sha256_of

            digest = sha256_of(data)
            existing = self.repo.find_document_by_hash(digest)
            if existing is not None:
                QMessageBox.information(
                    self, "已经有了",
                    f"「{path.name}」和文档库里的「{existing.orig_name}」内容相同，跳过。",
                )
                continue

            body, warning = extract_text(path)
            dialog = DocumentImportDialog(
                self,
                name=path.name,
                kind=kind_of(path.suffix),
                size=len(data),
                text=body,
                warning=warning,
            )
            if not dialog.exec():
                continue
            if dialog.choice() == DocumentImportDialog.READ_ONLY:
                if body:
                    QGuiApplication.clipboard().setText(body)
                    QMessageBox.information(
                        self, "已复制", "正文已复制到剪贴板，没有保存文件。"
                    )
                continue

            try:
                rel, size, digest = self.doc_store.save(path)
            except DocumentError as exc:
                QMessageBox.warning(self, "保存失败", f"{path.name}\n{exc}")
                continue
            self.repo.add_document(
                rel_path=rel,
                orig_name=path.name,
                ext=path.suffix.lower(),
                size=size,
                sha256=digest,
                text_content=body,
                folder=target_folder,
            )
            added += 1

        if skipped:
            preview = "、".join(skipped[:5])
            more = f" 等 {len(skipped)} 个" if len(skipped) > 5 else ""
            QMessageBox.information(
                self, "这些类型还不支持",
                f"{preview}{more} 没能导入。\n\n"
                "目前支持：PDF、Word、Excel、PPT，以及常见文本文件。",
            )
        if added:
            self.refresh()
            self.changed.emit()
        return added

    # ---------------- 拖拽 ----------------

    def dragEnterEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.drop_hint.setText("松手导入")

    def dragLeaveEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self.drop_hint.setText("把文件拖进这个窗口即可导入")

    def dropEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        self.drop_hint.setText("把文件拖进这个窗口即可导入")
        files = [
            url.toLocalFile()
            for url in event.mimeData().urls()
            if url.isLocalFile() and url.toLocalFile()
        ]
        if files:
            self.import_files(files)
            event.acceptProposedAction()

    # ---------------- 单条操作 ----------------

    def view_document(self, doc_id: str) -> None:
        doc = self.repo.get_document(doc_id)
        if doc is None:
            return
        viewer = DocumentViewer(self, doc, self.doc_store.abs_path(doc.rel_path))
        viewer.setAttribute(Qt.WA_DeleteOnClose, True)
        viewer.show()
        viewer.raise_()
        viewer.activateWindow()

    def delete_document(self, doc_id: str) -> None:
        doc = self.repo.get_document(doc_id)
        if doc is None:
            return
        confirm = QMessageBox.question(
            self, "删除文档",
            f"确定删除「{doc.orig_name}」？\n会进回收站，30 天内可恢复。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        self.repo.delete_document(doc_id)
        self.refresh()
        self.changed.emit()