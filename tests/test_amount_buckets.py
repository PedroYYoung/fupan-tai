# -*- coding: utf-8 -*-
"""成交额分档聚合逻辑回归测试（基于 spot_df['amount'] 元）"""
import pandas as pd
import pytest

from modules import compute


def _make_spot(amounts_yi):
    """amounts_yi: 亿元列表 → spot_df['amount'] 为元"""
    rows = []
    for i, a in enumerate(amounts_yi):
        rows.append({
            "code": f"sh{i:06d}",
            "name": f"stock{i}",
            "amount": a * 1e8,
            "mktcap": 1e10,
        })
    return pd.DataFrame(rows)


def test_amount_buckets_labels_and_counts():
    amounts = [150, 80, 60, 30, 15, 8, 3, 0.5]  # 覆盖全部 7 档
    df = _make_spot(amounts)
    bkts = compute.amount_buckets(df)
    labels = [b["label"] for b in bkts]
    assert labels == ["100亿+", "50-100亿", "20-50亿", "10-20亿", "5-10亿", "1-5亿", "<1亿"]
    counts = {b["label"]: b["count"] for b in bkts}
    assert counts["100亿+"] == 1
    assert counts["50-100亿"] == 2
    assert counts["20-50亿"] == 1
    assert counts["10-20亿"] == 1
    assert counts["5-10亿"] == 1
    assert counts["1-5亿"] == 1
    assert counts["<1亿"] == 1


def test_amount_buckets_pct_sums_to_100():
    amounts = [150, 80, 60, 30, 15, 8, 3, 0.5]
    df = _make_spot(amounts)
    bkts = compute.amount_buckets(df)
    assert round(sum(b["pct"] for b in bkts), 1) == 100.0


def test_amount_buckets_empty_returns_zero_pct():
    df = _make_spot([])
    bkts = compute.amount_buckets(df)
    assert all(b["count"] == 0 and b["pct"] == 0 for b in bkts)


def test_amount_buckets_boundary_inclusive():
    # 10亿正好在 10-20 档（左闭右开）
    df = _make_spot([10, 5, 1, 0.1])
    bkts = {b["label"]: b["count"] for b in compute.amount_buckets(df)}
    assert bkts["10-20亿"] == 1
    assert bkts["5-10亿"] == 1
    assert bkts["1-5亿"] == 1
    assert bkts["<1亿"] == 1


def test_amount_buckets_hundred_billion_plus_open():
    df = _make_spot([100, 200, 100])
    bkts = {b["label"]: b["count"] for b in compute.amount_buckets(df)}
    assert bkts["100亿+"] == 3
