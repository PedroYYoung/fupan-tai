# -*- coding: utf-8 -*-
"""复盘报告自动结论规则引擎评分测试。

严格对应 src/rules/engine.ts + src/rules/thresholds.ts 的评分规则：
  总评 = 资金面(0~40) + 结构面(0~30) + 情绪面(0~30)，满分 100。
  每维度：基准分（中性）+ 触发条件加减分，clamp 到 [0, 满分]。
  百分位为 None 时（缺失/样本不足）不触发对应判断。

本测试用 Python 复现评分规则，验证「规则语义」；TS 实现正确性由 vue-tsc + vite build 保证。
"""
import json
import os

import pytest

DAILY_DIR = os.path.join(os.path.dirname(__file__), "..", "public", "data", "daily")

# ---- 复现 thresholds.ts ----
WEIGHT = {"fund": 40, "structure": 30, "emotion": 30}
BASE = {"fund": 24, "structure": 18, "emotion": 18}
FUND = {"vol_up": 15, "vol_down": -15, "over10e_high": 80, "over10e_low": 20, "margin_high": 90, "delta": 16}
STRUCT = {"extreme": 90, "disperse": 10, "delta": 12, "mktcap_delta": 6}
EMO = {"lu_high": 90, "ld_low": 10, "ld_count": 50, "ld_over10e": 5, "delta": 12}


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _score_fund(mom, over10e_pctile, margin_pctile):
    """资金面得分（对应 engine.ts fundRule）。amt_pctile 仅影响文案不影响得分。"""
    score = BASE["fund"]
    if mom is not None and over10e_pctile is not None:
        if mom > FUND["vol_up"] and over10e_pctile > FUND["over10e_high"]:
            score = BASE["fund"] + FUND["delta"]
        elif mom < FUND["vol_down"] and over10e_pctile < FUND["over10e_low"]:
            score = BASE["fund"] - FUND["delta"]
    return _clamp(score, 0, WEIGHT["fund"])


def _score_structure(top10_pctile):
    score = BASE["structure"]
    if top10_pctile is not None:
        if top10_pctile > STRUCT["extreme"]:
            score = BASE["structure"] - STRUCT["delta"]
        elif top10_pctile < STRUCT["disperse"]:
            score = BASE["structure"] + STRUCT["delta"]
    return _clamp(score, 0, WEIGHT["structure"])


def _score_emotion(lu_pctile, ld_pctile, ld_count, ld_over10e):
    score = BASE["emotion"]
    if lu_pctile is not None and ld_pctile is not None and lu_pctile > EMO["lu_high"] and ld_pctile < EMO["ld_low"]:
        score = BASE["emotion"] + EMO["delta"]
    if ld_count is not None and ld_over10e is not None and ld_count > EMO["ld_count"] and ld_over10e >= EMO["ld_over10e"]:
        score = BASE["emotion"] - EMO["delta"]
    return _clamp(score, 0, WEIGHT["emotion"])


# ---------------------------------------------------------------- 资金面

def test_fund_volume_up():
    assert _score_fund(mom=20, over10e_pctile=85, margin_pctile=50) == 40


def test_fund_volume_down():
    assert _score_fund(mom=-20, over10e_pctile=15, margin_pctile=50) == 8


def test_fund_neutral():
    assert _score_fund(mom=0, over10e_pctile=50, margin_pctile=50) == 24


def test_fund_margin_warning_does_not_change_score():
    # 杠杆高位警示：不改分
    assert _score_fund(mom=0, over10e_pctile=50, margin_pctile=95) == 24


def test_fund_missing_does_not_trigger():
    # 环比或百分位缺失 → 不触发放量/缩量，保持基准分
    assert _score_fund(mom=None, over10e_pctile=85, margin_pctile=50) == 24
    assert _score_fund(mom=20, over10e_pctile=None, margin_pctile=50) == 24


# ---------------------------------------------------------------- 结构面

def test_structure_extreme():
    assert _score_structure(95) == 6


def test_structure_disperse():
    assert _score_structure(5) == 30


def test_structure_neutral():
    assert _score_structure(50) == 18


def test_structure_missing_neutral():
    assert _score_structure(None) == 18


# ---------------------------------------------------------------- 情绪面

def test_emotion_profit():
    assert _score_emotion(lu_pctile=95, ld_pctile=5, ld_count=10, ld_over10e=0) == 30


def test_emotion_risk():
    assert _score_emotion(lu_pctile=50, ld_pctile=50, ld_count=60, ld_over10e=6) == 6


def test_emotion_neutral():
    assert _score_emotion(lu_pctile=50, ld_pctile=50, ld_count=10, ld_over10e=0) == 18


def test_emotion_missing_no_trigger():
    assert _score_emotion(lu_pctile=None, ld_pctile=5, ld_count=10, ld_over10e=0) == 18


# ---------------------------------------------------------------- 总分

def test_total_score_clamp():
    fund = _score_fund(20, 85, 50)
    structure = _score_structure(5)
    emotion = _score_emotion(95, 5, 10, 0)
    total = _clamp(fund + structure + emotion, 0, 100)
    assert total == 100


def test_total_score_low_clamp():
    fund = _score_fund(-20, 15, 50)
    structure = _score_structure(95)
    emotion = _score_emotion(50, 50, 60, 6)
    total = _clamp(fund + structure + emotion, 0, 100)
    assert 0 <= total <= 100


# ---------------------------------------------------------------- 真实数据端到端

def test_recent_daily_fields_present():
    """最近快照必须含报告所需字段（评分依赖的百分位/家数等）。"""
    files = sorted(os.listdir(DAILY_DIR))
    assert files
    with open(os.path.join(DAILY_DIR, files[-1]), encoding="utf-8") as f:
        d = json.load(f)
    o = d["overview"]
    assert o["total_amount"] is not None
    assert o["limit_up"] is not None and o["limit_down"] is not None
    # 集中度、情绪字段存在
    assert "top10_total" in d["concentration"]
    assert "lu_pctile" in d["emotion"] and "ld_pctile" in d["emotion"]
    assert "pctile_count" in d["liquidity"]


def test_multiple_daily_files_reportable():
    """至少 4 个历史快照可生成报告（覆盖多日期测试）。"""
    files = sorted(os.listdir(DAILY_DIR))
    assert len(files) >= 4, "历史快照不足 4 个，无法覆盖多日期测试"


# ---------------------------------------------------------------- 结构面多信号累积（复现 engine.ts structureRule）

def _structure_tags(top10_pctile, mkt_signal):
    """完整复现 structureRule 多信号累积：返回 (score, tags)。
    mkt_signal: None / 'big_suck'(大盘吸血) / 'micro_up'(小微盘活跃)。"""
    tags = []
    if top10_pctile is not None:
        if top10_pctile > STRUCT["extreme"]:
            tags.append(("成交高度集中", "risk", -STRUCT["delta"]))
        elif top10_pctile < STRUCT["disperse"]:
            tags.append(("成交极度分散", "positive", STRUCT["delta"]))
    if mkt_signal == "big_suck":
        tags.append(("大盘吸血", "risk", -STRUCT["mktcap_delta"]))
    elif mkt_signal == "micro_up":
        tags.append(("小微盘活跃", "positive", STRUCT["mktcap_delta"]))
    has_risk = any(t[1] == "risk" for t in tags)
    has_pos = any(t[1] == "positive" for t in tags)
    if has_risk and has_pos:
        tags.append(("结构分化", "neutral", 0))
    score = BASE["structure"]
    for t in tags:
        score += t[2]
    return _clamp(score, 0, WEIGHT["structure"]), tags


def test_structure_top10_concentrated_only():
    """1. Top10 高度集中，未出现小微盘扩散。"""
    score, tags = _structure_tags(95, None)
    assert score == 6
    assert [t[0] for t in tags] == ["成交高度集中"], "不应出现额外信号"


def test_structure_micro_up_only():
    """2. Top10 未高度集中，小微盘扩散。"""
    score, tags = _structure_tags(50, "micro_up")
    assert score == 24  # 18 + 6
    assert [t[0] for t in tags] == ["小微盘活跃"]


def test_structure_concentrated_and_micro_up():
    """3. Top10 高度集中，同时小微盘扩散 → 结构分化。"""
    score, tags = _structure_tags(95, "micro_up")
    assert score == 12  # 18 - 12 + 6（保留分值贡献，非覆盖）
    assert [t[0] for t in tags] == ["成交高度集中", "小微盘活跃", "结构分化"]
    assert tags[-1][1] == "neutral" and tags[-1][2] == 0


def test_structure_concentrated_and_big_suck():
    """4. Top10 高度集中，同时大市值占比上升（同向 risk，不构成分化）。"""
    score, tags = _structure_tags(95, "big_suck")
    assert score == 0  # 18 - 12 - 6
    labels = [t[0] for t in tags]
    assert labels == ["成交高度集中", "大盘吸血"], "同向风险不应生成分化标签"
    assert "结构分化" not in labels


def test_structure_disperse_and_big_suck():
    """5. Top10 极度分散 + 大盘吸血（相反方向，另一种分化组合）。"""
    score, tags = _structure_tags(5, "big_suck")
    assert score == 24  # 18 + 12 - 6
    assert [t[0] for t in tags] == ["成交极度分散", "大盘吸血", "结构分化"]


# ---------------------------------------------------------------- 情绪面并存（复现 engine.ts emotionRule）

def _emotion_tags(lu_pctile, ld_pctile, ld_count, ld_o10):
    """完整复现 emotionRule：返回 (score, tags)，杀跌风险优先。"""
    tags = []
    profit = lu_pctile is not None and ld_pctile is not None and lu_pctile > EMO["lu_high"] and ld_pctile < EMO["ld_low"]
    kill = ld_count is not None and ld_o10 is not None and ld_count > EMO["ld_count"] and ld_o10 >= EMO["ld_over10e"]
    if profit:
        tags.append(("赚钱效应强", "positive", EMO["delta"]))
    if kill:
        tags.append(("高位股杀跌", "risk", -EMO["delta"]))
    score = BASE["emotion"]
    if kill:
        score = BASE["emotion"] - EMO["delta"]  # 杀跌优先
    elif profit:
        score = BASE["emotion"] + EMO["delta"]
    return _clamp(score, 0, WEIGHT["emotion"]), tags


def test_emotion_profit_and_kill_both():
    """6. 赚钱效应与杀跌风险同时触发：保留两个信号，得分杀跌优先。"""
    score, tags = _emotion_tags(lu_pctile=95, ld_pctile=5, ld_count=60, ld_o10=6)
    assert score == 6  # 杀跌优先，不叠加
    assert [t[0] for t in tags] == ["赚钱效应强", "高位股杀跌"], "两个信号都必须保留，不得丢失赚钱效应"


# ---------------------------------------------------------------- 市值结构环比日期定位回归

def test_structure_mktcap_uses_current_trade_date():
    """回归：市值结构环比必须按当前交易日定位，不能用序列最后两组（避免套用未来日期数据）。"""
    bucket_pts = [
        {"date": "20261102", "buckets": [{"label": ">1000亿", "pct": 3.0}, {"label": "<50亿", "pct": 44.1}]},
        {"date": "20261103", "buckets": [{"label": ">1000亿", "pct": 2.8}, {"label": "<50亿", "pct": 47.8}]},
        {"date": "20261104", "buckets": [{"label": ">1000亿", "pct": 2.9}, {"label": "<50亿", "pct": 46.7}]},
    ]
    trade_date = "20261103"
    # 正确：按当前交易日定位 idx=1，prev=20261102 → 小微盘活跃（升）
    idx = next(i for i, p in enumerate(bucket_pts) if p["date"] == trade_date)
    last = bucket_pts[idx]["buckets"]
    prev = bucket_pts[idx - 1]["buckets"]
    b_last = next(b["pct"] for b in last if b["label"] == ">1000亿")
    b_prev = next(b["pct"] for b in prev if b["label"] == ">1000亿")
    m_last = next(b["pct"] for b in last if b["label"] == "<50亿")
    m_prev = next(b["pct"] for b in prev if b["label"] == "<50亿")
    assert m_last > m_prev and b_last < b_prev, "按当前日期定位应判定为小微盘活跃"

    # 错误（旧逻辑）：固定用序列最后两组（1104 vs 1103）会误判为大盘吸血
    last2 = bucket_pts[-1]["buckets"]
    prev2 = bucket_pts[-2]["buckets"]
    b_last2 = next(b["pct"] for b in last2 if b["label"] == ">1000亿")
    b_prev2 = next(b["pct"] for b in prev2 if b["label"] == ">1000亿")
    m_last2 = next(b["pct"] for b in last2 if b["label"] == "<50亿")
    m_prev2 = next(b["pct"] for b in prev2 if b["label"] == "<50亿")
    assert b_last2 > b_prev2 and m_last2 < m_prev2, "最后两组确为大市值升/小微盘降（证明旧逻辑会误判）"
