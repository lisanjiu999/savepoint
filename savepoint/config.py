"""全局配置、路径与用户设置。

打包成 exe 后 ``__file__`` 指向 PyInstaller 的临时解包目录，不能再用它推
数据目录，否则数据会写进临时目录、下次启动就没了。所以这里用
``sys.executable`` 判断冻结状态。

用户设置（数据目录、备份份数等）保存在程序目录旁的 ``savepoint.ini``，
这样便携版拷走整个文件夹设置也跟着走。
"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

import configparser
import os
import sys
from pathlib import Path

APP_NAME = "SavePoint"
APP_VERSION = "1.7.0"
# 任务栏分组要用稳定 ID，否则 Windows 会把程序归到 python 那一组
APP_ID = "SavePoint.App.1"

IS_FROZEN = bool(getattr(sys, "frozen", False))


def _app_root() -> Path:
    if IS_FROZEN:
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _asset_dir() -> Path:
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle) / "assets"
    return Path(__file__).resolve().parent / "assets"


APP_ROOT = _app_root()
SETTINGS_PATH = APP_ROOT / "savepoint.ini"
ASSET_DIR = _asset_dir()

LEGACY_INI = "pmtool.ini"
LEGACY_DATA = "pmtool-data"


def _migrate_legacy_layout() -> None:
    """从旧名字（pmtool）迁移到 SavePoint，只在目标不存在时改名。"""
    old_ini = APP_ROOT / LEGACY_INI
    if old_ini.is_file() and not SETTINGS_PATH.exists():
        try:
            old_ini.rename(SETTINGS_PATH)
        except OSError:
            pass
    old_data = APP_ROOT / LEGACY_DATA
    new_data = APP_ROOT / "savepoint-data"
    if old_data.is_dir() and not new_data.exists():
        try:
            old_data.rename(new_data)
        except OSError:
            pass


_migrate_legacy_layout()


def asset(name: str) -> Path:
    return ASSET_DIR / name


DEFAULTS: dict[str, str] = {
    "data_dir": "",  # 空 = 程序目录旁的 savepoint-data
    "backup_keep": "10",
    "backup_interval_hours": "6",
    "clipboard_clear_seconds": "30",
    "tray_enabled": "1",
    "close_to_tray": "1",
    "hotkey": "Ctrl+Alt+N",
    "onboarded": "0",
}

_settings: dict[str, str] = dict(DEFAULTS)


def load_settings() -> dict[str, str]:
    global _settings
    values = dict(DEFAULTS)
    if SETTINGS_PATH.is_file():
        parser = configparser.ConfigParser()
        try:
            # utf-8-sig：记事本另存的 ini 常带 BOM，不剥掉会把节名读成 "\ufeff[pmtool]"
            parser.read(SETTINGS_PATH, encoding="utf-8-sig")
        except (OSError, configparser.Error):
            parser = configparser.ConfigParser()
        if parser.has_section("savepoint"):
            for key, value in parser["savepoint"].items():
                if key in DEFAULTS:
                    values[key] = value
        elif parser.has_section("pmtool"):
            # 兼容旧版本的 ini 节名
            for key, value in parser["pmtool"].items():
                if key in DEFAULTS:
                    values[key] = value
    _settings = values
    return values


def save_settings(patch: dict[str, str] | None = None) -> None:
    global _settings
    if patch:
        _settings.update({k: str(v) for k, v in patch.items()})
    parser = configparser.ConfigParser()
    parser["savepoint"] = {k: str(v) for k, v in _settings.items()}
    try:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with SETTINGS_PATH.open("w", encoding="utf-8") as handle:
            parser.write(handle)
    except OSError:
        # 程序目录只读时（装到 Program Files）退化为不持久化，不影响运行
        pass


def get_setting(key: str, default: str | None = None) -> str:
    return _settings.get(key, DEFAULTS.get(key, default or ""))


def get_int(key: str, fallback: int = 0) -> int:
    try:
        return int(str(get_setting(key)).strip())
    except (TypeError, ValueError):
        return fallback


def get_bool(key: str, fallback: bool = False) -> bool:
    raw = str(get_setting(key)).strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return fallback


def set_setting(key: str, value: str | bool | int) -> None:
    if isinstance(value, bool):
        value = "1" if value else "0"
    save_settings({key: str(value)})


def clipboard_clear_seconds() -> int:
    return max(0, get_int("clipboard_clear_seconds", 30))


def backup_keep() -> int:
    return max(0, get_int("backup_keep", 10))


def backup_interval_hours() -> int:
    return max(0, get_int("backup_interval_hours", 6))


def default_data_dir() -> Path:
    return APP_ROOT / "savepoint-data"


def resolve_data_dir() -> Path:
    env = os.environ.get("SAVEPOINT_DATA_DIR", "").strip()
    if env:
        return Path(env).expanduser().resolve()
    configured = get_setting("data_dir").strip()
    if configured:
        return Path(configured).expanduser()
    return default_data_dir()


def is_first_run() -> bool:
    return not get_bool("onboarded", False)


load_settings()

DATA_DIR = resolve_data_dir()
DB_PATH = DATA_DIR / "projects.db"
SHOT_DIR = DATA_DIR / "screenshots"
THUMB_DIR = DATA_DIR / "thumbnails"
DOC_DIR = DATA_DIR / "documents"
BACKUP_DIR = DATA_DIR / "backups"
LOG_PATH = DATA_DIR / "savepoint.log"


def reload_paths() -> None:
    """改了数据目录之后重新计算路径（只在启动早期调用）。"""
    global DATA_DIR, DB_PATH, SHOT_DIR, THUMB_DIR, DOC_DIR, BACKUP_DIR, LOG_PATH
    DATA_DIR = resolve_data_dir()
    DB_PATH = DATA_DIR / "projects.db"
    SHOT_DIR = DATA_DIR / "screenshots"
    THUMB_DIR = DATA_DIR / "thumbnails"
    DOC_DIR = DATA_DIR / "documents"
    BACKUP_DIR = DATA_DIR / "backups"
    LOG_PATH = DATA_DIR / "savepoint.log"


THUMB_MAX = 560

RECENT_DAYS = 7
STALE_DAYS = 30

STATUS_LABELS = {
    "active": "进行中",
    "paused": "暂停",
    "done": "完成",
    "archived": "归档",
}
STATUS_ORDER = ["active", "paused", "done", "archived"]

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tif", ".tiff"}


def ensure_dirs() -> None:
    for folder in (DATA_DIR, SHOT_DIR, THUMB_DIR, DOC_DIR, BACKUP_DIR):
        folder.mkdir(parents=True, exist_ok=True)