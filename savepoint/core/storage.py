"""截图文件与缩略图管理。"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

import hashlib
import io
import shutil
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageOps

from .. import config


class ScreenshotError(Exception):
    pass


class ShotStore:
    def __init__(
        self,
        shot_dir: Path = config.SHOT_DIR,
        thumb_dir: Path = config.THUMB_DIR,
        thumb_max: int = config.THUMB_MAX,
    ) -> None:
        self.shot_dir = shot_dir
        self.thumb_dir = thumb_dir
        self.thumb_max = thumb_max
        self.shot_dir.mkdir(parents=True, exist_ok=True)
        self.thumb_dir.mkdir(parents=True, exist_ok=True)

    # ---------------- 路径 ----------------

    def abs_shot(self, rel: str) -> Path:
        return self.shot_dir / rel

    def abs_thumb(self, rel: str) -> Path:
        return self.thumb_dir / rel

    # ---------------- 写入 ----------------

    def save_bytes(
        self,
        project_id: str,
        data: bytes,
        suffix: str = ".png",
        taken_at: datetime | None = None,
    ) -> tuple[str, str, str, bool]:
        """保存截图与缩略图，返回 (相对路径, 缩略图相对路径, sha256, 是否重复)。"""
        if not data:
            raise ScreenshotError("图片数据为空")
        digest = hashlib.sha256(data).hexdigest()
        stamp = taken_at or datetime.now()
        name = f"{stamp:%Y%m%d-%H%M%S}_{digest[:10]}{suffix.lower()}"
        rel = f"{project_id}/{name}"
        thumb_rel = f"{project_id}/{stamp:%Y%m%d-%H%M%S}_{digest[:10]}.png"

        target = self.abs_shot(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        already = target.exists()
        if not already:
            target.write_bytes(data)

        thumb_abs = self.abs_thumb(thumb_rel)
        if not thumb_abs.exists():
            thumb_abs.parent.mkdir(parents=True, exist_ok=True)
            try:
                self._write_thumbnail(data, thumb_abs)
            except Exception:
                thumb_abs = None  # type: ignore[assignment]
        return rel, (thumb_rel if thumb_abs else ""), digest, already

    def save_file(
        self, project_id: str, source: Path | str, taken_at: datetime | None = None
    ) -> tuple[str, str, str]:
        path = Path(source)
        if not path.is_file():
            raise ScreenshotError(f"文件不存在：{path}")
        if path.suffix.lower() not in config.IMAGE_SUFFIXES:
            raise ScreenshotError(f"不支持的图片格式：{path.suffix}")
        data = path.read_bytes()
        rel, thumb_rel, digest, _ = self.save_bytes(
            project_id, data, path.suffix.lower(), taken_at
        )
        return rel, thumb_rel, digest

    def _write_thumbnail(self, data: bytes, target: Path) -> None:
        with Image.open(io.BytesIO(data)) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA")
            img.thumbnail((self.thumb_max, self.thumb_max), Image.LANCZOS)
            canvas = Image.new("RGBA", img.size, (255, 255, 255, 255))
            canvas.alpha_composite(img.convert("RGBA"))
            canvas.convert("RGB").save(target, "PNG", optimize=True)

    def make_thumbnail_from(self, rel: str, thumb_rel: str) -> bool:
        """缩略图缺失时按原图补一张。"""
        src = self.abs_shot(rel)
        if not src.is_file():
            return False
        dst = self.abs_thumb(thumb_rel)
        dst.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._write_thumbnail(src.read_bytes(), dst)
            return True
        except Exception:
            return False

    # ---------------- 删除 ----------------

    def remove_project(self, project_id: str) -> None:
        for root in (self.shot_dir, self.thumb_dir):
            folder = root / project_id
            if folder.exists():
                shutil.rmtree(folder, ignore_errors=True)

    def remove_files(self, rel_paths: list[str]) -> None:
        for rel in rel_paths:
            if not rel:
                continue
            for root in (self.shot_dir, self.thumb_dir):
                path = root / rel
                try:
                    if path.is_file():
                        path.unlink()
                except OSError:
                    pass

    # ---------------- 统计 ----------------

    def project_usage(self, project_id: str) -> tuple[int, int]:
        folder = self.shot_dir / project_id
        if not folder.is_dir():
            return 0, 0
        count = 0
        size = 0
        for path in folder.rglob("*"):
            if path.is_file():
                count += 1
                size += path.stat().st_size
        return count, size