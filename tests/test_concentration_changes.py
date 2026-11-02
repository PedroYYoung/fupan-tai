# -*- coding: utf-8 -*-
"""个股集中度 Top10/Top20/Top50「较上一有效交易日变化」回归测试。

背景
----
集中度累计占比（top10_total / top20_cum_pct / top50_cum_pct）依赖全市场实时快照。
上一交易日快照可能因历史重建 / 源不可用而缺失（如 20261019 全为 None），
此时若只按「上一交易日」取基准，变化会恒为 None；正确做法是向前回溯到
最近一个仍有有效集中度值的真实快照，并记录真实比较日期，不冒充「昨日」。

锁定契约
--------
1. 上一交易日有值 → 变化 = 当日 − 上一交易日，比较日期 = 上一交易日
2. 上一交易日缺失、更早有值 → 向前回溯，变化 = 当日 − 更早日，比较日期 = 更早日
3. 向前回溯不到任何有效值 → 变化 = None、比较日期 = None（绝不按 0 计）
4. 变化是「百分比之间的差值」，单位为百分点（前端用 ppDelta 渲染「个百分点」）
"""
import json
import os

import pandas as pd
import pytest

import build as build_main
from modules import common


DATES = ["20261014", "20261015", "20261016", "20261019", "20261020"]
LATEST = "20261020"          # 最近已收盘交易日（实时快照可用）
PREV = "20261019"            # 上一交易日（快照集中度缺失的场景）
EARLIER = "20261016"         # 更早仍有集中度值的交易日

# 与真实会话无关的「当前实时」夹具：每只 100 亿、共 1000 只。
# 每只成交额相等 → 单只占比 0.1%，故 top10_total=1.0 / top20_cum_pct=2.0 / top50_cum_pct=5.0
_SPOT_AMOUNT = 1e10
_SPOT_N = 1000


def _fake_spot() -> pd.DataFrame:
    codes = [f"{600000 + i:06d}" for i in range(_SPOT_N)]
    return pd.DataFrame({
        "code": codes,
        "name": [f"股票{i}" for i in range(_SPOT_N)],
        "close": [10.0] * _SPOT_N,
        "change_pct": [5.0] * _SPOT_N,
        "amount": [float(_SPOT_AMOUNT)] * _SPOT_N,
        "mktcap": [1e11] * _SPOT_N,
        "float_mktcap": [8e10] * _SPOT_N,
    })


def _prepare_env(monkeypatch, tmp_path):
    data_dir = tmp_path / "data"
    for sub in ("daily", "series", "meta"):
        os.makedirs(os.path.join(str(data_dir), sub), exist_ok=True)
    monkeypatch.setattr(build_main, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(common, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(common, "REPO_ROOT", str(tmp_path))

    monkeypatch.setattr(build_main.spot_mod, "get_spot", lambda date=None: _fake_spot())
    monkeypatch.setattr(build_main.index_mod, "get_index_amount_resilient",
                        lambda code, d, last_known=None: (1000.0, d, ""))
    monkeypatch.setattr(build_main.index_mod, "get_index_change_pct", lambda c, d: 1.23)
    monkeypatch.setattr(build_main.index_mod, "get_index_close", lambda c, d: 3000.0)
    monkeypatch.setattr(build_main.index_mod, "get_index_ytd_pct", lambda c, d, dates=None: None)
    monkeypatch.setattr(build_main.margin_mod, "get_margin", lambda d: (None, None))
    monkeypatch.setattr(build_main.industry_mod, "get_industry_daily",
                        lambda total_amount, date=None: {"top10_up": [], "top10_down": [],
                                                         "source": "eastmoney", "note": ""})
    monkeypatch.setattr(build_main.industry_mod, "get_industry_week_rank", lambda d, ds: None)
    monkeypatch.setattr(build_main.industry_mod, "load_industry_cache", lambda: (None, None))
    monkeypatch.setattr(build_main.zt_mod, "fetch_pools",
                        lambda date, spot_df=None: {"lu": 0, "ld": 0, "lu_rows": [], "ld_rows": [],
                                                    "lu_ok": True, "ld_ok": True,
                                                    "lu_src": "eastmoney", "ld_src": "eastmoney",
                                                    "ld_reason": None})
    monkeypatch.setattr(build_main, "last_closed_trade_date", lambda dates: LATEST)
    return str(data_dir)


def _write(data_dir, date, concentration):
    obj = {
        "trade_date": date,
        "overview": {"total_amount": 10000.0, "over_10e_count": 100, "stock_count": 1000},
        "concentration": concentration,
        "liquidity": {"over_10e_count": 100, "mktcap_buckets": []},
        "emotion": {},
    }
    with open(os.path.join(data_dir, "daily", f"{date}.json"), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def _read(data_dir, date):
    with open(os.path.join(data_dir, "daily", f"{date}.json"), encoding="utf-8") as f:
        return json.load(f)


def _conc(top10, top20, top50):
    return {"top_n": [10, 20, 50], "top10": [], "top20": [], "top50": [],
            "top20_cum_pct": top20, "top50_cum_pct": top50,
            "top10_total": top10, "top10_total_pctile_hist": None}


def test_change_uses_prev_trading_day(monkeypatch, tmp_path):
    """上一交易日有值 → 变化 = 当日 − 上一交易日，比较日期 = 上一交易日。"""
    data_dir = _prepare_env(monkeypatch, tmp_path)
    _write(data_dir, PREV, _conc(0.5, 1.5, 4.0))

    build_main.build_one(LATEST, DATES)
    c = _read(data_dir, LATEST)["concentration"]

    assert c["top10_total"] == 1.0
    assert c["top10_change"] == pytest.approx(0.5)
    assert c["top20_change"] == pytest.approx(0.5)
    assert c["top50_change"] == pytest.approx(1.0)
    assert c["concentration_change_date"] == PREV


def test_change_falls_back_to_earlier_valid_day(monkeypatch, tmp_path):
    """上一交易日缺失、更早有值 → 向前回溯，且记录真实比较日期。"""
    data_dir = _prepare_env(monkeypatch, tmp_path)
    # 上一交易日：集中度缺失（历史重建 / 源不可用）
    _write(data_dir, PREV, {"top_n": [10, 20, 50], "top10": [], "top20": [], "top50": [],
                            "top20_cum_pct": None, "top50_cum_pct": None,
                            "top10_total": None, "top10_total_pctile_hist": None})
    # 更早交易日：仍有集中度值
    _write(data_dir, EARLIER, _conc(0.6, 1.8, 4.5))

    build_main.build_one(LATEST, DATES)
    c = _read(data_dir, LATEST)["concentration"]

    assert c["top10_change"] == pytest.approx(0.4)    # 1.0 - 0.6
    assert c["top20_change"] == pytest.approx(0.2)    # 2.0 - 1.8
    assert c["top50_change"] == pytest.approx(0.5)    # 5.0 - 4.5
    assert c["concentration_change_date"] == EARLIER


def test_change_none_when_no_baseline(monkeypatch, tmp_path):
    """向前回溯不到任何有效值 → 变化与比较日期均为 None（绝不按 0 计）。"""
    data_dir = _prepare_env(monkeypatch, tmp_path)
    # 不写任何历史快照 → 回溯不到基准

    build_main.build_one(LATEST, DATES)
    c = _read(data_dir, LATEST)["concentration"]

    assert c["top10_total"] == 1.0
    assert c["top10_change"] is None
    assert c["top20_change"] is None
    assert c["top50_change"] is None
    assert c["concentration_change_date"] is None
