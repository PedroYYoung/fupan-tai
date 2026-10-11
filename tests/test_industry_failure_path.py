# -*- coding: utf-8 -*-
"""行业板块失败处理回归测试：失败时保留旧数据，不用空数据覆盖。"""
import json
import os
import tempfile

import pytest

import build as build_main
from modules import industry_mod


def test_industry_module_returns_none_on_failure(monkeypatch):
    """行业接口异常时应返回 None，而不是抛异常或返回空列表。"""
    import akshare as ak
    monkeypatch.setattr(ak, "stock_board_industry_name_em",
                        lambda *a, **k: (_ for _ in ()).throw(ConnectionError("东财挂了")))
    result = industry_mod.get_industry_daily(total_amount=10000.0)
    assert result is None


def test_build_inherits_industry_from_previous_day(monkeypatch, tmp_path):
    """当日行业失败时，build.py 应从上一交易日 daily 文件继承行业数据。"""
    prev_date = "20261008"
    target_date = "20261009"
    prev_industry = {"top10_up": [{"name": "证券", "change": 2.5, "amount": 120.0, "ratio": 1.2}],
                     "top10_down": [{"name": "煤炭", "change": -1.5, "amount": 80.0, "ratio": 0.8}]}

    # 构造最小数据目录
    data_dir = tmp_path / "public" / "data"
    daily_dir = data_dir / "daily"
    daily_dir.mkdir(parents=True)
    meta_dir = data_dir / "meta"
    meta_dir.mkdir(parents=True)
    series_dir = data_dir / "series"
    series_dir.mkdir(parents=True)

    # 上一交易日 daily 文件
    with open(daily_dir / f"{prev_date}.json", "w", encoding="utf-8") as f:
        json.dump({"trade_date": prev_date, "industry": prev_industry,
                   "overview": {}, "index_volume": [], "widebase": [],
                   "concentration": {}, "liquidity": {}, "emotion": {}, "sparklines": {}}, f)

    monkeypatch.setattr(build_main, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(build_main.calendar_mod, "get_trade_dates",
                        lambda: ["20261007", prev_date, target_date])
    monkeypatch.setattr(build_main.spot_mod, "get_spot",
                        lambda d: _make_min_spot_df())
    monkeypatch.setattr(build_main.index_mod, "get_index_amount", lambda c, d: None)
    monkeypatch.setattr(build_main.margin_mod, "get_margin", lambda d: None)
    monkeypatch.setattr(build_main.zt_mod, "get_limit_pools", lambda d, spot: (0, 0, [], []))
    monkeypatch.setattr(build_main.compute, "microcap_proxy_amount", lambda spot: (0.0, 0))
    monkeypatch.setattr(build_main.compute, "over_10e", lambda spot: (0, 0.0, 0))
    monkeypatch.setattr(build_main.compute, "concentration", lambda spot: None)
    monkeypatch.setattr(build_main.compute, "update_series", lambda *a, **k: None)
    monkeypatch.setattr(build_main.compute, "pctile", lambda vals, v: None)
    monkeypatch.setattr(build_main.compute, "rank_of", lambda vals, v: None)
    monkeypatch.setattr(build_main.compute, "append_bucket_series", lambda *a, **k: None)
    monkeypatch.setattr(build_main.compute, "build_index_agg", lambda: None)
    monkeypatch.setattr(build_main, "atomic_write_json", lambda p, o: _write_json(p, o))

    # 行业模块失败
    monkeypatch.setattr(build_main.industry_mod, "get_industry_daily", lambda total: None)

    build_main.build_one(target_date, ["20261007", prev_date, target_date])

    with open(daily_dir / f"{target_date}.json", encoding="utf-8") as f:
        daily = json.load(f)
    assert daily["industry"] == prev_industry


def _make_min_spot_df():
    import pandas as pd
    return pd.DataFrame({
        "code": ["600000"], "name": ["浦发银行"], "close": [10.0],
        "change_pct": [0.0], "amount": [1e8], "mktcap": [1e10], "float_mktcap": [1e10]
    })


def _write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
