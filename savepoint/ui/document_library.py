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
from .icons import folder_icon
from .selection import GlowDelegate, ensure_animating

DEFAULT_FOLDER = "未分类"


class DocumentLibraryWindow(QWidget):
    changed = Signal()

    def __init__(self, parent: QWidget | None, repo, doc_store: DocStore) -> None:
        super().__init__(parent, Qt.Window)
        self.repo = repo
        self.doc_store = doc_store
        self._folder: str | None = None
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
        hint = QLabel("分区")
        hint.setObjectName("SectionTitle")
        left.addWidget(hint)
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
        self._reload_folders()
        self._reload_docs()

    def _reload_folders(self) -> None:
        self.folder_tree.blockSignals(True)
        self.folder_tree.clear()

        total = self.repo.count_documents()
        all_item = QTreeWidgetItem([f"全部文档　{total}"])
        all_item.setIcon(0, folder_icon("全部文档", True, dark=False))
        all_item.setData(0, Qt.UserRole, None)
        self.folder_tree.addTopLevelItem(all_item)

        for name, count in self.repo.document_folders():
            item = QTreeWidgetItem([f"{name}　{count}"])
            item.setIcon(0, folder_icon(name, True, dark=False))
            item.setData(0, Qt.UserRole, name)
            self.folder_tree.addTopLevelItem(item)

        target = 0
        for index in range(self.folder_tree.topLevelItemCount()):
            if self.folder_tree.topLevelItem(index).data(0, Qt.UserRole) == self._folder:
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

        docs = self.repo.list_documents(
            folder=self._folder,
            query=self.search_edit.text().strip() or None,
        )
        for doc in docs:
            self.docs_layout.insertWidget(self.docs_layout.count() - 1, self._card(doc))

        scope = self._folder or "全部"
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
        self._folder = item.data(0, Qt.UserRole)
        self._reload_folders()
        self._reload_docs()

    def _on_folder_menu(self, pos) -> None:  # noqa: ANN001 - Qt 回调
        item = self.folder_tree.itemAt(pos)
        if item is None:
            return
        folder = item.data(0, Qt.UserRole)
        menu = QMenu(self)
        if folder is None:
            menu.addAction("新建分区…", self.create_folder)
        else:
            menu.addAction("导入文件到此分区…", lambda: self.pick_files(folder))
            menu.addAction("重命名分区…", lambda: self.rename_folder(folder))
            menu.addSeparator()
            menu.addAction("删除分区…", lambda: self.delete_folder(folder))
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
        self._folder = name
        self._reload_folders()
        self._reload_docs()

    def rename_folder(self, folder: str) -> None:
        name = self._prompt("重命名分区", "新的分区名", folder)
        if not name or name == folder:
            return
        self.repo.rename_document_folder(folder, name)
        if self._folder == folder:
            self._folder = name
        self.refresh()

    def delete_folder(self, folder: str) -> None:
        count = dict(self.repo.document_folders()).get(folder, 0)
        if not count:
            return
        confirm = QMessageBox.question(
            self, "删除分区",
            f"「{folder}」里有 {count} 份文档，全部移进回收站？\n30 天内可以恢复。",
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