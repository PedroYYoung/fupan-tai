# -*- coding: utf-8 -*-
"""涨跌停数据完整性（专项二）

核心不变量：
1. 「接口成功但 0 家」是真值 0；「接口失败 / 超出服务端保留窗口」必须是 None，不能写 0。
2. 历史日期不得用当前实时快照兜底（否则等于把今天的数据写进历史）。
3. 序列里不得出现「只有涨停没有跌停」以外的不一致（跌停日期必须是涨停日期的子集）。
4. 已知缺口（东财跌停池只保留最近 30 天造成）要能被自动识别，不能静默通过。
"""
import glob
import json
import os

import akshare as ak
import pandas as pd
import pytest

from modules import zt_mod
from modules.common import DATA_DIR

ZT_DF = pd.DataFrame({
    "代码": ["600000", "000001"],
    "名称": ["浦发银行", "平安银行"],
    "涨跌幅": [10.0, 10.0],
    "成交额": [15e8, 6e8],
})
DT_DF = pd.DataFrame({
    "代码": ["600001"],
    "名称": ["某股"],
    "涨跌幅": [-10.0],
    "成交额": [20e8],
})


def _series(key):
    with open(os.path.join(DATA_DIR, "series", f"{key}.json"), encoding="utf-8") as f:
        return json.load(f)["points"]


def test_empty_down_pool_is_real_zero(monkeypatch):
    """跌停池返回空表＝当日确实 0 家跌停（合法值），必须区别于接口失败"""
    monkeypatch.setattr(ak, "stock_zt_pool_em", lambda date=None: ZT_DF)
    monkeypatch.setattr(ak, "stock_zt_pool_dtgc_em", lambda date=None: pd.DataFrame())
    r = zt_mod.fetch_pools("20261020")
    assert r["ld"] == 0
    assert r["ld_ok"] is True and r["ld_src"] == "eastmoney"
    assert r["lu"] == 2 and r["lu_ok"] is True


def test_down_pool_out_of_window_is_none_not_zero(monkeypatch):
    """东财跌停池只保留最近 30 天：超窗必须 None（不写 0、不写序列），并给出原因"""
    def boom(date=None):
        raise ValueError("跌停股池只能获取最近 30 个交易日的数据")

    monkeypatch.setattr(ak, "stock_zt_pool_em", lambda date=None: ZT_DF)
    monkeypatch.setattr(ak, "stock_zt_pool_dtgc_em", boom)
    r = zt_mod.fetch_pools("20220209")
    assert r["ld"] is None and r["ld_ok"] is False
    assert r["ld_rows"] == []
    assert "30" in (r["ld_reason"] or "")
    assert r["lu"] == 2, "涨停池可用时不应连累涨停"


def test_failure_never_falls_back_to_spot_for_history(monkeypatch):
    """历史日期不传 spot_df：两个池都失败时只能 None，绝不能伪造"""
    def boom(date=None):
        raise RuntimeError("network down")

    monkeypatch.setattr(ak, "stock_zt_pool_em", boom)
    monkeypatch.setattr(ak, "stock_zt_pool_dtgc_em", boom)
    r = zt_mod.fetch_pools("20250114", None)
    assert r["lu"] is None and r["ld"] is None


def test_down_pool_is_subset_of_up_pool():
    """跌停序列的日期集合必须是涨停序列的子集（不存在只有跌停没有涨停的孤立点）"""
    lu = {p["date"] for p in _series("limit_up_down")}
    ld = {p["date"] for p in _series("limit_down")}
    assert not (ld - lu), f"存在跌停日期但无涨停日期：{sorted(ld - lu)[:10]}"


def test_no_zero_substitution_for_missing_days():
    """缺口日不得以 0 出现：limit_down 里值为 0 的日期必须有涨停记录且不是缺口日"""
    lu = {p["date"]: p["value"] for p in _series("limit_up_down")}
    ld = {p["date"]: p["value"] for p in _series("limit_down")}
    zero_days = [d for d, v in ld.items() if v == 0]
    for d in zero_days:
        assert d in lu
    # 现有数据里 0 家跌停的日子应当极少（若有大量 0，说明曾经把失败写成 0）
    assert len(zero_days) <= 30, f"跌停 0 家的天数异常偏多：{len(zero_days)}，疑似把缺失写成了 0"


def test_gaps_are_known_and_bounded():
    """缺口自动识别：目前缺口全部由「东财跌停池 30 天窗口」造成，且不得超过基线 98 天"""
    with open(os.path.join(DATA_DIR, "meta", "trading_days.json"), encoding="utf-8") as f:
        dates = json.load(f)["list"]
    lu = {p["date"] for p in _series("limit_up_down")}
    ld = {p["date"] for p in _series("limit_down")}
    span = sorted(d for d in dates if lu and min(lu) <= d <= max(lu))
    gaps = [d for d in span if d in lu and d not in ld]
    assert len(gaps) <= 98, (
        f"跌停缺口增大到 {len(gaps)} 天（基线 98）：新增缺口={sorted(set(gaps))[:5]}，"
        "说明某次采集把跌停池失败静默跳过了")
    # 缺口日必须「有涨停、无跌停」，不能反过来
    assert all(d in lu for d in gaps)


def test_snapshots_do_not_fake_zero_down():
    """快照 sparkline：跌停缺失必须是 null，不能是 0（否则前端会画出「跌停归零」假信号）"""
    ld = {p["date"]: p["value"] for p in _series("limit_down")}
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "daily", "*.json"))):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        for pt in (d.get("sparklines") or {}).get("limit_up_down") or []:
            if pt.get("down") is None:
                continue
            assert pt["down"] == ld.get(pt["date"]), (
                f"{os.path.basename(path)} sparkline {pt['date']} 跌停值与序列不一致")


def test_snapshot_emotion_null_when_pool_unavailable():
    """快照中 limit_down 为 None 时，门槛家数/占比也必须是 None（不能算出 0）"""
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "daily", "*.json"))):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        em = d.get("emotion") or {}
        if em.get("limit_down") is None:
            assert em.get("ld_over5e_count") is None
            assert em.get("ld_ratio_of_total") is None
            assert em.get("ld_ratio_of_over10e") is None
            assert em.get("ld_over10e") == []


@pytest.mark.parametrize("date", ["20261014", "20261015", "20261016", "20261009"])
def test_known_good_values_match_eastmoney(date):
    """已核验日期的跌停家数与东财跌停池一致（回归锁：防止后续重跑改写真实值）"""
    known = {"20261009": 8, "20261014": 11, "20261015": 26, "20261016": 10}
    ld = {p["date"]: p["value"] for p in _series("limit_down")}
    assert ld.get(date) == known[date]


# ---------------------------------------------------------------- 源优先级（20261020 实测回归）
def test_series_limit_down_matches_eastmoney_snapshot():
    """序列跌停值必须等于「东财池直采成功」当日的快照值。

    实测案例：20261020 首建时东财池给出 6 家（limit_down_ok=True）；数小时后重跑，
    池接口 SSLError，快照兜底判定得 9 家并写回序列 —— 低可信源覆盖了已核验值，
    同一日期在序列与旧快照之间出现两个数。此测试锁定「降级不得覆盖直采」。
    """
    ld = {p["date"]: p.get("value") for p in _series("limit_down")}
    bad = []
    for fp in sorted(glob.glob(os.path.join(DATA_DIR, "daily", "*.json"))):
        d = os.path.basename(fp)[:-5]
        with open(fp, encoding="utf-8") as f:
            snap = json.load(f)
        pool = (snap.get("data_quality") or {}).get("limit_pool") or {}
        emo = snap.get("emotion") or {}
        if pool.get("limit_down_ok") is not True or pool.get("limit_down_src") != "eastmoney":
            continue
        if emo.get("limit_down") is None or d not in ld:
            continue
        if ld[d] != emo["limit_down"]:
            bad.append((d, ld[d], emo["limit_down"]))
    assert not bad, f"序列跌停值与东财直采快照不一致（序列, 快照）：{bad[:5]}"


def test_no_stale_amount_presented_as_today():
    """滞后超阈值的「最近交易日降级」不得留在快照里冒充当日成交额。

    sh932000 序列止于 20251231，20261020 一度复用该值（滞后 293 天）。
    """
    from modules.index_mod import MAX_STALE_DAYS, _days_between

    bad = []
    for fp in sorted(glob.glob(os.path.join(DATA_DIR, "daily", "*.json"))):
        d = os.path.basename(fp)[:-5]
        with open(fp, encoding="utf-8") as f:
            snap = json.load(f)
        for block in ("index_volume", "widebase"):
            for r in snap.get(block) or []:
                if r.get("note") != "last_trading_day" or r.get("amount") is None:
                    continue
                gap = _days_between(str(r.get("amount_date") or ""), d)
                if gap is None or gap > MAX_STALE_DAYS:
                    bad.append((d, r.get("code"), r.get("amount"), r.get("amount_date"), gap))
    assert not bad, f"存在陈旧降级行冒充当日值：{bad[:5]}"
