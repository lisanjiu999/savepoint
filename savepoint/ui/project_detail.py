"""项目详情页：基本信息、备注、追加式记录、截图时间线。"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt, QTimer, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from .. import config
from ..core import paths
from ..core.repo import Project
from ..core.storage import ScreenshotError
from .dialogs import EntryEditDialog, ImageViewer, ProjectDialog, show_open_failure
from .style import STATUS_COLORS
from .timeline import DropZone, ScreenshotCard


def _clear_layout(layout) -> None:
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout() is not None:
            _clear_layout(item.layout())


def _section_header(title: str, hint: str = "") -> QWidget:
    box = QWidget()
    column = QVBoxLayout(box)
    column.setContentsMargins(0, 10, 0, 6)
    column.setSpacing(6)

    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(8)
    label = QLabel(title)
    label.setObjectName("SectionTitle")
    row.addWidget(label)
    if hint:
        hint_label = QLabel(hint)
        hint_label.setObjectName("Muted")
        row.addWidget(hint_label)
    row.addStretch(1)
    column.addLayout(row)

    divider = QFrame()
    divider.setObjectName("Divider")
    divider.setFixedHeight(1)
    column.addWidget(divider)
    return box


class ProjectDetail(QWidget):
    changed = Signal()
    deleted = Signal(str)

    def __init__(self, repo, store, doc_store=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.repo = repo
        self.store = store
        self.doc_store = doc_store
        self._project: Project | None = None
        self._loading = False
        self._overlay = None
        self._capture_restore = True

        self._notes_timer = QTimer(self)
        self._notes_timer.setSingleShot(True)
        self._notes_timer.setInterval(600)
        self._notes_timer.timeout.connect(self._save_notes)

        self._build()

    # ---------------- 构建 ----------------

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        outer.addWidget(scroll)

        content = QWidget()
        content.setObjectName("Root")
        self.content_layout = QVBoxLayout(content)
        self.content_layout.setContentsMargins(28, 22, 28, 40)
        self.content_layout.setSpacing(14)
        scroll.setWidget(content)

        # 标题行
        head = QHBoxLayout()
        head.setSpacing(10)
        self.title_label = QLabel()
        self.title_label.setObjectName("CardTitle")
        self.title_label.setStyleSheet("font-size:17pt; font-weight:600;")
        head.addWidget(self.title_label)
        self.status_pill = QLabel()
        self.status_pill.setObjectName("StatusPill")
        head.addWidget(self.status_pill, 0, Qt.AlignVCenter)
        head.addStretch(1)

        self.more_btn = QPushButton("⋯")
        self.more_btn.setFixedWidth(38)
        self.more_btn.setToolTip("更多操作")
        self.more_btn.clicked.connect(self._show_menu)
        head.addWidget(self.more_btn)
        self.content_layout.addLayout(head)

        # 元信息 + 标签
        self.meta_label = QLabel()
        self.meta_label.setObjectName("Muted")
        self.content_layout.addWidget(self.meta_label)

        self.tags_row = QHBoxLayout()
        self.tags_row.setSpacing(6)
        self.tags_row.setContentsMargins(0, 2, 0, 0)
        self.content_layout.addLayout(self.tags_row)

        # 路径 + 打开 + 状态
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self.path_label = QLabel()
        self.path_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.path_label.setWordWrap(True)
        path_row.addWidget(self.path_label, 1)
        self.open_btn = QPushButton("打开文件夹")
        self.open_btn.clicked.connect(self._open_folder)
        path_row.addWidget(self.open_btn)

        self.status_combo = QComboBox()
        self.status_combo.setFixedWidth(98)
        for key in config.STATUS_ORDER:
            self.status_combo.addItem(config.STATUS_LABELS[key], key)
        self.status_combo.setToolTip("修改项目状态")
        self.status_combo.currentIndexChanged.connect(self._on_status_changed)
        path_row.addWidget(self.status_combo)
        self.content_layout.addLayout(path_row)

        # 描述与下一步
        form_row = QHBoxLayout()
        form_row.setSpacing(14)
        left = QVBoxLayout()
        left.setSpacing(4)
        left.addWidget(_section_header("一句话描述"))
        self.summary_edit = QLineEdit()
        self.summary_edit.setPlaceholderText("30 字内，三个月后的自己能看懂就行")
        self.summary_edit.editingFinished.connect(self._save_summary)
        left.addWidget(self.summary_edit)
        right = QVBoxLayout()
        right.setSpacing(4)
        right.addWidget(_section_header("下一步"))
        self.next_edit = QLineEdit()
        self.next_edit.setPlaceholderText("下次打开时要做什么")
        self.next_edit.editingFinished.connect(self._save_next)
        right.addWidget(self.next_edit)
        form_row.addLayout(left, 1)
        form_row.addLayout(right, 1)
        self.content_layout.addLayout(form_row)

        # 备注
        self.content_layout.addWidget(_section_header("备注", "自动保存"))
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText(
            "思路、踩过的坑、参考链接…\n纯文本记录，随手写，失焦自动保存。"
        )
        self.notes_edit.setMinimumHeight(130)
        self.notes_edit.textChanged.connect(self._on_notes_changed)
        self.content_layout.addWidget(self.notes_edit)

        # 记录（追加式）
        self.content_layout.addWidget(_section_header("记录", "按时间倒序，只追加不改写"))
        entry_row = QHBoxLayout()
        entry_row.setSpacing(8)
        self.entry_input = QLineEdit()
        self.entry_input.setPlaceholderText(
            "顺手记一笔：今天做了什么 / 卡在哪 / 想到了什么…（回车添加）"
        )
        self.entry_input.returnPressed.connect(self._add_entry)
        entry_row.addWidget(self.entry_input, 1)
        add_btn = QPushButton("添加")
        add_btn.setObjectName("Primary")
        add_btn.clicked.connect(self._add_entry)
        entry_row.addWidget(add_btn)
        self.content_layout.addLayout(entry_row)

        self.entries_layout = QVBoxLayout()
        self.entries_layout.setSpacing(6)
        self.content_layout.addLayout(self.entries_layout)

        # 文档
        self.content_layout.addWidget(
            _section_header("文档", "Word / PDF / Excel / PPT 拖进来就能读")
        )
        self.docs_layout = QVBoxLayout()
        self.docs_layout.setSpacing(8)
        self.content_layout.addLayout(self.docs_layout)

        # 截图
        self.content_layout.addWidget(
            _section_header("截图时间线", "拖进来、截一张、或粘贴，自动带时间")
        )
        self.drop_zone = DropZone()
        self.drop_zone.files_dropped.connect(self._add_files)
        self.drop_zone.paste_requested.connect(self._paste_image)
        self.drop_zone.capture_requested.connect(self._start_capture)
        self.content_layout.addWidget(self.drop_zone)

        self.shots_layout = QVBoxLayout()
        self.shots_layout.setSpacing(10)
        self.content_layout.addLayout(self.shots_layout)
        self.content_layout.addStretch(1)

    # ---------------- 绑定 ----------------

    def current_project_id(self) -> str | None:
        return self._project.id if self._project else None

    def flush(self) -> None:
        """切走前把未落盘的备注写回。"""
        if self._notes_timer.isActive():
            self._notes_timer.stop()
            self._save_notes()

    def bind_project(self, project_id: str) -> None:
        project = self.repo.get_project(project_id)
        if project is None:
            self.clear()
            return
        if self._project and self._project.id != project.id:
            self.flush()
        self._project = project
        self._loading = True
        try:
            self.title_label.setText(project.name)
            self._apply_status_pill(project.status)
            index = self.status_combo.findData(project.status)
            if index >= 0:
                self.status_combo.setCurrentIndex(index)
            self._render_tags(project.tags)

            shots = self.repo.list_screenshots(project.id)
            entries = self.repo.list_entries(project.id)
            docs = self.repo.list_documents(project.id)
            self.meta_label.setText(
                f"最后更新 {paths.relative_time(project.updated_at)}"
                f" · {len(entries)} 条记录 · {len(shots)} 张截图 · {len(docs)} 份文档"
                f" · 创建于 {paths.human_time(project.created_at, with_year=True)}"
            )
            self._refresh_path()
            self.summary_edit.setText(project.summary)
            self.next_edit.setText(project.next_step)
            self.notes_edit.setPlainText(project.notes)
            self._render_entries(entries)
            self._render_documents(docs)
            self._render_shots(shots)
        finally:
            self._loading = False

    def refresh(self) -> None:
        if self._project:
            self.bind_project(self._project.id)

    def clear(self) -> None:
        self._project = None
        self.title_label.setText("")
        self.status_pill.setText("")
        self.meta_label.setText("")
        self.path_label.setText("")
        self.notes_edit.setPlainText("")
        self.summary_edit.setText("")
        self.next_edit.setText("")
        _clear_layout(self.entries_layout)
        _clear_layout(self.docs_layout)
        _clear_layout(self.shots_layout)

    # ---------------- 状态 ----------------

    def _apply_status_pill(self, status: str) -> None:
        label = config.STATUS_LABELS.get(status, status)
        color = STATUS_COLORS.get(status, "#9ca3af")
        self.status_pill.setText(label)
        self.status_pill.setStyleSheet(
            f"background:{color}1a; color:{color}; border:1px solid {color}55;"
            " border-radius:9px; padding:2px 10px; font-size:9pt; font-weight:600;"
        )

    def _render_tags(self, tags: list[str]) -> None:
        # 连同 stretch 一起清干净，否则重复绑定时旧标签会残留在原位
        while self.tags_row.count():
            item = self.tags_row.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        for tag in tags:
            chip = QLabel(f"#{tag}")
            chip.setObjectName("TagChip")
            self.tags_row.addWidget(chip)
        self.tags_row.addStretch(1)

    def _on_status_changed(self, _index: int) -> None:
        if self._loading or not self._project:
            return
        status = self.status_combo.currentData()
        if not status or status == self._project.status:
            return
        self.repo.set_status(self._project.id, status)
        self._project.status = status
        self._apply_status_pill(status)
        self.changed.emit()

    # ---------------- 路径 ----------------

    def _refresh_path(self) -> None:
        assert self._project is not None
        exists, hint = paths.folder_state(self._project.path)
        if not self._project.path.strip():
            self.path_label.setText("未设置项目路径")
            self.path_label.setStyleSheet("color:#9ca3af;")
            self.open_btn.setEnabled(False)
        elif exists:
            self.path_label.setText(f"📁 {self._project.path}")
            self.path_label.setStyleSheet("")
            self.open_btn.setEnabled(True)
        else:
            self.path_label.setText(f"📁 {self._project.path}　（{hint}）")
            self.path_label.setStyleSheet("color:#d97706;")
            self.open_btn.setEnabled(False)

    def _open_folder(self) -> None:
        if not self._project or not self._project.path.strip():
            return
        exists, hint = paths.folder_state(self._project.path)
        if not exists:
            QMessageBox.warning(self, "打不开", f"文件夹{hint}：\n{self._project.path}")
            return
        try:
            paths.open_in_explorer(self._project.path)
        except OSError as exc:
            show_open_failure(self, self._project.path, exc)

    # ---------------- 保存 ----------------

    def _save_summary(self) -> None:
        if self._loading or not self._project:
            return
        text = self.summary_edit.text().strip()
        if text != self._project.summary:
            self.repo.update_project(self._project.id, summary=text)
            self._project.summary = text
            self.changed.emit()

    def _save_next(self) -> None:
        if self._loading or not self._project:
            return
        text = self.next_edit.text().strip()
        if text != self._project.next_step:
            self.repo.update_project(self._project.id, next_step=text)
            self._project.next_step = text
            self.changed.emit()

    def _on_notes_changed(self) -> None:
        if self._loading or not self._project:
            return
        self._notes_timer.start()

    def _save_notes(self) -> None:
        if not self._project:
            return
        text = self.notes_edit.toPlainText()
        if text != self._project.notes:
            self.repo.update_project(self._project.id, notes=text)
            self._project.notes = text
            self.changed.emit()

    # ---------------- 记录 ----------------

    def _add_entry(self) -> None:
        if not self._project:
            return
        text = self.entry_input.text().strip()
        if not text:
            return
        self.repo.add_entry(self._project.id, text)
        self.entry_input.clear()
        self._render_entries(self.repo.list_entries(self._project.id))
        self._update_meta()
        self.changed.emit()

    def _render_entries(self, entries) -> None:
        _clear_layout(self.entries_layout)
        if not entries:
            empty = QLabel("还没有记录。从今天开始随手记，三个月后就是救命的东西。")
            empty.setObjectName("Muted")
            self.entries_layout.addWidget(empty)
            return
        for entry in entries:
            card = QFrame()
            card.setObjectName("EntryCard")
            row = QHBoxLayout(card)
            row.setContentsMargins(12, 8, 12, 8)
            row.setSpacing(12)

            stamp = QLabel(paths.human_time(entry.created_at))
            stamp.setObjectName("Muted")
            stamp.setFixedWidth(96)
            stamp.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            stamp.setToolTip(entry.created_at)
            row.addWidget(stamp)

            body = QLabel(entry.body)
            body.setWordWrap(True)
            body.setTextInteractionFlags(Qt.TextSelectableByMouse)
            row.addWidget(body, 1)

            edit_btn = QPushButton("编辑")
            edit_btn.setObjectName("Link")
            edit_btn.setStyleSheet("font-size:9pt;")
            edit_btn.clicked.connect(lambda _=False, eid=entry.id: self._edit_entry(eid))
            row.addWidget(edit_btn, 0, Qt.AlignTop)

            delete_btn = QPushButton("删除")
            delete_btn.setObjectName("Link")
            delete_btn.setStyleSheet("color:#c0392b; font-size:9pt;")
            delete_btn.clicked.connect(lambda _=False, eid=entry.id: self._delete_entry(eid))
            row.addWidget(delete_btn, 0, Qt.AlignTop)

            self.entries_layout.addWidget(card)

    def _edit_entry(self, entry_id: str) -> None:
        if not self._project:
            return
        rows = [e for e in self.repo.list_entries(self._project.id) if e.id == entry_id]
        if not rows:
            return
        dialog = EntryEditDialog(self, rows[0].body)
        if not dialog.exec():
            return
        text = dialog.text()
        if not text:
            return
        self.repo.update_entry(entry_id, text)
        self._render_entries(self.repo.list_entries(self._project.id))
        self.changed.emit()

    def _delete_entry(self, entry_id: str) -> None:
        if not self._project:
            return
        self.repo.delete_entry(entry_id)
        self._render_entries(self.repo.list_entries(self._project.id))
        self._update_meta()
        self.changed.emit()

    def _update_meta(self) -> None:
        if not self._project:
            return
        project = self.repo.get_project(self._project.id)
        if project is None:
            return
        self._project.updated_at = project.updated_at
        shots = self.repo.list_screenshots(project.id)
        entries = self.repo.list_entries(project.id)
        docs = self.repo.list_documents(project.id)
        self.meta_label.setText(
            f"最后更新 {paths.relative_time(project.updated_at)}"
            f" · {len(entries)} 条记录 · {len(shots)} 张截图 · {len(docs)} 份文档"
            f" · 创建于 {paths.human_time(project.created_at, with_year=True)}"
        )

    # ---------------- 文档 ----------------

    def _render_documents(self, docs) -> None:
        _clear_layout(self.docs_layout)
        if not docs:
            empty = QLabel(
                "把 Word、PDF、Excel、PPT 拖进来，会自动读取内容并问你要不要存到项目里。"
            )
            empty.setObjectName("Muted")
            empty.setWordWrap(True)
            self.docs_layout.addWidget(empty)
            return
        for doc in docs:
            self.docs_layout.addWidget(self._document_card(doc))

    def _document_card(self, doc) -> QWidget:
        card = QFrame()
        card.setObjectName("EntryCard")
        row = QHBoxLayout(card)
        row.setContentsMargins(12, 9, 12, 9)
        row.setSpacing(12)

        from ..core.documents import kind_of
        from .document_dialog import kind_color

        kind = kind_of(doc.ext)
        badge = QLabel(kind)
        badge.setAlignment(Qt.AlignCenter)
        badge.setFixedWidth(54)
        color = kind_color(kind)
        badge.setStyleSheet(
            f"color:{color}; border:1px solid {color}55; background:{color}14;"
            " border-radius:5px; padding:3px 0; font-size:8.5pt; font-weight:600;"
        )
        row.addWidget(badge)

        text_box = QVBoxLayout()
        text_box.setSpacing(2)
        name = QLabel(doc.orig_name)
        name.setWordWrap(True)
        name.setStyleSheet("font-weight:600;")
        text_box.addWidget(name)

        bits = [paths.human_size(doc.size)]
        if doc.text_content:
            bits.append(f"{len(doc.text_content)} 字")
        else:
            bits.append("无文本")
        bits.append(paths.human_time(doc.created_at))
        meta = QLabel(" · ".join(bits))
        meta.setObjectName("Muted")
        text_box.addWidget(meta)
        row.addLayout(text_box, 1)

        open_btn = QPushButton("查看")
        open_btn.setObjectName("Link")
        open_btn.clicked.connect(lambda _=False, d=doc: self._view_document(d.id))
        row.addWidget(open_btn)

        del_btn = QPushButton("删除")
        del_btn.setObjectName("Link")
        del_btn.setStyleSheet("color:#c0392b; font-size:9pt;")
        del_btn.clicked.connect(lambda _=False, d=doc: self._delete_document(d.id))
        row.addWidget(del_btn)
        return card

    def _view_document(self, doc_id: str) -> None:
        doc = self.repo.get_document(doc_id)
        if doc is None:
            return
        from .document_dialog import DocumentViewer

        if self.doc_store is None:
            QMessageBox.warning(self, "打不开", "文档存储没有初始化。")
            return
        viewer = DocumentViewer(self, doc, self.doc_store.abs_path(doc.rel_path))
        viewer.setAttribute(Qt.WA_DeleteOnClose, True)
        viewer.show()
        viewer.raise_()
        viewer.activateWindow()

    def _delete_document(self, doc_id: str) -> None:
        if not self._project:
            return
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
        self._render_documents(self.repo.list_documents(self._project.id))
        self._update_meta()
        self.changed.emit()

    def _import_documents(self, paths_list: list[Path]) -> int:
        """逐个询问并把文档存进项目，返回入库数量。"""
        if not self._project or self.doc_store is None:
            return 0
        from ..core.documents import DocumentError, extract_text

        added = 0
        for path in paths_list:
            try:
                data = path.read_bytes()
            except OSError as exc:
                QMessageBox.warning(self, "读取失败", f"{path.name}\n{exc}")
                continue

            from ..core.documents import sha256_of

            digest = sha256_of(data)
            if self.repo.find_document_by_hash(self._project.id, digest):
                QMessageBox.information(
                    self, "已经有了", f"「{path.name}」已经在当前项目的文档里了。"
                )
                continue

            text, warning = extract_text(path)

            from .document_dialog import DocumentImportDialog, kind_color  # noqa: F401
            from ..core.documents import kind_of

            dialog = DocumentImportDialog(
                self,
                name=path.name,
                kind=kind_of(path.suffix),
                size=len(data),
                text=text,
                warning=warning,
            )
            if not dialog.exec():
                continue
            if dialog.choice() == DocumentImportDialog.READ_ONLY:
                # 只看不存：把内容直接作为一条记录留下，不复制文件
                if text:
                    self.repo.add_entry(
                        self._project.id, f"读了《{path.name}》：\n{text[:2000]}"
                    )
                    added += 1
                continue

            try:
                rel, size, digest = self.doc_store.save(self._project.id, path)
            except DocumentError as exc:
                QMessageBox.warning(self, "保存失败", f"{path.name}\n{exc}")
                continue
            self.repo.add_document(
                self._project.id,
                rel_path=rel,
                orig_name=path.name,
                ext=path.suffix.lower(),
                size=size,
                sha256=digest,
                text_content=text,
            )
            added += 1
        return added

    # ---------------- 截图 ----------------

    def _render_shots(self, shots) -> None:
        _clear_layout(self.shots_layout)
        if not shots:
            empty = QLabel("还没有截图。做项目时随手截一张阶段成果，回顾时比文字直观得多。")
            empty.setObjectName("Muted")
            self.shots_layout.addWidget(empty)
            return
        for shot in shots:
            thumb_path = self.store.abs_thumb(shot.thumb_path) if shot.thumb_path else Path()
            if shot.thumb_path and not thumb_path.is_file():
                self.store.make_thumbnail_from(shot.rel_path, shot.thumb_path)
            card = ScreenshotCard(shot, thumb_path, self.store.abs_shot(shot.rel_path))
            card.opened.connect(self._view_shot)
            card.caption_changed.connect(self._save_caption)
            card.removed.connect(self._delete_shot)
            self.shots_layout.addWidget(card)

    def _save_caption(self, shot_id: str, text: str) -> None:
        self.repo.set_caption(shot_id, text)
        self.changed.emit()

    def _view_shot(self, shot_id: str) -> None:
        shot = self.repo.get_screenshot(shot_id)
        if shot is None:
            return
        image_path = self.store.abs_shot(shot.rel_path)
        if not image_path.is_file():
            QMessageBox.warning(self, "图片丢失", f"文件不存在：\n{image_path}")
            return
        viewer = ImageViewer(self, image_path, shot.caption or "查看截图")
        viewer.setModal(False)
        viewer.setAttribute(Qt.WA_DeleteOnClose, True)
        viewer.show()
        viewer.raise_()
        viewer.activateWindow()

    def _delete_shot(self, shot_id: str) -> None:
        if not self._project:
            return
        shot = self.repo.delete_screenshot(shot_id)
        if shot:
            self.store.remove_files([shot.rel_path, shot.thumb_path])
        self._render_shots(self.repo.list_screenshots(self._project.id))
        self._update_meta()
        self.changed.emit()

    def _add_files(self, files: list[str]) -> None:
        """拖进来的文件：图片进截图时间线，其余按文档处理。"""
        if not self._project:
            return
        from ..core.documents import is_document

        images: list[Path] = []
        documents: list[Path] = []
        skipped: list[str] = []
        for file_text in files:
            path = Path(file_text)
            if not path.is_file():
                continue
            suffix = path.suffix.lower()
            if suffix in config.IMAGE_SUFFIXES:
                images.append(path)
            elif is_document(path):
                documents.append(path)
            else:
                skipped.append(path.name)

        shots_added = self._add_image_paths(images)
        docs_added = self._import_documents(documents) if documents else 0

        if docs_added:
            self._render_documents(self.repo.list_documents(self._project.id))
        if shots_added:
            self._render_shots(self.repo.list_screenshots(self._project.id))
        if shots_added or docs_added:
            self._update_meta()
            self.changed.emit()

        if skipped:
            preview = "、".join(skipped[:5])
            more = f" 等 {len(skipped)} 个" if len(skipped) > 5 else ""
            QMessageBox.information(
                self,
                "这些类型还不支持",
                f"{preview}{more} 没能导入。\n\n"
                "目前支持：图片，以及 PDF / Word / Excel / PPT 和常见文本文件。",
            )

    def _add_image_paths(self, images: list[Path]) -> int:
        added = 0
        for path in images:
            try:
                data = path.read_bytes()
            except OSError as exc:
                QMessageBox.warning(self, "读取失败", f"{path}\n{exc}")
                continue
            if self._store_image(data, path.suffix.lower()):
                added += 1
        return added

    def _paste_image(self) -> None:
        if not self._project:
            return
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()
        data: bytes | None = None
        if mime is not None and mime.hasImage():
            image = clipboard.image()
            if not image.isNull():
                buffer = QByteArray()
                device = QBuffer(buffer)
                device.open(QIODevice.WriteOnly)
                image.save(device, "PNG")
                device.close()
                data = bytes(buffer)
        elif mime is not None and mime.hasUrls():
            self._add_files([u.toLocalFile() for u in mime.urls() if u.isLocalFile()])
            return
        if not data:
            QMessageBox.information(self, "没有图片", "剪贴板里没有可用的图片。")
            return
        if self._store_image(data, ".png"):
            self._render_shots(self.repo.list_screenshots(self._project.id))
            self._update_meta()
            self.changed.emit()

    # ---------------- 区域截图 ----------------

    def _start_capture(self) -> None:
        if not self._project:
            return
        window = self.window()
        self._capture_restore = window.isVisible()
        if self._capture_restore:
            # 先把自己藏起来，免得截进去
            window.hide()
        QTimer.singleShot(220, self._show_capture_overlay)

    def _show_capture_overlay(self) -> None:
        from .capture import ScreenCaptureOverlay

        overlay = ScreenCaptureOverlay()
        overlay.captured.connect(self._on_captured)
        overlay.cancelled.connect(self._on_capture_cancelled)
        self._overlay = overlay
        overlay.show()
        overlay.raise_()
        overlay.activateWindow()
        overlay.setFocus(Qt.OtherFocusReason)

    def _restore_window(self) -> None:
        if not getattr(self, "_capture_restore", True):
            return
        window = self.window()
        window.show()
        window.raise_()
        window.activateWindow()

    def _on_capture_cancelled(self) -> None:
        self._overlay = None
        self._restore_window()

    def _on_captured(self, pixmap: QPixmap) -> None:
        self._overlay = None
        self._restore_window()
        if pixmap.isNull():
            QMessageBox.warning(self, "截图失败", "没有拿到图像。")
            return
        buffer = QByteArray()
        device = QBuffer(buffer)
        device.open(QIODevice.WriteOnly)
        pixmap.save(device, "PNG")
        device.close()
        data = bytes(buffer)
        if not data:
            QMessageBox.warning(self, "截图失败", "没能生成图片数据。")
            return
        if self._store_image(data, ".png") and self._project:
            self._render_shots(self.repo.list_screenshots(self._project.id))
            self._update_meta()
            self.changed.emit()

    def _store_image(self, data: bytes, suffix: str) -> bool:
        assert self._project is not None
        try:
            rel, thumb_rel, digest, duplicated = self.store.save_bytes(
                self._project.id, data, suffix
            )
        except ScreenshotError as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return False
        if self.repo.find_screenshot_by_hash(self._project.id, digest):
            return False
        self.repo.add_screenshot(
            self._project.id, rel_path=rel, thumb_path=thumb_rel, sha256=digest
        )
        return True

    # ---------------- 其它操作 ----------------

    def _show_menu(self) -> None:
        if not self._project:
            return
        menu = QMenu(self)
        edit_action = menu.addAction("编辑项目信息")
        menu.addSeparator()
        copy_action = menu.addAction("复制项目路径")
        open_action = menu.addAction("在资源管理器中打开")
        menu.addSeparator()
        archive_text = "移出归档" if self._project.status == "archived" else "归档"
        archive_action = menu.addAction(archive_text)
        menu.addSeparator()
        delete_action = menu.addAction("删除项目…")

        chosen = menu.exec(self.more_btn.mapToGlobal(self.more_btn.rect().bottomLeft()))
        if chosen is None:
            return
        if chosen == edit_action:
            self._edit_project()
        elif chosen == copy_action:
            QApplication.clipboard().setText(self._project.path)
        elif chosen == open_action:
            self._open_folder()
        elif chosen == archive_action:
            if self._project.status == "archived":
                self.repo.set_status(self._project.id, "active")
            else:
                self.repo.set_status(self._project.id, "archived")
            self.bind_project(self._project.id)
            self.changed.emit()
        elif chosen == delete_action:
            self._delete_project()

    def _edit_project(self) -> None:
        if not self._project:
            return
        dialog = ProjectDialog(self, project=self._project)
        if dialog.exec():
            values = dialog.values()
            self.repo.update_project(
                self._project.id,
                name=values["name"],
                path=values["path"],
                summary=values["summary"],
                status=values["status"],
            )
            self.repo.set_tags(self._project.id, values["tags"])
            self.bind_project(self._project.id)
            self.changed.emit()

    def _delete_project(self) -> None:
        if not self._project:
            return
        confirm = QMessageBox.question(
            self, "删除项目",
            f"确定删除「{self._project.name}」？\n记录、截图会一起删除，无法恢复。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return
        project_id = self._project.id
        self.repo.delete_project(project_id)
        self.repo.prune_orphan_tags()
        self.store.remove_project(project_id)
        if self.doc_store is not None:
            self.doc_store.remove_project(project_id)
        self.clear()
        self.deleted.emit(project_id)