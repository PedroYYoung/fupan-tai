# -*- coding: utf-8 -*-
"""流动性结构「较上一有效交易日变化」回归测试。

根因：历史日（如 2026-10-19）重建时没有 existing 快照可沿用，
liquidity 分档表被写成空列表；导致下一交易日（2026-10-20）无法
基于上一交易日计算 count_change / pct_change，括号内变化消失。
"""
import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts")))

import repair_liquidity_changes as repair
from modules import calendar_mod, common


def _make_bucket(label, count, pct):
    return {"label": label, "count": count, "pct": pct}


def test_attach_changes_with_prev():
    prev = [_make_bucket("A", 10, 5.0), _make_bucket("B", 20, 10.0)]
    cur = [_make_bucket("A", 12, 5.5), _make_bucket("B", 18, 9.5)]
    out = repair._attach_changes(cur, prev)
    assert out[0]["count_change"] == 2
    assert out[0]["pct_change"] == 0.5
    assert out[1]["count_change"] == -2
    assert out[1]["pct_change"] == -0.5


def test_attach_changes_without_prev():
    cur = [_make_bucket("A", 12, 5.5)]
    out = repair._attach_changes(cur, None)
    assert out[0]["count_change"] is None
    assert out[0]["pct_change"] is None


def test_repair_skips_empty_prev_and_uses_earlier_snapshot(tmp_path, monkeypatch):
    """中间交易日 liquidity 为空时，目标日应向前回溯到更早有效快照计算变化。"""
    d = tmp_path / "data"
    for sub in ("daily", "series", "meta"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(common, "DATA_DIR", str(d), raising=False)

    # 使用虚构日期，避免污染真实 daily 文件
    dates = ["20990114", "20990115", "20990116", "20990117", "20990120"]

    def make_daily(date, buckets):
        return {"trade_date": date, "overview": {}, "liquidity": {"mktcap_buckets": buckets}}

    buckets_base = [_make_bucket("<50亿", 100, 50.0), _make_bucket("50-100亿", 50, 25.0)]
    buckets_today = [_make_bucket("<50亿", 110, 52.0), _make_bucket("50-100亿", 45, 22.0)]

    repair._save_daily("20990114", make_daily("20990114", buckets_base))
    repair._save_daily("20990117", make_daily("20990117", []))  # 重建后无分档
    repair._save_daily("20990120", make_daily("20990120", buckets_today))

    monkeypatch.setattr(calendar_mod, "get_trade_dates", lambda: dates, raising=False)

    repair.repair("20990120")

    s20 = json.load(open(d / "daily" / "20990120.json", encoding="utf-8"))
    b = s20["liquidity"]["mktcap_buckets"]
    assert b[0]["count_change"] == 10   # 110 - 100
    assert b[0]["pct_change"] == 2.0    # 52.0 - 50.0
    assert b[1]["count_change"] == -5   # 45 - 50
    assert b[1]["pct_change"] == -3.0


def test_repair_keeps_null_when_no_baseline(tmp_path, monkeypatch):
    """向前回溯不到任何有效分档表时，变化字段保持 null。"""
    d = tmp_path / "data"
    for sub in ("daily", "series", "meta"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(common, "DATA_DIR", str(d), raising=False)

    dates = ["20990120"]
    monkeypatch.setattr(calendar_mod, "get_trade_dates", lambda: dates, raising=False)

    buckets = [_make_bucket("A", 10, 5.0)]
    repair._save_daily("20990120", {"trade_date": "20990120", "overview": {},
                                    "liquidity": {"mktcap_buckets": buckets}})

    repair.repair("20990120")

    s = json.load(open(d / "daily" / "20990120.json", encoding="utf-8"))
    assert s["liquidity"]["mktcap_buckets"][0]["count_change"] is None
    assert s["liquidity"]["mktcap_buckets"][0]["pct_change"] is None
