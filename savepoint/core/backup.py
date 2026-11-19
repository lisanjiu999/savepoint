"""滚动备份：把数据库与截图打包成快照，限制保留数量。"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

import shutil
import sqlite3
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from .. import config


def _zip_dir(zf: zipfile.ZipFile, folder: Path, arc_root: str) -> int:
    if not folder.is_dir():
        return 0
    count = 0
    for path in folder.rglob("*"):
        if path.is_file():
            arc = Path(arc_root) / path.relative_to(folder)
            # 图片本身已压缩，用 STORED 省 CPU
            method = zipfile.ZIP_STORED if path.suffix.lower() in config.IMAGE_SUFFIXES else zipfile.ZIP_DEFLATED
            zf.write(path, arcname=str(arc).replace("\\", "/"), compress_type=method)
            count += 1
    return count


def make_snapshot(
    *,
    db_path: Path | None = None,
    shot_dir: Path | None = None,
    thumb_dir: Path | None = None,
    backup_dir: Path | None = None,
    keep: int | None = None,
    min_interval_hours: int | None = None,
) -> Path | None:
    """生成一次快照；距上次快照不足 min_interval_hours 时跳过。"""
    db_path = db_path or config.DB_PATH
    shot_dir = shot_dir or config.SHOT_DIR
    thumb_dir = thumb_dir or config.THUMB_DIR
    backup_dir = backup_dir or config.BACKUP_DIR
    keep = config.backup_keep() if keep is None else keep
    if min_interval_hours is None:
        min_interval_hours = config.backup_interval_hours()

    backup_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(backup_dir.glob("snapshot-*.zip"))
    if existing:
        last = datetime.fromtimestamp(existing[-1].stat().st_mtime)
        if datetime.now() - last < timedelta(hours=min_interval_hours):
            return None

    stamp = datetime.now()
    target = backup_dir / f"snapshot-{stamp:%Y%m%d-%H%M%S}.zip"
    tmp_db = backup_dir / f".tmp-{stamp:%Y%m%d%H%M%S}.db"
    tmp_db.unlink(missing_ok=True)

    try:
        src = sqlite3.connect(str(db_path))
        dst = sqlite3.connect(str(tmp_db))
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()

        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            zf.write(tmp_db, arcname="projects.db")
            _zip_dir(zf, shot_dir, "screenshots")
            _zip_dir(zf, thumb_dir, "thumbnails")
            zf.writestr(
                "README.txt",
                f"{config.APP_NAME} 备份\n生成时间：{stamp:%Y-%m-%d %H:%M:%S}\n"
                "恢复：解压到数据目录，projects.db 与 screenshots/ 覆盖回去即可。\n",
            )
    finally:
        tmp_db.unlink(missing_ok=True)

    _prune(backup_dir, keep)
    return target


def _prune(backup_dir: Path, keep: int) -> None:
    if keep <= 0:
        return
    snapshots = sorted(backup_dir.glob("snapshot-*.zip"))
    for old in snapshots[:-keep]:
        try:
            old.unlink()
        except OSError:
            pass


def list_snapshots(backup_dir: Path | None = None) -> list[tuple[Path, int]]:
    backup_dir = backup_dir or config.BACKUP_DIR
    result: list[tuple[Path, int]] = []
    for path in sorted(backup_dir.glob("snapshot-*.zip"), reverse=True):
        try:
            result.append((path, path.stat().st_size))
        except OSError:
            continue
    return result


def restore_snapshot(
    zip_path: Path,
    *,
    data_dir: Path | None = None,
    db_path: Path | None = None,
) -> Path:
    """把快照恢复进数据目录，返回恢复前自动备份的位置。

    调用方必须先关闭数据库连接。
    """
    import sqlite3

    data_dir = data_dir or config.DATA_DIR
    db_path = db_path or config.DB_PATH

    staging = data_dir / ".restore-staging"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(staging)

        new_db = staging / "projects.db"
        if not new_db.is_file():
            raise ValueError("快照里没有 projects.db，无法恢复")

        # 先确认快照里的库能打开
        check = sqlite3.connect(str(new_db))
        try:
            check.execute("SELECT COUNT(*) FROM sqlite_master").fetchone()
        finally:
            check.close()

        # 备份当前数据，恢复错了还能退回来
        safety = data_dir / "backups" / f"pre-restore-{datetime.now():%Y%m%d-%H%M%S}"
        safety.mkdir(parents=True, exist_ok=True)
        if db_path.is_file():
            shutil.copy2(db_path, safety / "projects.db")
        for name in ("screenshots", "thumbnails"):
            source = data_dir / name
            if source.is_dir():
                shutil.copytree(source, safety / name, dirs_exist_ok=True)

        # 替换
        for suffix in ("-wal", "-shm"):
            Path(str(db_path) + suffix).unlink(missing_ok=True)
        shutil.copy2(new_db, db_path)
        for name in ("screenshots", "thumbnails"):
            source = staging / name
            if source.is_dir():
                shutil.rmtree(data_dir / name, ignore_errors=True)
                shutil.copytree(source, data_dir / name)
        return safety
    finally:
        shutil.rmtree(staging, ignore_errors=True)