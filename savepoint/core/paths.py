"""小的格式化与路径工具。"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path


def parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None


def human_time(value: str, *, with_year: bool = False) -> str:
    dt = parse_iso(value)
    if dt is None:
        return value
    if with_year:
        return dt.strftime("%Y-%m-%d %H:%M")
    if dt.year == datetime.now().year:
        return dt.strftime("%m-%d %H:%M")
    return dt.strftime("%Y-%m-%d %H:%M")


def relative_time(value: str) -> str:
    dt = parse_iso(value)
    if dt is None:
        return ""
    delta = datetime.now() - dt
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "刚刚"
    if seconds < 60:
        return "刚刚"
    if seconds < 3600:
        return f"{seconds // 60} 分钟前"
    if seconds < 86400:
        return f"{seconds // 3600} 小时前"
    days = seconds // 86400
    if days < 30:
        return f"{days} 天前"
    if days < 365:
        return f"{days // 30} 个月前"
    return f"{days // 365} 年前"


def human_size(num: int) -> str:
    size = float(num)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def folder_state(path_text: str) -> tuple[bool, str]:
    """返回 (目录是否存在, 提示文本)。"""
    if not path_text.strip():
        return False, "未设置路径"
    try:
        path = Path(path_text)
        if path.is_dir():
            return True, ""
        if path.exists():
            return False, "路径不是文件夹"
        return False, "路径不存在"
    except OSError:
        return False, "路径无效"


def _integrity_level() -> str:
    """当前进程的完整性级别：Low / Medium / High / System / Unknown。"""
    try:
        import ctypes
        from ctypes import wintypes

        advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        advapi32.OpenProcessToken.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.HANDLE),
        ]
        advapi32.OpenProcessToken.restype = wintypes.BOOL
        advapi32.GetTokenInformation.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.c_void_p,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
        ]
        advapi32.GetTokenInformation.restype = wintypes.BOOL
        advapi32.ConvertSidToStringSidW.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_wchar_p),
        ]

        class SidAndAttributes(ctypes.Structure):
            _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", wintypes.DWORD)]

        class TokenMandatoryLabel(ctypes.Structure):
            _fields_ = [("Label", SidAndAttributes)]

        token = wintypes.HANDLE()
        if not advapi32.OpenProcessToken(
            kernel32.GetCurrentProcess(), 0x0008, ctypes.byref(token)
        ):
            return "Unknown"
        try:
            buffer = ctypes.create_string_buffer(256)
            size = wintypes.DWORD()
            if not advapi32.GetTokenInformation(
                token, 25, buffer, 256, ctypes.byref(size)
            ):
                return "Unknown"
            label = ctypes.cast(buffer, ctypes.POINTER(TokenMandatoryLabel)).contents
            text = ctypes.c_wchar_p()
            if not advapi32.ConvertSidToStringSidW(label.Label.Sid, ctypes.byref(text)):
                return "Unknown"
            sid = text.value or ""
        finally:
            kernel32.CloseHandle(token)

        mapping = {
            "-4096": "Low",
            "-8192": "Medium",
            "-12288": "High",
            "-16384": "System",
        }
        for suffix, name in mapping.items():
            if sid.endswith(suffix):
                return name
        return sid
    except Exception:  # noqa: BLE001 - 非 Windows 或调用失败
        return "Unknown"


def is_low_integrity() -> bool:
    """当前进程是否运行在低完整性（受限）环境。"""
    return _integrity_level() == "Low"


def integrity_fix_command() -> str:
    """返还可以把程序目录标签改回 Medium 的命令。"""
    import sys

    if getattr(sys, "frozen", False):
        folder = Path(sys.executable).resolve().parent
    else:
        folder = Path(__file__).resolve().parent.parent.parent
    return f'icacls "{folder}" /setintegritylevel (OI)(CI)Medium /T'


def open_in_explorer(path_text: str) -> None:
    """在资源管理器里打开目录。

    受限环境（低完整性进程、应用容器、带 UI 限制的作业）会拒绝 ShellExecute
    并抛 WinError 5，而且即使 explorer.exe 能起来也不会显示窗口。所以先按
    三级回退尝试，低完整性时直接给出可操作的提示。
    """
    target = str(Path(path_text))

    try:
        os.startfile(target)  # noqa: S606 - Windows 专用
        return
    except OSError as exc:
        first_error = exc

    if _integrity_level() == "Low":
        raise OSError(
            "当前程序所在的文件夹被标成了「低完整性」，Windows 会以受限权限运行它，"
            "因此不允许它唤起资源管理器。\n\n"
            "两种解决办法：\n"
            "1. 把压缩包解压到一个普通目录（例如 C:\\Apps\\SavePoint）再运行；\n"
            "2. 或在普通 PowerShell 里执行：\n"
            f"{integrity_fix_command()}"
        ) from first_error

    try:
        subprocess.Popen(["explorer.exe", target], close_fds=True)
        return
    except OSError as exc:
        first_error = exc

    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", target],
            close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return
    except OSError as exc:
        raise exc from first_error