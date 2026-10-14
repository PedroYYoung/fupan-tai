# -*- coding: utf-8 -*-
"""指数周期均额回归测试"""
import json
import os
import tempfile

import pytest

from modules import compute, common


def _write_series(tmpdir, code, points):
    series_dir = os.path.join(tmpdir, "series")
    os.makedirs(series_dir, exist_ok=True)
    path = os.path.join(series_dir, f"index_amount_{code}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"key": f"index_amount_{code}", "name": "test", "unit": "亿", "points": points}, f)
    return path


@pytest.fixture
def patched_data_dir(monkeypatch):
    tmp = tempfile.mkdtemp()
    monkeypatch.setattr(common, "DATA_DIR", tmp)
    return tmp


def test_avg_index_amount_week(patched_data_dir):
    code = "sh000001"
    points = [
        {"date": "20261005", "value": 100},  # Mon
        {"date": "20261006", "value": 200},  # Tue
        {"date": "20261007", "value": 300},  # Wed
        {"date": "20261008", "value": 400},  # Thu
        {"date": "20261009", "value": 500},  # Fri
    ]
    _write_series(patched_data_dir, code, points)
    dates = ["20261005", "20261006", "20261007", "20261008", "20261009"]
    assert compute.avg_index_amount(code, "20261009", dates, "week") == 300.0


def test_avg_index_amount_month_uses_only_current_month(patched_data_dir):
    code = "sh000001"
    points = [
        {"date": "20260930", "value": 50},
        {"date": "20261005", "value": 100},
        {"date": "20261009", "value": 200},
    ]
    _write_series(patched_data_dir, code, points)
    dates = ["20260930", "20261005", "20261009"]
    assert compute.avg_index_amount(code, "20261009", dates, "month") == 150.0


def test_avg_index_amount_no_data_returns_none(patched_data_dir):
    code = "sh000001"
    _write_series(patched_data_dir, code, [])
    dates = ["20261009"]
    assert compute.avg_index_amount(code, "20261009", dates, "week") is None
