"""SQLite 连接与版本化迁移。

约定：
* 外键默认关闭，必须显式 PRAGMA foreign_keys=ON。
* 时间统一存本地时间的 ISO 文本 ``YYYY-MM-DDTHH:MM:SS``。
"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS projects (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'active'
                CHECK (status IN ('active','paused','done','archived')),
    path        TEXT NOT NULL DEFAULT '',
    summary     TEXT NOT NULL DEFAULT '',
    notes       TEXT NOT NULL DEFAULT '',
    next_step   TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE
);

CREATE TABLE IF NOT EXISTS project_tags (
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    tag_id     INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (project_id, tag_id)
);

CREATE TABLE IF NOT EXISTS entries (
    id         TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS screenshots (
    id         TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    rel_path   TEXT NOT NULL,
    thumb_path TEXT NOT NULL DEFAULT '',
    caption    TEXT NOT NULL DEFAULT '',
    sha256     TEXT NOT NULL DEFAULT '',
    taken_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vault_items (
    id           TEXT PRIMARY KEY,
    project_id   TEXT REFERENCES projects(id) ON DELETE SET NULL,
    category     TEXT NOT NULL DEFAULT 'other'
                 CHECK (category IN ('apikey','prompt','account','snippet','other')),
    title        TEXT NOT NULL,
    content      TEXT NOT NULL,
    is_sensitive INTEGER NOT NULL DEFAULT 0,
    note         TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_entries_project  ON entries(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_shots_project    ON screenshots(project_id, taken_at);
CREATE INDEX IF NOT EXISTS idx_shots_sha        ON screenshots(project_id, sha256);
CREATE INDEX IF NOT EXISTS idx_vault_category   ON vault_items(category, updated_at);
CREATE INDEX IF NOT EXISTS idx_projects_status  ON projects(status, updated_at);
"""

# v2：保险箱 => 笔记。去掉加密相关字段，改成"目录 + 文档"。
# 旧的分类映射成目录名，密文原样保留（由用户自行清理）。
SCHEMA_V2 = """
CREATE TABLE IF NOT EXISTS notes (
    id         TEXT PRIMARY KEY,
    folder     TEXT NOT NULL DEFAULT '未分类',
    title      TEXT NOT NULL DEFAULT '',
    content    TEXT NOT NULL DEFAULT '',
    project_id TEXT REFERENCES projects(id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

INSERT INTO notes (id, folder, title, content, project_id, created_at, updated_at)
SELECT id,
       CASE category
           WHEN 'apikey'  THEN '密钥与账号'
           WHEN 'account' THEN '密钥与账号'
           WHEN 'prompt'  THEN '提示词'
           WHEN 'snippet' THEN '配置片段'
           ELSE '未分类'
       END,
       title, content, project_id, created_at, updated_at
FROM vault_items;

DROP TABLE IF EXISTS vault_items;

DELETE FROM meta WHERE key IN ('kdf_salt', 'kdf_iterations', 'pw_check');

CREATE INDEX IF NOT EXISTS idx_notes_folder ON notes(folder, updated_at);
"""

# v3：软删除（回收站）。删除只打时间戳，30 天内可恢复。
SCHEMA_V3 = """
ALTER TABLE entries ADD COLUMN deleted_at TEXT;
ALTER TABLE screenshots ADD COLUMN deleted_at TEXT;
ALTER TABLE notes ADD COLUMN deleted_at TEXT;

CREATE INDEX IF NOT EXISTS idx_entries_deleted ON entries(deleted_at);
CREATE INDEX IF NOT EXISTS idx_shots_deleted    ON screenshots(deleted_at);
CREATE INDEX IF NOT EXISTS idx_notes_deleted    ON notes(deleted_at);
"""

# v4：文档。把 Word / PDF / Excel 之类拖进来存到项目里，顺带存提取出的纯文本。
SCHEMA_V4 = """
CREATE TABLE IF NOT EXISTS documents (
    id           TEXT PRIMARY KEY,
    project_id   TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    rel_path     TEXT NOT NULL,
    orig_name    TEXT NOT NULL,
    ext          TEXT NOT NULL DEFAULT '',
    size         INTEGER NOT NULL DEFAULT 0,
    sha256       TEXT NOT NULL DEFAULT '',
    text_content TEXT NOT NULL DEFAULT '',
    note         TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    deleted_at   TEXT
);

CREATE INDEX IF NOT EXISTS idx_docs_project ON documents(project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_docs_sha     ON documents(project_id, sha256);
CREATE INDEX IF NOT EXISTS idx_docs_deleted ON documents(deleted_at);
"""

# v5：文档从「挂在项目下」改成「独立的文档库」，用分区归类，项目关联变成可选。
# SQLite 不能直接去掉 NOT NULL，所以重建表再搬数据。
SCHEMA_V5 = """
CREATE TABLE documents_v5 (
    id           TEXT PRIMARY KEY,
    folder       TEXT NOT NULL DEFAULT '未分类',
    project_id   TEXT REFERENCES projects(id) ON DELETE SET NULL,
    rel_path     TEXT NOT NULL,
    orig_name    TEXT NOT NULL,
    ext          TEXT NOT NULL DEFAULT '',
    size         INTEGER NOT NULL DEFAULT 0,
    sha256       TEXT NOT NULL DEFAULT '',
    text_content TEXT NOT NULL DEFAULT '',
    note         TEXT NOT NULL DEFAULT '',
    created_at   TEXT NOT NULL,
    deleted_at   TEXT
);

INSERT INTO documents_v5 (id, folder, project_id, rel_path, orig_name, ext, size,
                          sha256, text_content, note, created_at, deleted_at)
SELECT id, '未分类', project_id, rel_path, orig_name, ext, size,
       sha256, text_content, note, created_at, deleted_at
FROM documents;

DROP TABLE documents;
ALTER TABLE documents_v5 RENAME TO documents;

CREATE INDEX IF NOT EXISTS idx_docs_folder  ON documents(folder, created_at);
CREATE INDEX IF NOT EXISTS idx_docs_sha     ON documents(sha256);
CREATE INDEX IF NOT EXISTS idx_docs_deleted ON documents(deleted_at);
"""

# (目标版本, 脚本)。新增变更时追加，不要修改已发布的历史脚本。
MIGRATIONS: list[tuple[int, str]] = [
    (1, SCHEMA_V1),
    (2, SCHEMA_V2),
    (3, SCHEMA_V3),
    (4, SCHEMA_V4),
    (5, SCHEMA_V5),
]

SCHEMA_VERSION = MIGRATIONS[-1][0]


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=20.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def current_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def migrate(conn: sqlite3.Connection) -> int:
    version = current_version(conn)
    for target, script in MIGRATIONS:
        if version < target:
            conn.executescript(script)
            conn.execute(f"PRAGMA user_version = {target}")
            conn.commit()
            version = target
    return version


def open_database(db_path: Path) -> sqlite3.Connection:
    conn = connect(db_path)
    migrate(conn)
    return conn