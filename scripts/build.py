"""一键打包：生成版本信息 → PyInstaller → 打 ZIP。

用法：.venv\\Scripts\\python.exe scripts\\build.py
产物：dist\\项目管理工具\\ 和 dist\\项目管理工具-<版本>-portable.zip
"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from savepoint import config  # noqa: E402

APP_NAME = "SavePoint"
VERSION_FILE = ROOT / "scripts" / "version_info.txt"
SPEC = ROOT / "scripts" / "savepoint.spec"

# 输出放在仓库的 dist 目录（也支持用 SAVEPOINT_DIST 指定别处）。
#
# 注意：如果仓库所在目录带 Windows「低完整性」标签（Low Mandatory Label），
# 从这里生成的 exe 会被系统以受限权限运行，无法唤起资源管理器。
# 遇到这种情况，把 zip 解压到普通目录再运行，或对该目录重新打标签（见 README）。
DIST = Path(os.environ.get("SAVEPOINT_DIST", str(ROOT / "dist")))
BUILD = ROOT / "build"
BUILD_OUT = ROOT / ".build-out"


def write_version_info(version: str) -> None:
    parts = [int(p) for p in (version.split(".") + ["0", "0", "0", "0"])[:4]]
    numbers = tuple(parts)
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={numbers},
    prodvers={numbers},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable('080404b0', [
        StringStruct('CompanyName', 'SavePoint'),
        StringStruct('FileDescription', '{APP_NAME}'),
        StringStruct('FileVersion', '{version}'),
        StringStruct('InternalName', 'savepoint'),
        StringStruct('OriginalFilename', '{APP_NAME}.exe'),
        StringStruct('ProductName', '{APP_NAME}'),
        StringStruct('ProductVersion', '{version}'),
        StringStruct('LegalCopyright', 'MIT License')
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""
    VERSION_FILE.write_text(text, encoding="utf-8")


# 绝不能进分发包的东西：用户数据、本机设置、日志
EXCLUDE_FROM_ZIP = {"savepoint-data", "pmtool-data", "savepoint.ini", "pmtool.ini"}


def make_zip(folder: Path, target: Path) -> Path:
    target.unlink(missing_ok=True)
    skipped = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in folder.rglob("*"):
            if not path.is_file():
                continue
            rel = path.relative_to(folder)
            if rel.parts and rel.parts[0] in EXCLUDE_FROM_ZIP:
                skipped += 1
                continue
            if path.suffix == ".log":
                skipped += 1
                continue
            archive.write(path, arcname=str(Path(folder.name) / rel))
    if skipped:
        print(f"      已排除 {skipped} 个用户数据/日志文件")
    return target


def sync_output(source: Path, target: Path) -> bool:
    """把构建产物同步到目标目录。

    不直接删除 dist：那里面可能有用户数据，也可能被 Windows 句柄占着。
    用 robocopy 镜像，并排除数据目录与 ini。
    """
    target.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        [
            "robocopy",
            str(source),
            str(target),
            "/MIR",
            "/XD",
            "pmtool-data",
            "savepoint-data",
            "/XF",
            "pmtool.ini",
            "savepoint.ini",
            "/R:2",
            "/W:1",
            "/NFL",
            "/NDL",
            "/NJH",
            "/NJS",
            "/NP",
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode < 8


def main() -> int:
    version = config.APP_VERSION
    write_version_info(version)
    print(f"[1/3] 版本信息已生成：{version}")

    shutil.rmtree(BUILD, ignore_errors=True)
    shutil.rmtree(BUILD_OUT, ignore_errors=True)

    print("[2/3] 运行 PyInstaller …")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(BUILD_OUT),
            "--workpath",
            str(BUILD),
            str(SPEC),
        ],
        cwd=str(ROOT),
    )
    if result.returncode != 0:
        print("打包失败")
        return result.returncode

    built = BUILD_OUT / APP_NAME
    if not (built / f"{APP_NAME}.exe").is_file():
        print(f"没有找到 exe：{built}")
        return 1

    target = DIST / APP_NAME
    if not sync_output(built, target):
        print(f"同步到 {target} 失败（可能被占用）")
        return 1
    shutil.rmtree(BUILD_OUT, ignore_errors=True)

    app_dir = DIST / APP_NAME
    exe_path = app_dir / f"{APP_NAME}.exe"
    if not exe_path.is_file():
        print(f"没有找到 exe：{exe_path}")
        return 1

    # 附带说明与许可证，方便拷给别人
    readme = ROOT / "README.md"
    if readme.is_file():
        shutil.copy2(readme, app_dir / "使用说明.md")
    license_file = ROOT / "LICENSE"
    if license_file.is_file():
        shutil.copy2(license_file, app_dir / "LICENSE")

    print("[3/3] 打压缩包 …")
    archive = make_zip(app_dir, DIST / f"{APP_NAME}-{version}-portable.zip")

    size_mb = sum(p.stat().st_size for p in app_dir.rglob("*") if p.is_file()) / 1024 / 1024
    print()
    print(f"exe     : {exe_path}")
    print(f"目录体积: {size_mb:.0f} MB")
    print(f"压缩包  : {archive}  {archive.stat().st_size / 1024 / 1024:.0f} MB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())