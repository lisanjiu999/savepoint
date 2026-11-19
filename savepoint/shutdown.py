"""进程退出收尾。

PySide6 在解释器 finalize 阶段析构 Qt 对象的顺序不确定，实测偶发
访问违例（0xC0000005）。这里先把顶层窗口连同 C++ 对象一起删掉，
再直接结束进程，绕开不确定的析构顺序。
"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

import os
import sys

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication


def hard_exit(code: int = 0) -> None:
    app = QApplication.instance()
    if app is not None:
        for widget in QApplication.topLevelWidgets():
            try:
                widget.close()
                widget.deleteLater()
            except RuntimeError:
                pass
        try:
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
        except RuntimeError:
            pass
    # pythonw 下 sys.stdout / sys.stderr 是 None，不能直接 flush
    for stream in (sys.stdout, sys.stderr):
        try:
            if stream is not None:
                stream.flush()
        except Exception:  # noqa: BLE001
            pass
    os._exit(code)