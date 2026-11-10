# -*- coding: utf-8 -*-
"""每日市场观察：共振门槛、事件分类、客观性测试。

覆盖任务书「十三、测试与实际验收」中的：
- 共振板块：2/5、3/5 不显示正式评分、不参与排名；4/5、5/5 参与；缺失指标不填 0。
- 公告分类：客观分类，例行披露过滤。
- 客观性：自动文字不出现买卖建议 / 涨跌预测 / 利好利空等推断措辞。
"""
import pytest

import build_observation as bo
from observation_sources import events
from observation_sources.events import classify_title, is_routine, build_factual_summary


# ---------------------------------------------------------------------------
# 共振门槛
# ---------------------------------------------------------------------------
def _board(**kw):
    base = {
        "name": "测试板块", "change": 2.0, "amount": 100.0, "amount_change": None,
        "up_count": None, "down_count": None, "limit_up_count": None,
        "constituent_count": None, "lead_name": None, "lead_code": None, "lead_limit_up": None,
    }
    base.update(kw)
    return base


def _three_boards(up=None, down=None, amt_change=True, limit_up=None):
    """构造 3 个板块，用于百分位计算（样本 >= 2）。"""
    bs = []
    for i in range(3):
        b = _board(name=f"板块{i}", change=1.0 + i, amount=100.0 + i)
        if up is not None:
            b["up_count"] = up + i
            b["down_count"] = down + i if down is not None else 0
        if amt_change:
            b["amount_change"] = 5.0 + i
        if limit_up is not None:
            b["limit_up_count"] = limit_up + i
            b["constituent_count"] = 50
        bs.append(b)
    return bs


def _valid_count(c):
    return c["valid_count"]


def test_resonance_2of5_not_ranked():
    """2/5 有效（仅涨幅 + 相对强度）：不显示评分、不参与排名。"""
    bs = _three_boards(amt_change=False)  # change + bench(相对强度) = 2 项
    candidates, qualified = bo._compute_resonance(bs, bench=-1.0, category="行业")
    for c in candidates:
        assert c["raw_score"] is None
    assert qualified == []


def test_resonance_3of5_not_ranked():
    """3/5 有效（涨幅 + 相对强度 + 上涨家数占比）：不参与排名。"""
    bs = _three_boards(up=30, down=10, amt_change=False)
    candidates, qualified = bo._compute_resonance(bs, bench=-1.0, category="行业")
    assert all(c["raw_score"] is None for c in candidates)
    assert qualified == []


def test_resonance_4of5_ranked():
    """4/5 有效（涨幅 + 相对强度 + 上涨家数占比 + 成交额变化）：参与正式排名。"""
    bs = _three_boards(up=30, down=10, amt_change=True)
    candidates, qualified = bo._compute_resonance(bs, bench=-1.0, category="行业")
    assert any(c["raw_score"] is not None for c in candidates)
    assert len(qualified) == 3


def test_resonance_5of5_ranked():
    """5/5 有效：参与正式排名。"""
    bs = _three_boards(up=30, down=10, amt_change=True, limit_up=3)
    candidates, qualified = bo._compute_resonance(bs, bench=-1.0, category="行业")
    assert all(c["raw_score"] is not None for c in candidates)
    assert len(qualified) == 3


def test_resonance_missing_not_zero():
    """缺失指标 value 必须为 None，不得填 0。"""
    bs = _three_boards(amt_change=False)
    candidates, _ = bo._compute_resonance(bs, bench=-1.0, category="行业")
    for c in candidates:
        assert c["indicators"]["up_ratio"]["value"] is None
        assert c["indicators"]["amount_change"]["value"] is None
        assert c["indicators"]["limit_up_density"]["value"] is None


# ---------------------------------------------------------------------------
# 事件分类（客观，不预设利好利空）
# ---------------------------------------------------------------------------
def test_classify_positive():
    assert classify_title("关于回购公司股份方案的公告") == ("资本运作", "positive")
    assert classify_title("关于控股股东增持公司股份的公告") == ("股东行为", "positive")
    assert classify_title("关于签署日常经营重大合同的公告") == ("经营进展", "positive")
    assert classify_title("2026年半年度业绩预告（预增）") == ("业绩信息", "positive")


def test_classify_risk():
    assert classify_title("关于控股股东减持股份计划的公告") == ("股东行为", "risk")
    assert classify_title("关于收到警示函的公告") == ("监管事项", "risk")
    assert classify_title("关于收到行政处罚事先告知书的公告") == ("监管事项", "risk")
    assert classify_title("关于公司涉及诉讼的公告") == ("法律事项", "risk")
    assert classify_title("关于业绩预亏的公告") == ("业绩信息", "risk")


def test_classify_neutral_direction():
    """方向不明确的权益变动，不预设积极/风险。"""
    cat, grp = classify_title("简式权益变动报告书")
    assert cat == "股东行为"
    assert grp == "neutral"


def test_routine_filtered():
    assert is_routine("关于召开2026年第一次临时股东大会的通知")
    assert is_routine("第三届董事会第一次会议决议公告")
    assert is_routine("关于为控股子公司提供担保的进展公告")
    assert is_routine("2026年第三季度报告")
    assert not is_routine("关于签署重大合同的公告")


def test_factual_summary_no_judgment():
    s = build_factual_summary("关于回购公司股份的公告", "某公司")
    assert s == "某公司公告：关于回购公司股份的公告"
    for bad in ["利好", "利空", "股价", "上涨", "下跌", "建议"]:
        assert bad not in s


# ---------------------------------------------------------------------------
# 客观性：自动文字不出现推断/交易导向措辞
# ---------------------------------------------------------------------------
FORBIDDEN = [
    "利好", "利空", "看多", "看空", "买入", "卖出", "加仓", "减仓", "推荐",
    "建议关注", "值得布局", "投资机会", "目标价", "上涨空间", "收益预期",
    "赚钱效应", "亏钱效应", "资金参与", "资金进场", "主力出逃", "资金撤退",
    "做多", "做空", "后市有望", "即将上涨", "预计下跌", "交投趋于谨慎", "警惕",
]


def _metric(value, change=None, change_pct=None, **kw):
    d = {"value": value, "change": change, "change_pct": change_pct}
    d.update(kw)
    return d


def _sample_metrics():
    return {
        "total_amount": _metric(16578, -4602, -21.7, unit="亿元"),
        "limit_up": _metric(32, -52, unit="家"),
        "limit_down": _metric(15, 15, unit="家"),
        "over_10e_count": _metric(354, -109, unit="家"),
        "top10_pct": _metric(7.4, -0.3, unit="%", change_kind="pp"),
        "top20_pct": _metric(11.16, -0.32, unit="%", change_kind="pp"),
        "top50_pct": _metric(18.77, -0.22, unit="%", change_kind="pp"),
        "margin_balance": _metric(22997.88, unit="亿元", stat_date="20261105"),
        "stock_count": _metric(5573, unit="家"),
    }


def test_market_summary_objective():
    m = _sample_metrics()
    indexes = [{"name": "上证指数", "code": "sh000001", "close": 3649.18, "change_pct": -1.1, "change_points": -40.58, "prev_close": 3689.76}]
    sector_top5 = {"industry": {"up": [{"name": "种植业与林业", "change": 1.67}],
                                "down": [{"name": "元件", "change": -5.48}]},
                   "concept": {"up": None, "down": None}}
    s = bo._build_market_summary(m, indexes, sector_top5, "20261106")
    # 保留真实数据描述
    assert "16578" in s and "4602" in s and "32" in s and "15" in s
    assert "种植业与林业" in s and "元件" in s  # 融合板块
    for w in FORBIDDEN:
        assert w not in s, f"market_summary 出现禁止词: {w}"


def test_market_summary_no_top10():
    """总结删除 Top10/Top20，仅保留 Top50。"""
    m = _sample_metrics()
    indexes = []
    sector_top5 = {"industry": {"up": [], "down": []}, "concept": {"up": None, "down": None}}
    s = bo._build_market_summary(m, indexes, sector_top5, "20261106")
    assert "前 50 大" in s
    assert "前 10 大" not in s


def test_margin_change_compares_valid_records(monkeypatch):
    """两融变化比较两条实际有效统计记录，不拿相邻交易日强行匹配。"""
    pts = [
        {"date": "20261102", "value": 23232.96},
        {"date": "20261103", "value": 22913.86},
        {"date": "20261105", "value": 22997.88},
    ]
    monkeypatch.setattr(bo, "_load_margin_series", lambda: pts)
    change, prev_date, prev_val = bo._margin_change("20261105", 22997.88)
    assert change == 84.02
    assert prev_date == "20261103"
    assert prev_val == 22913.86


def test_build_indexes_points():
    """六大指数涨跌点数按涨跌幅反推。"""
    daily = {"index_volume": [{"name": "上证指数", "code": "sh000001", "close": 3649.1774, "change_pct": -1.1}],
             "widebase": [{"name": "中证500", "code": "sh000905", "close": 6597.3508, "change_pct": -2.13}]}
    idx = bo._build_indexes(daily)
    names = {i["name"]: i for i in idx}
    assert len(idx) == 6
    sh = names["上证指数"]
    assert sh["close"] == 3649.1774
    assert sh["change_points"] is not None and abs(sh["change_points"] - (-40.58)) < 1.0
    assert sh["prev_close"] is not None


def test_mktcap_dist_buckets():
    """成交额≥10亿股票市值六档分档。"""
    stocks = [
        {"code": "a", "amount": 20, "mktcap": 30},    # <50亿
        {"code": "b", "amount": 15, "mktcap": 80},    # 50-100
        {"code": "c", "amount": 12, "mktcap": 300},   # 200-500
        {"code": "d", "amount": 8, "mktcap": 2000},   # 成交额<10，不参与
        {"code": "e", "amount": 50, "mktcap": None},  # 缺市值
    ]
    dist = bo._build_mktcap_dist(stocks)
    assert dist["sample_total"] == 3  # a,b,c 有市值
    assert dist["missing_mktcap"] == 1  # e 缺市值
    labels = {b["label"]: b["count"] for b in dist["buckets"]}
    assert labels["<50亿"] == 1
    assert labels["50-100亿"] == 1
    assert labels["200-500亿"] == 1
    assert labels["100-200亿"] == 0
    # 成交额<10 的 d 不参与
    assert dist["sample_total"] == 3


def test_mktcap_dist_no_data_not_reuse():
    """无数据时 sample_total=None，不复用全A分档。"""
    dist = bo._build_mktcap_dist([])
    assert dist["sample_total"] is None
    assert dist["buckets"] == []


def test_group_events_dedup():
    """公告分组：回购/风险减持，同公司同类别合并。"""
    evs = [
        {"event_id": "1", "title": "关于回购股份方案的公告", "stock_code": "A", "company_name": "甲公司",
         "category_group": "positive", "event_category": "资本运作", "published_at": "2026-11-06T20:00"},
        {"event_id": "2", "title": "关于回购进展的公告", "stock_code": "A", "company_name": "甲公司",
         "category_group": "positive", "event_category": "资本运作", "published_at": "2026-11-06T19:00"},
        {"event_id": "3", "title": "关于控股股东减持的公告", "stock_code": "B", "company_name": "乙公司",
         "category_group": "risk", "event_category": "股东行为", "published_at": "2026-11-06T18:00"},
        {"event_id": "4", "title": "关于减持进展的公告", "stock_code": "B", "company_name": "乙公司",
         "category_group": "risk", "event_category": "股东行为", "published_at": "2026-11-06T17:00"},
    ]
    g = bo._group_events(evs)
    assert len(g["buyback"]) == 1  # 甲公司回购合并为 1 条
    assert len(g["risk"]) == 1     # 乙公司减持合并为 1 条


def test_resonance_ths_no_score():
    """历史简版共振：不足 4 项有效，board 的 raw_score 必须为 None。"""
    daily = {
        "industry": {"top10_up": [{"name": "种植业与林业", "change": 1.67, "amount": 93.9}],
                     "top10_down": [{"name": "元件", "change": -2.1, "amount": 200.0}],
                     "source": "ths"},
        "widebase": [{"name": "中证全指(沪深合计代理)", "change_pct": -1.85}],
    }
    prev = {"industry": {"top10_up": [{"name": "种植业与林业", "amount": 90.0}], "top10_down": []}}
    r = bo._resonance_from_ths(daily, prev, -1.85)
    assert r["qualified_full"] is False
    if r["board"] is not None:
        assert r["board"]["raw_score"] is None
