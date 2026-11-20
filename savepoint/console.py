"""控制台编码兼容。

Windows 的控制台默认不是 UTF-8（常见 cp936 / cp1252），直接 print 中文会抛
UnicodeEncodeError。这里在启动早期把标准输出切到 UTF-8，失败则退回替换字符，
保证程序不会因为打印日志而崩溃。
"""

# SPDX-License-Identifier: MIT

from __future__ import annotations

import sys


def ensure_utf8_console() -> None:
    """把 stdout / stderr 尽量切到 UTF-8。pythonw 下它们可能是 None。"""
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
                continue
            except (ValueError, OSError):
                pass
        # 老版本或已包装过的流：退而求其次，避免编码错误中断程序
        try:
            stream.errors = "replace"
        except (AttributeError, ValueError):
            pass