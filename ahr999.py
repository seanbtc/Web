# -*- coding: utf-8 -*-
"""兼容层：AHR999 实现已迁移到 ``commons.ahr999``（Web 与 AutoDCA 共用）。

保留本模块是为了让既有 ``from ahr999 import compute_ahr999`` 等导入继续工作；
新代码请直接 ``from commons.ahr999 import ...``。
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from commons.ahr999 import *  # noqa: F401,F403
from commons.ahr999 import __all__  # noqa: F401
