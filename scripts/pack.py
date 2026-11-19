"""把 dist 里的应用目录打成便携包（排除数据和 ini）。"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from savepoint import config  # noqa: E402

APP = "SavePoint"
src = ROOT / "dist" / APP
out = ROOT / "dist" / f"{APP}-{config.APP_VERSION}-portable.zip"
skip = {"pmtool-data", "savepoint-data", "pmtool.ini", "savepoint.ini"}

if not src.is_dir():
    raise SystemExit(f"没有构建产物：{src}")

out.unlink(missing_ok=True)
count = 0
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
    for path in src.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(src)
        if rel.parts and rel.parts[0] in skip:
            continue
        if path.suffix == ".log":
            continue
        archive.write(path, arcname=str(Path(APP) / rel))
        count += 1

print(f"{count} 个文件")
print(f"{out}  {out.stat().st_size / 1024 / 1024:.0f} MB")