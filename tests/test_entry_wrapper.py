# -*- coding: utf-8 -*-
"""入口单一来源回归：``web_dashboard.py`` 必须是指向 ``web.py`` 的符号链接。

背景：入口与实现以 symlink 共享同一份代码（测试 import web、生产跑
web_dashboard，二者同一文件）。风险是有人替换成"整文件副本"（两边漂移），
或在 Windows 上以 core.symlinks=false 检出（链接变成文本文件，入口坏掉）。
本测试钉住"链接存在且指向正本"。
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / 'web_dashboard.py'
CANONICAL = ROOT / 'web.py'


def test_entry_is_symlink():
    assert ENTRY.exists(), '生产入口缺失'
    assert os.path.islink(ENTRY), (
        'web_dashboard.py 必须是指向 web.py 的符号链接；'
        '若是普通文件（副本），测试与生产将覆盖两套代码'
    )


def test_entry_points_to_canonical_module():
    assert ENTRY.resolve() == CANONICAL.resolve()


def test_canonical_module_is_not_replaced_by_stub():
    assert len(CANONICAL.read_text(encoding='utf-8').splitlines()) > 1000
