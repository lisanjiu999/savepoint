"""开机自启（HKCU Run 键，不需要管理员权限）。"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

import sys
from pathlib import Path

import winreg

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "SavePoint"
LEGACY_VALUE_NAME = "PmtoolProjectManager"


def _command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    exe = pythonw if pythonw.is_file() else Path(sys.executable)
    launcher = Path(__file__).resolve().parent.parent.parent / "scripts" / "dev_launch.py"
    return f'"{exe}" "{launcher}"'


def is_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return bool(value)
    except OSError:
        return False


def set_enabled(enabled: bool) -> bool:
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enabled:
                winreg.SetValueEx(key, VALUE_NAME, 0, winreg.REG_SZ, _command())
            else:
                for name in (VALUE_NAME, LEGACY_VALUE_NAME):
                    try:
                        winreg.DeleteValue(key, name)
                    except FileNotFoundError:
                        pass
        return True
    except OSError:
        return False