# -*- coding: utf-8 -*-
"""成交额≥10亿股票市值结构回归测试"""
import pandas as pd
import pytest

from modules import compute


def _make_spot(marketcaps_yi, amounts_yi):
    rows = []
    for i, (m, a) in enumerate(zip(marketcaps_yi, amounts_yi)):
        rows.append({
            "code": f"sh{i:06d}",
            "name": f"s{i}",
            "amount": a * 1e8,
            "mktcap": m * 1e8,
        })
    return pd.DataFrame(rows)


def test_over_10e_marketcap_buckets_counts_and_pcts():
    # 6 只活跃股（>=10亿），覆盖 6 个市值档
    m = [1200, 800, 300, 150, 80, 30]
    a = [15, 12, 20, 11, 10.5, 10]
    df = _make_spot(m, a)
    bkts = compute.over_10e_marketcap_buckets(df)
    labels = [b["label"] for b in bkts]
    assert labels == ["1000亿以上", "500-1000亿", "200-500亿", "100-200亿", "50-100亿", "50亿以下"]
    assert sum(b["count"] for b in bkts) == 6
    assert abs(sum(b["pct"] for b in bkts) - 100.0) < 0.5
    by_label = {b["label"]: b for b in bkts}
    assert by_label["1000亿以上"]["count"] == 1
    assert by_label["50亿以下"]["count"] == 1


def test_over_10e_marketcap_value_buckets_sums_total():
    m = [1200, 800, 300, 150, 80, 30]
    a = [15, 12, 20, 11, 10.5, 10]
    df = _make_spot(m, a)
    count_bkts = compute.over_10e_marketcap_buckets(df)
    value_bkts = compute.over_10e_marketcap_value_buckets(df)
    total_value = sum(b["total_value"] for b in value_bkts)
    assert round(total_value, 2) == round(sum(m), 2)
    assert abs(sum(b["pct"] for b in value_bkts) - 100.0) < 0.5
    for cb, vb in zip(count_bkts, value_bkts):
        assert cb["label"] == vb["label"]
        assert cb["count"] == vb["count"]


def test_over_10e_filters_out_below_10e():
    df = _make_spot([1200, 30], [9.9, 15])
    bkts = compute.over_10e_marketcap_buckets(df)
    assert sum(b["count"] for b in bkts) == 1


def test_over_10e_marketcap_buckets_missing_columns():
    df = pd.DataFrame([{"code": "sh000001", "amount": 1e9}])
    bkts = compute.over_10e_marketcap_buckets(df)
    assert all(b["count"] == 0 and b["pct"] == 0 for b in bkts)
