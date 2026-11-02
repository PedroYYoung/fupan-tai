# -*- coding: utf-8 -*-
"""两市成交额口径回归测试：指数口径优先，降级时回退快照口径（绝不写入缺失值）。"""
import pandas as pd

import build as build_main

D = "20261016"


def _spot(total_yi):
    return pd.DataFrame({"code": ["600000", "000001"],
                         "name": ["浦发银行", "平安银行"],
                         "close": [10.0, 12.0], "change_pct": [0.0, 0.0],
                         "amount": [total_yi * 1e8 / 2, total_yi * 1e8 / 2],
                         "mktcap": [1e11, 1e11], "float_mktcap": [1e11, 1e11]})


def _row(code, amount, amount_date=D, note=""):
    return {"code": code, "name": code, "amount": amount,
            "amount_date": amount_date, "note": note}


def test_prefers_index_caliber_when_both_real():
    rows = [_row("sh000001", 7324.75), _row("sz399001", 8229.46)]
    assert build_main._resolve_total_amount(_spot(15552.55), rows, D) == 15554.21


def test_divergence_still_uses_index_caliber():
    """快照口径偏离 >5% 时仍采用指数口径（口径唯一），但会告警。"""
    rows = [_row("sh000001", 6624.92), _row("sz399001", 7519.11)]
    assert build_main._resolve_total_amount(_spot(16296.84), rows, D) == 14144.03


def test_falls_back_to_spot_when_index_degraded():
    rows = [_row("sh000001", 6624.92, amount_date="20261015"),
            _row("sz399001", 7519.11, amount_date="20261015")]
    assert build_main._resolve_total_amount(_spot(16296.84), rows, D) == 16296.84


def test_falls_back_to_spot_when_note_present():
    rows = [_row("sh000001", 6624.92, note="last_known"),
            _row("sz399001", 7519.11)]
    assert build_main._resolve_total_amount(_spot(16000.0), rows, D) == 16000.0


def test_falls_back_to_spot_when_amount_missing():
    rows = [_row("sh000001", None), _row("sz399001", 7519.11)]
    assert build_main._resolve_total_amount(_spot(15000.0), rows, D) == 15000.0


def test_falls_back_to_spot_when_index_rows_absent():
    assert build_main._resolve_total_amount(_spot(15000.0), [], D) == 15000.0
