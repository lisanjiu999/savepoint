"""开发模式的启动引导：让注册表自启能在任意工作目录下 import 到 savepoint。"""
# SPDX-License-Identifier: MIT

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from savepoint.main import run  # noqa: E402

run()