# -*- coding: utf-8 -*-
"""序列口径完整性：微盘代理口径 + 示例数据残留 + 量级突跳（专项一）

背景：`index_amount_micro_proxy` 曾在 2026-10-09 前后从 ~130 亿元/只 掉到 0.46 亿元/只。
根因不是「口径断层」，而是 2020-01-02~2026-09-24 整段为 `make_sample_data.py`
（random.seed(20260925)）生成的合成数据（基准 130 + 随机游走），与真实值差约 280 倍。
"""
import json
import os

import pandas as pd
import pytest

from modules import compute
from modules.common import DATA_DIR

# 已确认由 make_sample_data.py 合成、必须为空的区间
DEMO_RANGES = {
    "index_amount_micro_proxy": ("20200102", "20260924"),
    "index_amount_bj899050": ("20200102", "20260924"),
    "index_amount_sh000688": ("20260105", "20260924"),
    "index_amount_sh932000": ("20260105", "20260924"),
}


def _load(key):
    with open(os.path.join(DATA_DIR, "series", f"{key}.json"), encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------- 计算口径
def _spot(n=1000):
    """构造：市值 1~1000 亿递增，成交额恒为 0.1 亿"""
    return pd.DataFrame({
        "mktcap": [i * 1e8 for i in range(1, n + 1)],
        "amount": [1e7] * n,
    })


def test_micro_proxy_is_mean_of_bottom_decile():
    """口径：后 10% 的**平均**成交额（亿元/只），不是合计"""
    val, k = compute.microcap_proxy_amount(_spot(1000))
    assert k == 100
    assert val == pytest.approx(0.1, abs=1e-6)


def test_micro_proxy_uses_smallest_mktcap_group():
    """后 10% 取的是市值最小的那批：把最小 100 只成交额改为 1 亿，均值应为 1.0"""
    df = _spot(1000)
    df.loc[df.index[:100], "amount"] = 1e8
    val, k = compute.microcap_proxy_amount(df)
    assert k == 100
    assert val == pytest.approx(1.0, abs=1e-6)


def test_micro_proxy_insufficient_universe_is_none():
    """样本 <100 只时「后10%」没有统计意义：返回 None，不许算出一个漂亮的小数字"""
    val, k = compute.microcap_proxy_amount(_spot(200))
    assert val is None and k == 20
    assert compute.microcap_proxy_amount(None) == (None, 0)


# ---------------------------------------------------------------- 序列完整性
@pytest.mark.parametrize("key", list(DEMO_RANGES))
def test_no_demo_points_remain(key):
    lo, hi = DEMO_RANGES[key]
    obj = _load(key)
    bad = [p["date"] for p in obj["points"] if lo <= p["date"] <= hi]
    assert not bad, f"{key} 仍残留 {len(bad)} 个合成点，例如 {bad[:3]}"


@pytest.mark.parametrize("key", list(DEMO_RANGES))
def test_coverage_start_declared(key):
    """清理后必须显式声明覆盖起点，前端/报告据此区分「真历史」与「无数据」"""
    obj = _load(key)
    assert obj.get("coverage_start"), f"{key} 缺少 coverage_start"
    assert obj["points"][0]["date"] == obj["coverage_start"]
    assert obj.get("note")


def test_micro_proxy_magnitude_plausible():
    """微盘股「每只」日均成交额应在 0.05~10 亿元；出现 130 亿说明口径或单位错了"""
    for p in _load("index_amount_micro_proxy")["points"]:
        assert 0.01 <= p["value"] <= 10, f"{p['date']} 微盘代理 {p['value']} 亿/只 明显失真"


def test_no_extreme_regime_break_after_repair():
    """真实序列不应出现 >20 倍的相邻跳变（合成数据拼接的典型特征：282 倍）"""
    for key in DEMO_RANGES:
        pts = [(p["date"], p["value"]) for p in _load(key)["points"] if p.get("value")]
        for (d1, v1), (d2, v2) in zip(pts, pts[1:]):
            r = max(v2 / v1, v1 / v2)
            assert r < 20, f"{key} {d1}={v1} → {d2}={v2} 跳变 {r:.1f} 倍，疑似口径断层"


def test_small_sample_has_no_rank():
    """样本 <30 时排名/百分位必须为空（3 个点的百分位毫无意义，不能当真）"""
    for key in ("index_amount_micro_proxy", "index_amount_bj899050"):
        for p in _load(key)["points"]:
            assert p.get("pctile") is None and p.get("rank_all") is None


def test_demo_generator_removed_from_repo():
    """演示数据生成器必须不在仓库里，否则仍可能覆盖真实序列"""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    assert not os.path.exists(os.path.join(root, "scripts", "make_sample_data.py"))


# ---------------------------------------------------------------- 数据契约（长期防护）
def _trade_dates():
    from modules import calendar_mod
    return set(calendar_mod.get_trade_dates())


def _snapshot_dates():
    ddir = os.path.join(DATA_DIR, "daily")
    return [f[:-5] for f in sorted(os.listdir(ddir)) if f.endswith(".json")]


def test_series_have_no_nontrading_points():
    """所有序列的点必须落在交易日历内。

    20261010（周六）曾被 `--date` 手动跑过一次：东财对非交易日返回「0 家」且**不报错**，
    于是序列里出现了一个 up=0/down=0 的污染点。交易日校验必须先于写序列，
    且不能靠「值是否为 0」来兜底判断。
    """
    ds = _trade_dates()
    sdir = os.path.join(DATA_DIR, "series")
    bad = {}
    for f in sorted(os.listdir(sdir)):
        if not f.endswith(".json"):
            continue
        for p in _load(f[:-5]).get("points", []):
            if p["date"] not in ds:
                bad.setdefault(f, []).append(p["date"])
    assert not bad, f"序列含非交易日点：{bad}"


def test_no_zero_limit_pool_values():
    """涨停/跌停家数写 0 只允许是真实「全市场无涨跌停」，接口失败必须写缺口"""
    for key in ("limit_up_down", "limit_down"):
        zeros = [p["date"] for p in _load(key)["points"] if p.get("value") == 0]
        assert not zeros, f"{key} 含 0 值点（疑似失败被写成 0）：{zeros[:5]}"


def test_sh000985_is_declared_proxy_of_total():
    """sh000985 = 沪深合计代理：序列值必须与 total_amount 完全一致，且带代理标识"""
    obj = _load("index_amount_sh000985")
    a = {p["date"]: p["value"] for p in obj["points"]}
    b = {p["date"]: p["value"] for p in _load("total_amount")["points"]}
    assert set(a) == set(b), "sh000985 与 total_amount 日期集合不同"
    diff = [d for d in a if abs(a[d] - b[d]) > 0.01]
    assert not diff, f"sh000985 与 total_amount 不一致 {len(diff)} 天：{diff[:5]}"
    assert obj.get("proxy") is True and obj.get("proxy_of") == "total_amount"


def test_total_amount_equals_sh_plus_sz():
    """两市成交额 == 上证指数 + 深证成指（同一口径，避免 0.02% 级尾差累积成断层）"""
    sh = {p["date"]: p["value"] for p in _load("index_amount_sh000001")["points"]}
    sz = {p["date"]: p["value"] for p in _load("index_amount_sz399001")["points"]}
    tot = {p["date"]: p["value"] for p in _load("total_amount")["points"]}
    bad = [d for d in tot if d in sh and d in sz and abs(sh[d] + sz[d] - tot[d]) > 0.02]
    assert not bad, f"总成交额 != 沪+深：{bad[:5]}"


def test_snapshot_sh000985_matches_series():
    """快照宽基行与序列必须同口径：同一指标不能在指数矩阵与趋势图里给出两个数"""
    tot = {p["date"]: p["value"] for p in _load("total_amount")["points"]}
    bad = []
    for d in _snapshot_dates():
        with open(os.path.join(DATA_DIR, "daily", f"{d}.json"), encoding="utf-8") as fh:
            snap = json.load(fh)
        row = next((r for r in snap.get("widebase", []) if r.get("code") == "sh000985"), None)
        if row and d in tot and (row.get("amount") is None or abs(row["amount"] - tot[d]) > 0.01):
            bad.append((d, row.get("amount"), tot[d]))
    assert not bad, f"快照 sh000985 与序列不一致：{bad[:3]}"


def test_snapshots_declare_date_rule():
    """每份快照都要声明业务日期规则，前端「更新时间」才不会被当成本地时间解释"""
    bad = []
    for d in _snapshot_dates():
        with open(os.path.join(DATA_DIR, "daily", f"{d}.json"), encoding="utf-8") as fh:
            q = json.load(fh).get("data_quality") or {}
        if q.get("date_rule") != "asia_shanghai":
            bad.append(d)
    assert not bad, f"快照缺 date_rule=asia_shanghai：{bad}"


def test_sparkline_has_no_nontrading_points():
    ds = _trade_dates()
    bad = []
    for d in _snapshot_dates():
        with open(os.path.join(DATA_DIR, "daily", f"{d}.json"), encoding="utf-8") as fh:
            sp = (json.load(fh).get("sparklines") or {}).get("limit_up_down", [])
        bad += [(d, p["date"]) for p in sp if p["date"] not in ds]
    assert not bad, f"sparkline 含非交易日点：{bad[:5]}"
