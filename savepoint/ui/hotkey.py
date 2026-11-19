"""全局热键（RegisterHotKey + 原生事件过滤）。"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

import ctypes
from ctypes import wintypes

from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication

WM_HOTKEY = 0x0312
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_MODIFIERS = {
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "meta": MOD_WIN,
}


class _MSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", wintypes.HWND),
        ("message", wintypes.UINT),
        ("wParam", wintypes.WPARAM),
        ("lParam", wintypes.LPARAM),
        ("time", wintypes.DWORD),
        ("pt", wintypes.POINT),
    ]


def parse_hotkey(spec: str) -> tuple[int, int] | None:
    """把 "Ctrl+Alt+N" 解析成 (修饰键, 虚拟键码)。"""
    parts = [part.strip().lower() for part in spec.split("+") if part.strip()]
    if not parts:
        return None
    modifiers = 0
    key = None
    for part in parts:
        if part in _MODIFIERS:
            modifiers |= _MODIFIERS[part]
            continue
        key = part
    if not key:
        return None
    if len(key) == 1:
        if key.isalpha():
            vk = ord(key.upper())
        elif key.isdigit():
            vk = ord(key)
        else:
            return None
    elif key.startswith("f") and key[1:].isdigit():
        number = int(key[1:])
        if not 1 <= number <= 24:
            return None
        vk = 0x70 + number - 1
    elif key in ("space", "enter", "tab"):
        vk = {"space": 0x20, "enter": 0x0D, "tab": 0x09}[key]
    else:
        return None
    return modifiers, vk


class GlobalHotkey(QAbstractNativeEventFilter):
    """注册一个系统级热键。

    Windows 的 WM_HOTKEY 会发给注册它的线程消息队列，这里用原生事件过滤
    截获，不需要自己造窗口。
    """

    def __init__(self, callback) -> None:
        super().__init__()
        self._callback = callback
        self._hotkey_id = 0x504D  # 'PM'
        self._registered = False
        self._user32 = ctypes.WinDLL("user32", use_last_error=True)

    def register(self, spec: str) -> bool:
        parsed = parse_hotkey(spec)
        if parsed is None:
            return False
        modifiers, vk = parsed
        self.unregister()
        ok = self._user32.RegisterHotKey(None, self._hotkey_id, modifiers | MOD_NOREPEAT, vk)
        self._registered = bool(ok)
        if self._registered:
            app = QCoreApplication.instance()
            if app is not None:
                app.installNativeEventFilter(self)
        return self._registered

    def unregister(self) -> None:
        if self._registered:
            try:
                self._user32.UnregisterHotKey(None, self._hotkey_id)
            except OSError:
                pass
            app = QCoreApplication.instance()
            if app is not None:
                try:
                    app.removeNativeEventFilter(self)
                except RuntimeError:
                    pass
            self._registered = False

    def is_registered(self) -> bool:
        return self._registered

    def nativeEventFilter(self, event_type, message):  # noqa: ANN001, N802 - Qt 命名
        if event_type not in (b"windows_generic_MSG", "windows_generic_MSG"):
            return False
        try:
            address = message if isinstance(message, int) else int(message)
            msg = _MSG.from_address(address)
        except (TypeError, ValueError):
            return False
        if msg.message == WM_HOTKEY and int(msg.wParam) == self._hotkey_id:
            self._callback()
            return True
        return False