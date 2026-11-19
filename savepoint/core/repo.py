"""数据访问层：项目、标签、记录、截图、笔记。"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta


def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")


def new_id() -> str:
    return uuid.uuid4().hex


@dataclass
class Project:
    id: str
    name: str
    status: str = "active"
    path: str = ""
    summary: str = ""
    notes: str = ""
    next_step: str = ""
    created_at: str = ""
    updated_at: str = ""
    tags: list[str] = field(default_factory=list)


@dataclass
class Entry:
    id: str
    project_id: str
    body: str
    created_at: str


@dataclass
class Screenshot:
    id: str
    project_id: str
    rel_path: str
    thumb_path: str
    caption: str
    sha256: str
    taken_at: str


@dataclass
class Note:
    id: str
    folder: str
    title: str
    content: str
    project_id: str | None
    created_at: str
    updated_at: str


class Repo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    # ---------------- 项目 ----------------

    def create_project(
        self,
        name: str,
        *,
        path: str = "",
        summary: str = "",
        status: str = "active",
        tags: list[str] | None = None,
    ) -> Project:
        stamp = now_iso()
        pid = new_id()
        self.conn.execute(
            "INSERT INTO projects (id, name, status, path, summary, notes, next_step,"
            " created_at, updated_at) VALUES (?,?,?,?,?,'','',?,?)",
            (pid, name.strip(), status, path.strip(), summary.strip(), stamp, stamp),
        )
        self.set_tags(pid, tags or [])
        self.conn.commit()
        return self.get_project(pid)

    def get_project(self, project_id: str) -> Project | None:
        row = self.conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
        if row is None:
            return None
        project = Project(
            id=row["id"],
            name=row["name"],
            status=row["status"],
            path=row["path"],
            summary=row["summary"],
            notes=row["notes"],
            next_step=row["next_step"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        project.tags = self.tags_of(project_id)
        return project

    def update_project(self, project_id: str, **fields: str) -> None:
        allowed = {"name", "status", "path", "summary", "notes", "next_step"}
        patch = {k: v for k, v in fields.items() if k in allowed}
        if not patch:
            return
        patch["updated_at"] = now_iso()
        assignments = ", ".join(f"{k} = ?" for k in patch)
        self.conn.execute(
            f"UPDATE projects SET {assignments} WHERE id = ?",
            (*patch.values(), project_id),
        )
        self.conn.commit()

    def touch(self, project_id: str) -> None:
        self.conn.execute(
            "UPDATE projects SET updated_at = ? WHERE id = ?", (now_iso(), project_id)
        )
        self.conn.commit()

    def delete_project(self, project_id: str) -> None:
        self.conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        self.conn.commit()

    def set_status(self, project_id: str, status: str) -> None:
        self.update_project(project_id, status=status)

    def list_projects(
        self,
        *,
        status: str | None = None,
        tag: str | None = None,
        query: str | None = None,
        order: str = "updated",
    ) -> list[Project]:
        sql = ["SELECT p.* FROM projects p"]
        params: list[object] = []
        if tag:
            sql.append(
                "JOIN project_tags pt ON pt.project_id = p.id"
                " JOIN tags t ON t.id = pt.tag_id AND t.name = ? COLLATE NOCASE"
            )
            params.append(tag)
        where: list[str] = []
        if status:
            where.append("p.status = ?")
            params.append(status)
        if query:
            like = f"%{query}%"
            where.append(
                "(p.name LIKE ? OR p.summary LIKE ? OR p.notes LIKE ? OR p.next_step LIKE ?"
                " OR EXISTS (SELECT 1 FROM entries e WHERE e.project_id = p.id AND e.body LIKE ?))"
            )
            params.extend([like] * 5)
        if where:
            sql.append("WHERE " + " AND ".join(where))
        if order == "created":
            sql.append("ORDER BY p.created_at DESC")
        elif order == "name":
            sql.append("ORDER BY p.name COLLATE NOCASE")
        else:
            sql.append("ORDER BY p.updated_at DESC")
        rows = self.conn.execute(" ".join(sql), params).fetchall()
        projects = []
        for row in rows:
            project = Project(
                id=row["id"],
                name=row["name"],
                status=row["status"],
                path=row["path"],
                summary=row["summary"],
                notes=row["notes"],
                next_step=row["next_step"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            project.tags = self.tags_of(project.id)
            projects.append(project)
        return projects

    def status_counts(self) -> dict[str, int]:
        rows = self.conn.execute(
            "SELECT status, COUNT(*) AS n FROM projects GROUP BY status"
        ).fetchall()
        counts = {row["status"]: row["n"] for row in rows}
        counts["all"] = sum(counts.values())
        return counts

    def stale_projects(self, days: int) -> list[Project]:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
        rows = self.conn.execute(
            "SELECT id FROM projects WHERE status = 'active' AND updated_at < ?"
            " ORDER BY updated_at ASC",
            (cutoff,),
        ).fetchall()
        return [p for p in (self.get_project(row["id"]) for row in rows) if p]

    def recent_projects(self, days: int) -> list[Project]:
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
        rows = self.conn.execute(
            "SELECT id FROM projects WHERE updated_at >= ? ORDER BY updated_at DESC",
            (cutoff,),
        ).fetchall()
        return [p for p in (self.get_project(row["id"]) for row in rows) if p]

    # ---------------- 标签 ----------------

    def tags_of(self, project_id: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT t.name FROM tags t JOIN project_tags pt ON pt.tag_id = t.id"
            " WHERE pt.project_id = ? ORDER BY t.name COLLATE NOCASE",
            (project_id,),
        ).fetchall()
        return [row["name"] for row in rows]

    def set_tags(self, project_id: str, names: list[str]) -> None:
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw in names:
            name = raw.strip().lstrip("#").strip()
            if name and name.casefold() not in seen:
                seen.add(name.casefold())
                cleaned.append(name)
        self.conn.execute("DELETE FROM project_tags WHERE project_id = ?", (project_id,))
        for name in cleaned:
            self.conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
            tag_id = self.conn.execute(
                "SELECT id FROM tags WHERE name = ? COLLATE NOCASE", (name,)
            ).fetchone()["id"]
            self.conn.execute(
                "INSERT OR IGNORE INTO project_tags (project_id, tag_id) VALUES (?, ?)",
                (project_id, tag_id),
            )
        self.conn.execute(
            "UPDATE projects SET updated_at = ? WHERE id = ?", (now_iso(), project_id)
        )
        self.conn.commit()

    def all_tags(self) -> list[tuple[str, int]]:
        rows = self.conn.execute(
            "SELECT t.name, COUNT(pt.project_id) AS n FROM tags t"
            " LEFT JOIN project_tags pt ON pt.tag_id = t.id"
            " GROUP BY t.id HAVING n > 0 ORDER BY n DESC, t.name COLLATE NOCASE"
        ).fetchall()
        return [(row["name"], row["n"]) for row in rows]

    def prune_orphan_tags(self) -> None:
        self.conn.execute(
            "DELETE FROM tags WHERE id NOT IN (SELECT tag_id FROM project_tags)"
        )
        self.conn.commit()

    # ---------------- 记录（追加式日志） ----------------

    def add_entry(self, project_id: str, body: str) -> Entry:
        text = body.strip()
        if not text:
            raise ValueError("记录内容不能为空")
        stamp = now_iso()
        entry_id = new_id()
        self.conn.execute(
            "INSERT INTO entries (id, project_id, body, created_at) VALUES (?,?,?,?)",
            (entry_id, project_id, text, stamp),
        )
        self.conn.execute(
            "UPDATE projects SET updated_at = ? WHERE id = ?", (stamp, project_id)
        )
        self.conn.commit()
        return Entry(entry_id, project_id, text, stamp)

    def list_entries(self, project_id: str, *, newest_first: bool = True) -> list[Entry]:
        order = "DESC" if newest_first else "ASC"
        rows = self.conn.execute(
            "SELECT * FROM entries WHERE project_id = ? AND deleted_at IS NULL"
            f" ORDER BY created_at {order}, rowid {order}",
            (project_id,),
        ).fetchall()
        return [Entry(r["id"], r["project_id"], r["body"], r["created_at"]) for r in rows]

    def update_entry(self, entry_id: str, body: str) -> None:
        self.conn.execute("UPDATE entries SET body = ? WHERE id = ?", (body.strip(), entry_id))
        self.conn.commit()

    def delete_entry(self, entry_id: str) -> None:
        """软删除，进回收站。"""
        self.conn.execute(
            "UPDATE entries SET deleted_at = ? WHERE id = ?", (now_iso(), entry_id)
        )
        self.conn.commit()

    # ---------------- 截图 ----------------

    def add_screenshot(
        self,
        project_id: str,
        *,
        rel_path: str,
        thumb_path: str,
        sha256: str,
        caption: str = "",
        taken_at: str | None = None,
    ) -> Screenshot:
        shot_id = new_id()
        stamp = taken_at or now_iso()
        self.conn.execute(
            "INSERT INTO screenshots (id, project_id, rel_path, thumb_path, caption, sha256,"
            " taken_at) VALUES (?,?,?,?,?,?,?)",
            (shot_id, project_id, rel_path, thumb_path, caption.strip(), sha256, stamp),
        )
        self.conn.execute(
            "UPDATE projects SET updated_at = ? WHERE id = ?", (now_iso(), project_id)
        )
        self.conn.commit()
        return Screenshot(shot_id, project_id, rel_path, thumb_path, caption.strip(), sha256, stamp)

    def list_screenshots(self, project_id: str) -> list[Screenshot]:
        rows = self.conn.execute(
            "SELECT * FROM screenshots WHERE project_id = ? AND deleted_at IS NULL"
            " ORDER BY taken_at ASC, rowid ASC",
            (project_id,),
        ).fetchall()
        return [
            Screenshot(
                r["id"], r["project_id"], r["rel_path"], r["thumb_path"],
                r["caption"], r["sha256"], r["taken_at"],
            )
            for r in rows
        ]

    def find_screenshot_by_hash(self, project_id: str, sha256: str) -> Screenshot | None:
        row = self.conn.execute(
            "SELECT * FROM screenshots WHERE project_id = ? AND sha256 = ?"
            " AND deleted_at IS NULL",
            (project_id, sha256),
        ).fetchone()
        if row is None:
            return None
        return Screenshot(
            row["id"], row["project_id"], row["rel_path"], row["thumb_path"],
            row["caption"], row["sha256"], row["taken_at"],
        )

    def set_caption(self, shot_id: str, caption: str) -> None:
        self.conn.execute(
            "UPDATE screenshots SET caption = ? WHERE id = ?", (caption.strip(), shot_id)
        )
        self.conn.commit()

    def get_screenshot(self, shot_id: str) -> Screenshot | None:
        row = self.conn.execute("SELECT * FROM screenshots WHERE id = ?", (shot_id,)).fetchone()
        if row is None:
            return None
        return Screenshot(
            row["id"], row["project_id"], row["rel_path"], row["thumb_path"],
            row["caption"], row["sha256"], row["taken_at"],
        )

    def delete_screenshot(self, shot_id: str) -> Screenshot | None:
        """软删除，进回收站；文件先留着，彻底删除时才清。"""
        shot = self.get_screenshot(shot_id)
        if shot is None:
            return None
        self.conn.execute(
            "UPDATE screenshots SET deleted_at = ? WHERE id = ?", (now_iso(), shot_id)
        )
        self.conn.commit()
        return shot

    def screenshot_paths(self, project_id: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT rel_path, thumb_path FROM screenshots WHERE project_id = ?",
            (project_id,),
        ).fetchall()
        paths: list[str] = []
        for row in rows:
            paths.append(row["rel_path"])
            if row["thumb_path"]:
                paths.append(row["thumb_path"])
        return paths

    # ---------------- 笔记 ----------------

    @staticmethod
    def _row_to_note(row: sqlite3.Row) -> Note:
        return Note(
            id=row["id"],
            folder=row["folder"],
            title=row["title"],
            content=row["content"],
            project_id=row["project_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list_notes(
        self, *, folder: str | None = None, query: str | None = None
    ) -> list[Note]:
        sql = ["SELECT * FROM notes WHERE deleted_at IS NULL"]
        where: list[str] = []
        params: list[object] = []
        if folder:
            where.append("folder = ?")
            params.append(folder)
        if query:
            like = f"%{query}%"
            where.append("(title LIKE ? OR content LIKE ?)")
            params.extend([like, like])
        if where:
            sql.append("AND " + " AND ".join(where))
        sql.append("ORDER BY updated_at DESC")
        rows = self.conn.execute(" ".join(sql), params).fetchall()
        return [self._row_to_note(row) for row in rows]

    def get_note(self, note_id: str) -> Note | None:
        row = self.conn.execute(
            "SELECT * FROM notes WHERE id = ? AND deleted_at IS NULL", (note_id,)
        ).fetchone()
        return None if row is None else self._row_to_note(row)

    def create_note(
        self, *, folder: str = "未分类", title: str = "", content: str = "",
        project_id: str | None = None,
    ) -> Note:
        stamp = now_iso()
        note_id = new_id()
        self.conn.execute(
            "INSERT INTO notes (id, folder, title, content, project_id, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (note_id, folder.strip() or "未分类", title.strip(), content, project_id, stamp, stamp),
        )
        self.conn.commit()
        return self.get_note(note_id)

    def update_note(self, note_id: str, **fields: object) -> None:
        allowed = {"folder", "title", "content", "project_id"}
        patch = {k: v for k, v in fields.items() if k in allowed}
        if not patch:
            return
        patch["updated_at"] = now_iso()
        assignments = ", ".join(f"{key} = ?" for key in patch)
        self.conn.execute(
            f"UPDATE notes SET {assignments} WHERE id = ?",
            (*patch.values(), note_id),
        )
        self.conn.commit()

    def delete_note(self, note_id: str) -> None:
        self.conn.execute(
            "UPDATE notes SET deleted_at = ? WHERE id = ?", (now_iso(), note_id)
        )
        self.conn.commit()

    def note_folders(self) -> list[tuple[str, int]]:
        """返回 [(目录名, 文档数)]，按文档数倒序。"""
        rows = self.conn.execute(
            "SELECT folder, COUNT(*) AS n FROM notes WHERE deleted_at IS NULL"
            " GROUP BY folder ORDER BY n DESC, folder COLLATE NOCASE"
        ).fetchall()
        return [(row["folder"], int(row["n"])) for row in rows]

    def count_notes(self) -> int:
        return int(
            self.conn.execute(
                "SELECT COUNT(*) FROM notes WHERE deleted_at IS NULL"
            ).fetchone()[0]
        )

    def rename_note(self, note_id: str, title: str) -> None:
        self.update_note(note_id, title=title.strip())

    def rename_folder(self, old: str, new: str) -> int:
        """整块分区改名，返回改动的笔记数。"""
        target = new.strip()
        if not target or target == old:
            return 0
        cursor = self.conn.execute(
            "UPDATE notes SET folder = ?, updated_at = ?"
            " WHERE folder = ? AND deleted_at IS NULL",
            (target, now_iso(), old),
        )
        self.conn.commit()
        return cursor.rowcount

    def delete_folder(self, folder: str) -> int:
        """把整个分区里的笔记移进回收站，返回数量。"""
        stamp = now_iso()
        cursor = self.conn.execute(
            "UPDATE notes SET deleted_at = ?"
            " WHERE folder = ? AND deleted_at IS NULL",
            (stamp, folder),
        )
        self.conn.commit()
        return cursor.rowcount

    def move_note(self, note_id: str, folder: str) -> None:
        self.update_note(note_id, folder=folder.strip() or "未分类")

    # ---------------- 回收站 ----------------

    def trash_items(self) -> list[dict]:
        """回收站里的东西，按删除时间倒序。"""
        items: list[dict] = []
        rows = self.conn.execute(
            "SELECT e.id, e.body, e.deleted_at, p.name AS project"
            " FROM entries e LEFT JOIN projects p ON p.id = e.project_id"
            " WHERE e.deleted_at IS NOT NULL ORDER BY e.deleted_at DESC"
        ).fetchall()
        for row in rows:
            items.append({
                "kind": "entry", "id": row["id"],
                "title": row["body"][:80],
                "sub": row["project"] or "（项目已移入回收站）",
                "deleted_at": row["deleted_at"],
            })

        rows = self.conn.execute(
            "SELECT s.id, s.caption, s.deleted_at, p.name AS project"
            " FROM screenshots s LEFT JOIN projects p ON p.id = s.project_id"
            " WHERE s.deleted_at IS NOT NULL ORDER BY s.deleted_at DESC"
        ).fetchall()
        for row in rows:
            items.append({
                "kind": "screenshot", "id": row["id"],
                "title": row["caption"] or "（无说明的截图）",
                "sub": row["project"] or "（项目已移入回收站）",
                "deleted_at": row["deleted_at"],
            })

        rows = self.conn.execute(
            "SELECT id, title, folder, deleted_at FROM notes WHERE deleted_at IS NOT NULL"
            " ORDER BY deleted_at DESC"
        ).fetchall()
        for row in rows:
            items.append({
                "kind": "note", "id": row["id"],
                "title": row["title"] or "（无标题）",
                "sub": row["folder"],
                "deleted_at": row["deleted_at"],
            })

        items.sort(key=lambda item: item["deleted_at"], reverse=True)
        return items

    def restore_item(self, kind: str, item_id: str) -> None:
        table = {"entry": "entries", "screenshot": "screenshots", "note": "notes"}.get(kind)
        if not table:
            return
        self.conn.execute(f"UPDATE {table} SET deleted_at = NULL WHERE id = ?", (item_id,))
        self.conn.commit()

    def purge_item(self, kind: str, item_id: str) -> list[str]:
        """彻底删除，返回需要一起删掉的文件相对路径。"""
        if kind == "screenshot":
            shot = self.get_screenshot(item_id)
            self.conn.execute("DELETE FROM screenshots WHERE id = ?", (item_id,))
            self.conn.commit()
            if shot is None:
                return []
            return [shot.rel_path, shot.thumb_path]
        table = {"entry": "entries", "note": "notes"}.get(kind)
        if not table:
            return []
        self.conn.execute(f"DELETE FROM {table} WHERE id = ?", (item_id,))
        self.conn.commit()
        return []

    def purge_expired_trash(self, days: int = 30) -> list[str]:
        """清掉超过保留期的回收站内容，返回要删的截图文件。"""
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
        paths: list[str] = []
        rows = self.conn.execute(
            "SELECT rel_path, thumb_path FROM screenshots"
            " WHERE deleted_at IS NOT NULL AND deleted_at < ?",
            (cutoff,),
        ).fetchall()
        for row in rows:
            paths.append(row["rel_path"])
            if row["thumb_path"]:
                paths.append(row["thumb_path"])
        for table in ("entries", "screenshots", "notes"):
            self.conn.execute(
                f"DELETE FROM {table} WHERE deleted_at IS NOT NULL AND deleted_at < ?",
                (cutoff,),
            )
        self.conn.commit()
        return paths

    # ---------------- 全局搜索 / 活动流 ----------------

    def search_all(self, query: str, limit: int = 30) -> list[dict]:
        """跨项目、记录、笔记、截图说明一起搜。"""
        text = query.strip()
        if not text:
            return []
        like = f"%{text}%"
        results: list[dict] = []

        rows = self.conn.execute(
            "SELECT id, name, summary FROM projects"
            " WHERE name LIKE ? OR summary LIKE ? OR notes LIKE ? OR next_step LIKE ?"
            " ORDER BY updated_at DESC LIMIT ?",
            (like, like, like, like, limit),
        ).fetchall()
        for row in rows:
            results.append({
                "kind": "project", "id": row["id"],
                "title": row["name"], "sub": row["summary"] or "",
            })

        rows = self.conn.execute(
            "SELECT e.id, e.body, e.created_at, e.project_id, p.name AS project"
            " FROM entries e LEFT JOIN projects p ON p.id = e.project_id"
            " WHERE e.deleted_at IS NULL AND e.body LIKE ?"
            " ORDER BY e.created_at DESC LIMIT ?",
            (like, limit),
        ).fetchall()
        for row in rows:
            results.append({
                "kind": "entry", "id": row["id"], "project_id": row["project_id"],
                "title": row["body"][:80],
                "sub": f"{row['project'] or ''} · {row['created_at'][:10]}",
            })

        rows = self.conn.execute(
            "SELECT id, title, folder FROM notes"
            " WHERE deleted_at IS NULL AND (title LIKE ? OR content LIKE ?)"
            " ORDER BY updated_at DESC LIMIT ?",
            (like, like, limit),
        ).fetchall()
        for row in rows:
            results.append({
                "kind": "note", "id": row["id"],
                "title": row["title"] or "（无标题）", "sub": row["folder"],
            })

        rows = self.conn.execute(
            "SELECT s.id, s.caption, s.project_id, p.name AS project FROM screenshots s"
            " LEFT JOIN projects p ON p.id = s.project_id"
            " WHERE s.deleted_at IS NULL AND s.caption LIKE ? LIMIT ?",
            (like, limit),
        ).fetchall()
        for row in rows:
            results.append({
                "kind": "screenshot", "id": row["id"], "project_id": row["project_id"],
                "title": row["caption"] or "（截图）", "sub": row["project"] or "",
            })
        return results

    def activity(self, days: int | None = None, limit: int = 300) -> list[dict]:
        """所有项目的记录合并成一条时间流。"""
        sql = (
            "SELECT e.id, e.body, e.created_at, e.project_id, p.name AS project"
            " FROM entries e LEFT JOIN projects p ON p.id = e.project_id"
            " WHERE e.deleted_at IS NULL"
        )
        params: list[object] = []
        if days:
            cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S")
            sql += " AND e.created_at >= ?"
            params.append(cutoff)
        sql += " ORDER BY e.created_at DESC, e.rowid DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [
            {
                "id": row["id"], "body": row["body"], "created_at": row["created_at"],
                "project_id": row["project_id"], "project": row["project"] or "（已删除）",
            }
            for row in rows
        ]

    # ---------------- meta ----------------

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return None if row is None else row["value"]

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self.conn.commit()