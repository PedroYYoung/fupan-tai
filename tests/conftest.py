# -*- coding: utf-8 -*-
import os
import sys

import pytest

# 让测试可以直接 import scripts/ 下的 build.py 与 modules/*
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))


@pytest.fixture(autouse=True)
def _isolate_industry_cache(tmp_path, monkeypatch):
    """把行业缓存重定向到临时目录，避免测试把构造的假数据写进 scripts/_cache。"""
    try:
        from modules import industry_mod
    except Exception:  # noqa: BLE001 — 依赖缺失时不影响其它测试
        return
    monkeypatch.setattr(industry_mod, "_CACHE_PATH",
                        str(tmp_path / "industry_last.json"), raising=False)


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path, monkeypatch):
    """把「写数据」的落点重定向到临时目录。

    背景：build_one() / heal_recent_limit_pools() 的测试会真实调用 compute.update_series，
    此前直接写进仓库的 public/data/series —— 一次 `--date 20261010`（周六，
    东财对非交易日返回「0 家」且不报错）就在真实序列里留下了一个 0 值污染点。
    测试只允许验证逻辑，不允许改写真实数据。

    注意：断言「真实数据契约」的测试（test_series_integrity）在模块顶层
    `from modules.common import DATA_DIR`，绑定的是真实路径，不受此 fixture 影响。
    """
    from modules import common

    d = tmp_path / "data"
    for sub in ("daily", "series", "meta"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(common, "DATA_DIR", str(d), raising=False)

    b = sys.modules.get("build")
    if b is not None and hasattr(b, "DATA_DIR"):
        monkeypatch.setattr(b, "DATA_DIR", str(d), raising=False)
