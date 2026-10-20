# -*- coding: utf-8 -*-
"""实时行情日期保护回归测试（根因：实时 spot 接口不支持历史日期）。

背景
----
全市场快照接口（东财 stock_zh_a_spot_em / efinance / 腾讯批量）都不接受日期参数，
永远返回**当前会话**行情。此前用 `--date 20261014` 之类的命令重跑历史交易日时，
当前会话行情被直接写进历史快照，导致 20261009 / 20261013 / 20261014 三份快照的
集中度、流动性分档等字段实际是「后一个交易日」的数据（已用 baostock 逐只核验）。

本测试锁定修复后的契约
----------------------
1. 目标日不是最近已收盘交易日 → 不得调用实时快照接口，不得写入实时派生字段
2. 目标日不是最近已收盘交易日 → 只用「按日期查询」的可靠源更新历史数据
3. 旧快照已有全市场字段 → 原样沿用（不清空、不改写）
4. 旧快照已标记不可用 → 重跑也不得复活
5. 不可用时一律 None / 空列表，绝不写 0 冒充真实值
6. 最近已收盘交易日的正常实时流程不受影响

全部使用 mock/fixture，不产生任何真实网络请求，也不写产品数据目录。
"""
import json
import os

import pandas as pd
import pytest

import build as build_main
from modules import common

DATES = ["20260928", "20261009", "20261013", "20261014", "20261015", "20261016"]
LATEST = "20261016"
HIST = "20261014"

# 与真实会话无关的「当前实时」夹具：每只 100 亿、共 1000 只 → 快照口径 10 万亿
# （1000 只是为了让「市值后10%」样本 k=100 达到 compute.MICRO_MIN_UNIVERSE，
#   否则微盘代理按设计不写入，无法验证实时链路）
_SPOT_AMOUNT = 1e10
_SPOT_N = 1000


# ---------------------------------------------------------------- 夹具 / 环境

def _fake_spot() -> pd.DataFrame:
    """构造一份「今天的」全市场快照（金额刻意与任何历史日都不同，便于断言未污染）"""
    codes = [f"{600000 + i:06d}" for i in range(_SPOT_N)]
    return pd.DataFrame({
        "code": codes,
        "name": [f"股票{i}" for i in range(_SPOT_N)],
        "close": [10.0 + i for i in range(_SPOT_N)],
        "change_pct": [5.0] * _SPOT_N,
        "amount": [float(_SPOT_AMOUNT)] * _SPOT_N,
        "mktcap": [1e11] * _SPOT_N,
        "float_mktcap": [8e10] * _SPOT_N,
    })


def _prepare_env(monkeypatch, tmp_path):
    """把数据目录重定向到临时目录，并 mock 掉全部网络模块"""
    data_dir = tmp_path / "data"
    for sub in ("daily", "series", "meta"):
        os.makedirs(os.path.join(str(data_dir), sub), exist_ok=True)
    monkeypatch.setattr(build_main, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(common, "DATA_DIR", str(data_dir))
    # 临时目录与仓库不在同一盘符（Windows），relpath 需要同一根
    monkeypatch.setattr(common, "REPO_ROOT", str(tmp_path))

    calls = {"spot": 0, "industry": 0}

    def fake_get_spot(date=None):
        calls["spot"] += 1
        return _fake_spot()

    def fake_index_amount(code, date, last_known=None):
        # 指数成交额按日期查询（可靠源），模拟真实可得
        return 1000.0, date, ""

    def fake_industry(total_amount, date=None):
        calls["industry"] += 1
        return {"top10_up": [{"name": "军工装备", "change": 5.61, "amount": 100.0, "ratio": 1.0}],
                "top10_down": [], "source": "eastmoney", "note": "口径：东财行业板块当日数据"}

    monkeypatch.setattr(build_main.spot_mod, "get_spot", fake_get_spot)
    monkeypatch.setattr(build_main.index_mod, "get_index_amount_resilient", fake_index_amount)
    monkeypatch.setattr(build_main.index_mod, "get_index_change_pct", lambda c, d: 1.23)
    monkeypatch.setattr(build_main.index_mod, "get_index_close", lambda c, d: 3000.0)
    monkeypatch.setattr(build_main.index_mod, "get_index_ytd_pct", lambda c, d, dates=None: None)
    monkeypatch.setattr(build_main.margin_mod, "get_margin", lambda d: (None, None))
    monkeypatch.setattr(build_main.industry_mod, "get_industry_daily", fake_industry)
    monkeypatch.setattr(build_main.industry_mod, "get_industry_week_rank", lambda d, ds: None)
    monkeypatch.setattr(build_main.industry_mod, "load_industry_cache", lambda: (None, None))

    def fake_pools(date, spot_df=None):
        """涨跌停池按日期查询（真实源 stock_zt_pool_em(date) 支持历史）"""
        lu = [{"code": "600001", "name": "A", "amount": 20.0, "change": 10.0,
               "board": "主板", "is_up": True}]
        ld = [{"code": "600002", "name": "B", "amount": 3.0, "change": -10.0,
               "board": "主板", "is_up": False}]
        return {"lu": len(lu), "ld": len(ld), "lu_rows": lu, "ld_rows": ld,
                "lu_ok": True, "ld_ok": True,
                "lu_src": "eastmoney", "ld_src": "eastmoney", "ld_reason": None}

    monkeypatch.setattr(build_main.zt_mod, "fetch_pools", fake_pools)

    # 固定「最近已收盘交易日」，避免测试结果随运行时钟漂移
    monkeypatch.setattr(build_main, "last_closed_trade_date", lambda dates: LATEST)
    return str(data_dir), calls


def _read(data_dir, date):
    with open(os.path.join(data_dir, "daily", f"{date}.json"), encoding="utf-8") as f:
        return json.load(f)


def _write(data_dir, date, obj):
    with open(os.path.join(data_dir, "daily", f"{date}.json"), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def _series_dates(data_dir, key):
    p = os.path.join(data_dir, "series", f"{key}.json")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return [pt["date"] for pt in json.load(f).get("points", [])]


# ---------------------------------------------------------------- 闸门函数

def test_realtime_target_is_only_latest_closed_day(monkeypatch):
    monkeypatch.setattr(build_main, "last_closed_trade_date", lambda dates: LATEST)
    assert build_main.is_realtime_session_target(LATEST, DATES) is True
    for d in ("20260928", "20261009", "20261013", "20261014", "20261015"):
        assert build_main.is_realtime_session_target(d, DATES) is False


# ---------------------------------------------------------------- 历史日期：不得使用实时行情

def test_historical_date_never_calls_spot(monkeypatch, tmp_path):
    """历史日期重跑：实时快照接口一次都不许调，且写入的字段不含今天的行情"""
    data_dir, calls = _prepare_env(monkeypatch, tmp_path)

    build_main.build_one(HIST, DATES)

    assert calls["spot"] == 0, "历史日不得调用实时快照接口"

    d = _read(data_dir, HIST)
    assert d["data_quality"]["spot_derived"] == "unavailable"

    # 实时派生字段：空/None，不是 0，也不是今天的值
    assert d["concentration"]["top10"] == []
    assert d["concentration"]["top20"] == []
    assert d["concentration"]["top50"] == []
    assert d["concentration"]["top10_total"] is None
    assert d["overview"]["over_10e_count"] is None
    assert d["overview"]["over_10e_ratio"] is None
    assert d["overview"]["stock_count"] is None
    assert d["liquidity"]["over_10e_count"] is None
    assert d["liquidity"]["over_10e_ratio"] is None
    assert d["liquidity"]["mktcap_buckets"] == []
    assert d["liquidity"]["amount_buckets"] == []
    assert d["emotion"]["lu_ratio_of_total"] is None
    assert d["emotion"]["ld_ratio_of_over10e"] is None
    assert d["active_stocks"] == []

    # 今天的行情数值（100 亿/只、5000 亿合计）绝不出现在历史快照里
    raw = json.dumps(d, ensure_ascii=False)
    assert "5000.0" not in raw and "119.0" not in raw

    # 微盘代理依赖实时快照 → 不写该行
    assert all(r["code"] != "micro_proxy" for r in d["widebase"])


def test_historical_date_still_updates_from_dated_sources(monkeypatch, tmp_path):
    """历史日期仍可用「按日期查询」的可靠源更新：指数成交额、涨跌停池、两融"""
    data_dir, _ = _prepare_env(monkeypatch, tmp_path)

    build_main.build_one(HIST, DATES)
    d = _read(data_dir, HIST)

    vol = {r["code"]: r for r in d["index_volume"]}
    assert vol["sh000001"]["amount"] == 1000.0          # 指数成交额按日期可得
    assert vol["sh000001"]["amount_date"] == HIST
    assert d["overview"]["limit_up"] == 1               # 涨跌停池按日期查询
    assert d["overview"]["limit_down"] == 1
    # 两市成交额采用指数口径（沪+深），不是快照口径
    assert d["overview"]["total_amount"] == 2000.0


def test_historical_date_does_not_refetch_realtime_industry(monkeypatch, tmp_path):
    """行业日快照（东财/同花顺板块）同样不接受历史日期 → 历史日不得调用"""
    data_dir, calls = _prepare_env(monkeypatch, tmp_path)

    build_main.build_one(HIST, DATES)
    assert calls["industry"] == 0
    assert _read(data_dir, HIST)["industry"] is None


def test_no_zero_filled_history_series(monkeypatch, tmp_path):
    """不可用时不得写 0 到序列（over_10e / 集中度不得出现该日点）"""
    data_dir, _ = _prepare_env(monkeypatch, tmp_path)

    build_main.build_one(HIST, DATES)

    assert HIST not in _series_dates(data_dir, "over_10e_count")
    assert HIST not in _series_dates(data_dir, "top10_concentration")
    assert HIST not in _series_dates(data_dir, "mktcap_buckets")
    # 涨跌停来自按日期查询的可靠源，应正常写入
    assert HIST in _series_dates(data_dir, "limit_up_down")


# ---------------------------------------------------------------- 历史日期：保护已有有效数据

def test_historical_rebuild_carries_existing_values(monkeypatch, tmp_path):
    """旧快照已有全市场字段 → 原样沿用，不清空、不重算"""
    data_dir, calls = _prepare_env(monkeypatch, tmp_path)
    old = {
        "trade_date": HIST,
        "overview": {"total_amount": 14144.03, "limit_up": 36, "limit_down": 11,
                     "over_10e_count": 283, "over_10e_ratio": 5.4, "stock_count": 5225},
        "concentration": {"top_n": [10, 20, 50],
                          "top10": [{"code": "300308", "name": "中际旭创",
                                     "amount": 155.65, "pct_of_total": 1.1}],
                          "top20": [], "top50": [],
                          "top20_cum_pct": 9.14, "top50_cum_pct": 16.15,
                          "top10_total": 5.89, "top10_total_pctile_hist": None},
        "liquidity": {"over_10e_count": 283, "over_10e_ratio": 5.4, "pctile_count": 71.3,
                      "mktcap_buckets": [{"label": "<50亿", "count": 2130, "pct": 40.8}],
                      "amount_buckets": [], "over_10e_marketcap_buckets": [],
                      "over_10e_marketcap_value_buckets": []},
        "emotion": {"limit_up": 36, "limit_down": 11},
    }
    _write(data_dir, HIST, old)

    build_main.build_one(HIST, DATES)
    d = _read(data_dir, HIST)

    assert calls["spot"] == 0
    assert d["data_quality"]["spot_derived"] == "carried_over"
    assert d["concentration"]["top10"][0]["code"] == "300308"
    assert d["concentration"]["top10_total"] == 5.89
    assert d["overview"]["stock_count"] == 5225
    assert d["overview"]["over_10e_count"] == 283
    assert d["liquidity"]["mktcap_buckets"][0]["count"] == 2130


def test_marked_unavailable_is_not_resurrected(monkeypatch, tmp_path):
    """已标记 unavailable 的快照，重跑时不得把残留值复活"""
    data_dir, calls = _prepare_env(monkeypatch, tmp_path)
    _write(data_dir, HIST, {
        "trade_date": HIST,
        "overview": {"total_amount": 14144.03, "over_10e_count": 342, "stock_count": 5225},
        "concentration": {"top_n": [10, 20, 50],
                          "top10": [{"code": "300308", "name": "中际旭创", "amount": 217.78,
                                     "pct_of_total": 1.42}],
                          "top20": [], "top50": [], "top20_cum_pct": 9.2, "top50_cum_pct": 16.2,
                          "top10_total": 7.11},
        "liquidity": {"over_10e_count": 342, "mktcap_buckets": [{"label": "<50亿", "count": 1}]},
        "emotion": {},
        "data_quality": {"spot_derived": "unavailable", "note": "无可靠历史来源"},
    })

    build_main.build_one(HIST, DATES)
    d = _read(data_dir, HIST)

    assert calls["spot"] == 0
    assert d["data_quality"]["spot_derived"] == "unavailable"
    assert d["concentration"]["top10"] == []
    assert d["overview"]["stock_count"] is None
    assert d["liquidity"]["over_10e_count"] is None


# ---------------------------------------------------------------- 最近交易日：正常实时流程

def test_latest_day_uses_realtime_spot_flow(monkeypatch, tmp_path):
    """最近已收盘交易日：实时快照照旧抓取并写入（不得因加保护而失效）"""
    data_dir, calls = _prepare_env(monkeypatch, tmp_path)

    build_main.build_one(LATEST, DATES)
    d = _read(data_dir, LATEST)

    assert calls["spot"] == 1, "最近交易日必须调用实时快照"
    assert calls["industry"] == 1, "最近交易日行业日快照照旧抓取"
    assert d["data_quality"]["spot_derived"] == "realtime"
    assert d["overview"]["stock_count"] == _SPOT_N
    assert len(d["concentration"]["top10"]) == 10
    assert d["concentration"]["top10"][0]["amount"] == round(_SPOT_AMOUNT / 1e8, 2)
    assert d["liquidity"]["mktcap_buckets"], "分档表应有数据"
    assert len(d["active_stocks"]) == _SPOT_N          # 全市场均 ≥5亿且涨幅≥5%
    assert any(r["code"] == "micro_proxy" for r in d["widebase"])
    assert LATEST in _series_dates(data_dir, "over_10e_count")
    assert LATEST in _series_dates(data_dir, "top10_concentration")


def test_latest_day_then_historical_rerun_keeps_realtime_data(monkeypatch, tmp_path):
    """先跑最新日（写入真实值），再重跑同日→仍为实时流程，数值不变"""
    data_dir, _ = _prepare_env(monkeypatch, tmp_path)

    build_main.build_one(LATEST, DATES)
    first = _read(data_dir, LATEST)
    build_main.build_one(LATEST, DATES)
    second = _read(data_dir, LATEST)

    assert first["concentration"]["top10"] == second["concentration"]["top10"]
    assert second["data_quality"]["spot_derived"] == "realtime"
