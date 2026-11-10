# -*- coding: utf-8 -*-
"""每日市场观察数据生成器（第二版）

从复盘台现有 daily 快照（public/data/daily/YYYYMMDD.json）派生独立观察数据，
输出 public/data/daily_observation/YYYYMMDD.json。

第二版增量：
- 修正最强共振板块门槛：≥4/5 项有效才进入正式排名；2/5、3/5 仅作「板块表现观察」，
  不显示正式评分、不参与排名；缺失指标一律 null，绝不填 0。
- 接入东财行业/概念板块（当日，行业与概念独立数据源/样本/排名）。
- 接入巨潮资讯网上市公司公告（可回溯历史，事件分类 + 去重 + verification_status）。
- 交易所/证监会/权威媒体来源独立采集、独立容错，未通过验证时如实标记 unavailable。
- 全部自动文字改为客观中性，删除「利好/利空/赚钱效应/资金进场」等推断性措辞。

设计约束（与复盘台核心数据隔离，故障隔离）：
- 不修改、不重写 public/data/daily/ 与 series/ 任何文件。
- 任一来源失败不影响其他来源，也不影响核心行情数据。
- 环比一律使用「上一个有效交易日」（交易日历），不使用自然日。

用法：
  python scripts/build_observation.py --date 20261106 [--collect-events] [--collect-boards]
  python scripts/build_observation.py --all
"""
import argparse
import json
import os
from datetime import datetime, timezone, timedelta

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "public", "data")
DAILY_DIR = os.path.join(DATA_DIR, "daily")
OUT_DIR = os.path.join(DATA_DIR, "daily_observation")
META_PATH = os.path.join(DATA_DIR, "meta", "trading_days.json")

# 采集适配器（相对导入）
sys_path = os.path.dirname(os.path.abspath(__file__))
if sys_path not in __import__("sys").path:
    __import__("sys").path.insert(0, sys_path)
try:
    from observation_sources import cninfo_announcements, eastmoney_boards, regulators
    from observation_sources import events as event_lib
except ImportError:  # 依赖缺失时降级，不阻断核心行情派生
    cninfo_announcements = eastmoney_boards = regulators = event_lib = None

# 全A基准：widebase 中用于计算「相对大盘强度」的基准（板块涨幅 - 基准涨幅）
BENCHMARK_NAME = "中证全指(沪深合计代理)"

_CN_TZ = timezone(timedelta(hours=8))


def _now_cn():
    return datetime.now(_CN_TZ).isoformat(timespec="seconds")


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_trading_days():
    return _read_json(META_PATH).get("list", [])


def _prev_trading_day(dates, date):
    for i in range(len(dates) - 1, -1, -1):
        if dates[i] < date:
            return dates[i]
    return None


def _fmt_date(date):
    return f"{date[:4]}-{date[4:6]}-{date[6:8]}"


def _chg(cur, prev):
    if cur is None or prev is None:
        return None
    return round(cur - prev, 2)


def _chg_pct(cur, prev):
    if cur is None or prev is None or prev == 0:
        return None
    return round((cur - prev) / prev * 100, 2)


def _benchmark_change(daily):
    for r in daily.get("widebase", []) or []:
        if r.get("name") == BENCHMARK_NAME:
            return r.get("change_pct")
    return None


# 六大指数（客户版核心数据展示）
INDEX_DEFS = [
    ("sh000001", "上证指数"),
    ("sz399001", "深证成指"),
    ("sz399006", "创业板指"),
    ("sh000688", "科创50"),
    ("sh000905", "中证500"),
    ("sh000852", "中证1000"),
]


def _load_margin_series():
    """加载两融余额历史序列（series/margin.json points）。"""
    try:
        path = os.path.join(DATA_DIR, "series", "margin.json")
        return (_read_json(path).get("points") or [])
    except Exception:  # noqa: BLE001
        return []


def _margin_change(margin_date, margin_value):
    """比较两条实际有效的两融记录，返回 (change, prev_date, prev_value)。

    只比较两条实际有效的两融统计日，不允许拿上一自然日/交易日强行匹配。
    """
    if not margin_date or margin_value is None:
        return None, None, None
    prev = None
    for p in _load_margin_series():
        d = p.get("date")
        if d and d < margin_date and p.get("value") is not None:
            prev = p  # 保留 date 最大且小于 margin_date 的记录
    if prev:
        return round(margin_value - prev["value"], 2), prev["date"], prev["value"]
    return None, None, None


def _build_indexes(daily):
    """六大指数当日行情：收盘、涨跌幅、涨跌点数（按涨跌幅反推上一交易日收盘）。"""
    iv = {r.get("code"): r for r in (daily.get("index_volume") or [])}
    wb = {r.get("code"): r for r in (daily.get("widebase") or [])}
    out = []
    for code, name in INDEX_DEFS:
        r = iv.get(code) or wb.get(code) or {}
        close = r.get("close")
        pct = r.get("change_pct")
        prev_close = None
        points = None
        if close is not None and pct is not None:
            # 涨跌点数 = 当日收盘 - 上一有效交易日收盘；上一收盘按涨跌幅反推（约值）
            prev_close = round(close / (1 + pct / 100.0), 2)
            points = round(close - prev_close, 2)
        out.append({
            "name": name, "code": code,
            "close": close, "change_pct": pct,
            "change_points": points, "prev_close": prev_close,
        })
    return out


# --------------------------------------------------------------------------
# 01 市场核心数据
# --------------------------------------------------------------------------
def _build_market_metrics(daily, prev):
    o = daily.get("overview", {})
    po = (prev or {}).get("overview", {})
    c = daily.get("concentration", {})
    pc = (prev or {}).get("concentration", {})

    def metric(value, change=None, change_pct=None, **extra):
        d = {"value": value, "change": change, "change_pct": change_pct}
        d.update(extra)
        return d

    # 集中度变化：优先用快照内已算好的「百分点变化」，缺失则用相邻快照差
    def _pp(cur, prev, snap):
        if snap is not None:
            return snap
        return _chg(cur, prev)

    m = {
        "total_amount": metric(
            o.get("total_amount"),
            _chg(o.get("total_amount"), po.get("total_amount")),
            _chg_pct(o.get("total_amount"), po.get("total_amount")),
            unit="亿元"),
        "limit_up": metric(o.get("limit_up"), _chg(o.get("limit_up"), po.get("limit_up")), unit="家"),
        "limit_down": metric(o.get("limit_down"), _chg(o.get("limit_down"), po.get("limit_down")), unit="家"),
        "over_10e_count": metric(
            o.get("over_10e_count"),
            _chg(o.get("over_10e_count"), po.get("over_10e_count")), unit="家"),
        "top10_pct": metric(c.get("top10_total"), _pp(c.get("top10_total"), pc.get("top10_total"), c.get("top10_change")),
                            unit="%", change_kind="pp"),
        "top20_pct": metric(c.get("top20_cum_pct"), _pp(c.get("top20_cum_pct"), pc.get("top20_cum_pct"), c.get("top20_change")),
                            unit="%", change_kind="pp"),
        "top50_pct": metric(c.get("top50_cum_pct"), _pp(c.get("top50_cum_pct"), pc.get("top50_cum_pct"), c.get("top50_change")),
                            unit="%", change_kind="pp"),
        "margin_balance": metric(o.get("margin_balance"), unit="亿元", stat_date=o.get("margin_date")),
        "stock_count": metric(o.get("stock_count"), unit="家"),
    }
    # 两融余额变化：比较两条实际有效的统计记录（T+1 披露，不拿相邻交易日强行匹配）
    mchg, mprev_date, mprev_val = _margin_change(o.get("margin_date"), o.get("margin_balance"))
    m["margin_balance"]["change"] = mchg
    m["margin_balance"]["prev_stat_date"] = mprev_date
    m["margin_balance"]["prev_value"] = mprev_val
    return m


# --------------------------------------------------------------------------
# 02 今日市场总结（融合指数与板块，客观中性）
# --------------------------------------------------------------------------
def _build_market_summary(m, indexes, sector_top5, date):
    parts = []
    ta = m["total_amount"]
    if ta["value"] is not None:
        s = f"{_fmt_date(date)}两市成交额 {ta['value']:.0f} 亿元"
        if ta["change"] is not None:
            direction = "增加" if ta["change"] > 0 else ("减少" if ta["change"] < 0 else "持平")
            s += f"，较上一交易日{direction} {abs(ta['change']):.0f} 亿元"
            if ta["change_pct"] is not None:
                s += f"（{ta['change_pct']:+.1f}%）"
        s += "。"
        parts.append(s)

    # 六大指数总体表现
    up_idx = [i for i in indexes if i.get("change_pct") is not None and i["change_pct"] > 0]
    down_idx = [i for i in indexes if i.get("change_pct") is not None and i["change_pct"] < 0]
    if up_idx and down_idx:
        parts.append(f"六大指数中 {len(up_idx)} 个上涨、{len(down_idx)} 个下跌，表现分化"
                     f"（{up_idx[0]['name']} +{up_idx[0]['change_pct']:.2f}%，"
                     f"{down_idx[0]['name']} {down_idx[0]['change_pct']:.2f}%）。")
    elif up_idx and not down_idx:
        parts.append(f"六大指数全线收涨，其中 {up_idx[0]['name']} +{up_idx[0]['change_pct']:.2f}% 居前。")
    elif down_idx and not up_idx:
        parts.append(f"六大指数全线收跌，其中 {down_idx[0]['name']} {down_idx[0]['change_pct']:.2f}% 居前。")

    lu, ld = m["limit_up"], m["limit_down"]
    if lu["value"] is not None and ld["value"] is not None:
        s = f"涨停 {lu['value']} 家、跌停 {ld['value']} 家"
        if lu["change"] is not None:
            s += f"（涨停较上一交易日{'增加' if lu['change'] > 0 else '减少'} {abs(lu['change'])} 家）"
        s += "。"
        parts.append(s)

    o10 = m["over_10e_count"]
    if o10["value"] is not None:
        s = f"成交额超 10 亿元个股 {o10['value']} 家"
        if o10["change"] is not None:
            s += f"（较上一交易日{'增加' if o10['change'] > 0 else '减少'} {abs(o10['change'])} 家）"
        s += "。"
        parts.append(s)

    t50 = m["top50_pct"]
    if t50["value"] is not None:
        s = f"前 50 大个股成交占比 {t50['value']:.1f}%"
        if t50["change"] is not None:
            s += f"（较上一交易日{'上升' if t50['change'] > 0 else '下降'} {abs(t50['change']):.2f} 个百分点）"
        s += "。"
        parts.append(s)

    ind_up = (sector_top5.get("industry") or {}).get("up") or []
    ind_down = (sector_top5.get("industry") or {}).get("down") or []
    if ind_up and ind_down:
        parts.append(f"行业板块涨幅居前为「{ind_up[0]['name']}」，跌幅居前为「{ind_down[0]['name']}」。")

    if not parts:
        return "当日市场核心数据缺失，暂无法生成市场总结。"
    return "".join(parts)


# --------------------------------------------------------------------------
# 03 最强共振板块
# --------------------------------------------------------------------------
def _cross_section_pctile(values, value):
    """value 在 values 中的横截面百分位（0~100）。样本 <2 返回 None。"""
    if value is None or not values or len(values) < 2:
        return None
    below = sum(1 for x in values if x < value)
    return round(below / (len(values) - 1) * 100, 1)


def _compute_resonance(boards, bench, category):
    """对一组板块（同分类）计算五项共振指标与横截面百分位。

    返回排序后的候选列表。valid_count>=4 才进入正式排名（raw_score 有效）；
    valid_count<4 的板块 raw_score=None，仅作「板块表现观察」。
    """
    candidates = []
    for b in boards:
        change = b.get("change")
        rel = _chg(change, bench) if change is not None and bench is not None else None
        up = b.get("up_count")
        down = b.get("down_count")
        up_ratio = None
        if up is not None and down is not None and (up + down) > 0:
            up_ratio = round(up / (up + down) * 100, 2)
        amt_change = b.get("amount_change")
        lu = b.get("limit_up_count")
        cons = b.get("constituent_count")
        lu_density = round(lu / cons * 100, 2) if (lu is not None and cons) else None

        indicators = {
            "board_change": {"label": "板块涨幅", "weight": 0.20, "value": change, "valid": change is not None},
            "relative_strength": {"label": "相对大盘强度", "weight": 0.20, "value": rel, "valid": rel is not None},
            "up_ratio": {"label": "上涨家数占比", "weight": 0.20, "value": up_ratio, "valid": up_ratio is not None},
            "amount_change": {"label": "成交额变化", "weight": 0.20, "value": amt_change, "valid": amt_change is not None},
            "limit_up_density": {"label": "涨停密度", "weight": 0.20, "value": lu_density, "valid": lu_density is not None},
        }
        valid_count = sum(1 for v in indicators.values() if v["valid"])
        candidates.append({
            "name": b.get("name"),
            "category": category,
            "change": change,
            "relative_strength": rel,
            "up_ratio": up_ratio,
            "amount": b.get("amount"),
            "amount_change": amt_change,
            "limit_up_count": lu,
            "constituent_count": cons,
            "limit_up_density": lu_density,
            "lead_name": b.get("lead_name"),
            "lead_code": b.get("lead_code"),
            "lead_limit_up": b.get("lead_limit_up"),
            "valid_count": valid_count,
            "indicators": indicators,
            "raw_score": None,
        })

    # 横截面百分位：每一项在「该分类全部有效样本」中计算
    sample_keys = ["board_change", "relative_strength", "up_ratio", "amount_change", "limit_up_density"]
    for key in sample_keys:
        vals = [c["indicators"][key]["value"] for c in candidates
                if c["indicators"][key]["valid"]]
        for c in candidates:
            v = c["indicators"][key]["value"]
            if v is not None:
                c["indicators"][key]["pctile"] = _cross_section_pctile(vals, v)
            else:
                c["indicators"][key]["pctile"] = None

    # 综合分：有效项百分位等权平均（仅 valid_count>=4 时有效）
    for c in candidates:
        pcts = [c["indicators"][k]["pctile"] for k in c["indicators"]
                if c["indicators"][k].get("pctile") is not None]
        if pcts and c["valid_count"] >= 4:
            c["raw_score"] = round(sum(pcts) / len(pcts), 1)

    # 正式排名：仅 raw_score 非 None（即 valid_count>=4）参与
    qualified = [c for c in candidates if c["raw_score"] is not None]
    qualified.sort(key=lambda x: -(x["raw_score"] or 0))
    return candidates, qualified


def _resonance_from_ths(daily, prev, bench):
    """历史/简版共振：基于 daily 快照的 ths 行业 Top10（最多 3 项有效）。

    严格遵循门槛：不足 4 项有效时不产出正式评分，board 标记为「板块表现观察」。
    """
    ind = daily.get("industry") or {}
    pind = (prev or {}).get("industry") or {}
    prev_map = {}
    for row in (pind.get("top10_up") or []) + (pind.get("top10_down") or []):
        prev_map[row.get("name")] = row.get("amount")

    boards = []
    for r in (ind.get("top10_up") or []) + (ind.get("top10_down") or []):
        boards.append({
            "name": r.get("name"),
            "change": r.get("change"),
            "amount": r.get("amount"),
            "amount_change": _chg(r.get("amount"), prev_map.get(r.get("name"))),
            "up_count": None,
            "down_count": None,
            "limit_up_count": None,
            "constituent_count": None,
            "lead_name": None,
            "lead_code": None,
            "lead_limit_up": None,
        })

    candidates, qualified = _compute_resonance(boards, bench, "行业")
    # 简版：无 4 项有效 → 无正式排名；取涨幅最高者作为「板块表现观察」
    candidates.sort(key=lambda x: -(x["change"] if x["change"] is not None else -1e9))
    board = candidates[0] if candidates else None
    if board:
        board["raw_score"] = None  # 强制清除简版评分，避免 2/5 却显示分数
        board["representative_stocks"] = []
        board["representative_note"] = "板块成分股映射未接入，暂无法提供该板块内代表性个股；下方「个股红榜」为全市场高活跃上涨股，与板块归属无关。"

    return {
        "board": board,
        "benchmark": bench,
        "benchmark_name": BENCHMARK_NAME,
        "note": "历史日期的行业板块仅含同花顺涨跌 Top10，上涨家数占比、涨停密度、成交额环比等指标缺失，"
                "有效指标不足 4/5，未达到完整共振门槛，故不参与正式排名、不显示评分。",
        "qualified_full": False,
        "qualified_count": len(qualified),
        "source": "ths_top10",
    }


def _resonance_from_em(industry_boards, concept_boards, bench):
    """当日完整共振：东财行业 + 概念独立数据源、独立样本、独立排名。"""
    result = {"benchmark": bench, "benchmark_name": BENCHMARK_NAME, "source": "eastmoney_push2"}

    ind_candidates, ind_qualified = _compute_resonance(industry_boards, bench, "行业")
    con_candidates, con_qualified = _compute_resonance(concept_boards, bench, "概念")

    # 行业榜首 + 概念榜首
    ind_top = ind_qualified[0] if ind_qualified else None
    con_top = con_qualified[0] if con_qualified else None

    qualified_count = len(ind_qualified) + len(con_qualified)
    board = ind_top or con_top

    result.update({
        "board": board,
        "industry_top": ind_top,
        "concept_top": con_top,
        "qualified_full": board is not None,
        "qualified_count": qualified_count,
        "note": "",
    })
    if board is None:
        result["note"] = "当日行业与概念板块均不足 4/5 项有效指标，未产生正式共振排名，仅作板块表现观察。"
    else:
        result["note"] = (f"行业与概念板块独立排名；当前榜首为 {board['category']}「{board['name']}」，"
                          f"数据覆盖 {board['valid_count']}/5 项有效。")
    return result


def _build_resonance(daily, prev, em_data=None):
    bench = _benchmark_change(daily)
    if em_data is not None:
        return _resonance_from_em(em_data.get("industry", []), em_data.get("concept", []), bench)
    return _resonance_from_ths(daily, prev, bench)


# --------------------------------------------------------------------------
# 04 红黑榜
# --------------------------------------------------------------------------
def _build_industry_rankings(daily, prev, em_data=None):
    ind = daily.get("industry") or {}
    pind = (prev or {}).get("industry") or {}
    prev_map = {}
    for row in (pind.get("top10_up") or []) + (pind.get("top10_down") or []):
        prev_map[row.get("name")] = row.get("amount")

    def enrich(rows):
        out = []
        for r in rows or []:
            out.append({
                "name": r.get("name"),
                "change": r.get("change"),
                "amount": r.get("amount"),
                "ratio": r.get("ratio"),
                "amount_change": _chg(r.get("amount"), prev_map.get(r.get("name"))),
            })
        return out

    industry = {
        "red": enrich(ind.get("top10_up")),
        "black": enrich(ind.get("top10_down")),
        "source": ind.get("source"),
        "note": ind.get("note"),
        "as_of": ind.get("as_of"),
    }

    concept = {"red": None, "black": None, "note": "概念板块数据尚未接入，暂不生成概念红黑榜。"}
    if em_data is not None and em_data.get("concept"):
        cons = sorted(em_data["concept"], key=lambda x: -(x["change"] if x["change"] is not None else -1e9))
        def _to_row(b):
            return {"name": b.get("name"), "change": b.get("change"), "amount": b.get("amount"),
                    "ratio": None, "amount_change": b.get("amount_change")}
        concept["red"] = [_to_row(b) for b in cons[:10]]
        concept["black"] = [_to_row(b) for b in cons[-10:][::-1]]
        concept["note"] = "概念板块红黑榜（东财概念板块，当日）。"

    # 若当日有东财行业全量，行业红黑榜扩展为全量 Top10
    if em_data is not None and em_data.get("industry"):
        inds = sorted(em_data["industry"], key=lambda x: -(x["change"] if x["change"] is not None else -1e9))
        def _to_ir(b):
            return {"name": b.get("name"), "change": b.get("change"), "amount": b.get("amount"),
                    "ratio": None, "amount_change": b.get("amount_change")}
        industry["red"] = [_to_ir(b) for b in inds[:10]]
        industry["black"] = [_to_ir(b) for b in inds[-10:][::-1]]
        industry["source"] = "eastmoney_push2"
        industry["note"] = "行业板块红黑榜（东财行业板块，当日，全行业样本）。"

    return {"industry": industry, "concept": concept}


def _build_stock_rankings(daily):
    active = daily.get("active_stocks") or []
    red = sorted(active, key=lambda x: -(x.get("change_pct") or 0))[:6]
    ld = (daily.get("emotion") or {}).get("ld_over10e") or []
    black = sorted(ld, key=lambda x: (x.get("change") or 0))[:6]
    return {
        "red": [{"code": s.get("code"), "name": s.get("name"), "change_pct": s.get("change_pct"),
                 "amount": s.get("amount"), "is_limit_up": s.get("is_limit_up")} for s in red],
        "black": [{"code": s.get("code"), "name": s.get("name"), "change": s.get("change"),
                   "amount": s.get("amount"), "board": s.get("board")} for s in black],
        "note": "个股红榜取当日「成交额≥5亿且涨幅≥5%」的高活跃上涨股；黑榜取「跌停且成交额≥10亿」个股。"
                "全市场涨跌个股榜需全市场快照，当前未接入。",
    }


# --------------------------------------------------------------------------
# 03 板块涨跌 Top5（替代最强共振主卡 / 独立红黑榜 / 个股活跃榜）
# --------------------------------------------------------------------------
def _sort_sector(boards, reverse):
    """按涨跌幅排序板块，缺失排最后。"""
    return sorted(boards, key=lambda b: (b.get("change") if b.get("change") is not None else -1e9),
                  reverse=reverse)


def _sector_row(b, category):
    return {
        "name": b.get("name"),
        "category": category,
        "change": b.get("change"),
        "amount": b.get("amount"),
        "limit_up_count": b.get("limit_up_count"),
        "limit_down_count": b.get("limit_down_count"),
    }


def _build_sector_top5(daily, em_data):
    """板块涨跌 Top5：行业/概念独立排序，各取上涨 Top5、下跌 Top5。

    - 当日（东财数据，日期一致）：行业/概念全量样本，含涨停/跌停家数。
    - 历史（无东财）：行业仅同花顺 Top10，无涨停/跌停家数；概念未采集。
    """
    ind = daily.get("industry") or {}
    ths_up = ind.get("top10_up") or []
    ths_down = ind.get("top10_down") or []

    em_ind = (em_data or {}).get("industry")
    em_con = (em_data or {}).get("concept")

    if em_ind:
        ind_up = _sort_sector(em_ind, True)[:5]
        ind_down = _sort_sector(em_ind, False)[:5]
        industry = {
            "up": [_sector_row(b, "行业") for b in ind_up],
            "down": [_sector_row(b, "行业") for b in ind_down],
            "source": "eastmoney_push2",
            "note": "东财行业板块全量样本（当日），涨停/跌停家数按板块真实成分股计算。",
        }
    else:
        up_rows = _sort_sector([{"name": r.get("name"), "change": r.get("change"),
                                 "amount": r.get("amount"), "limit_up_count": None,
                                 "limit_down_count": None} for r in ths_up], True)[:5]
        down_rows = _sort_sector([{"name": r.get("name"), "change": r.get("change"),
                                   "amount": r.get("amount"), "limit_up_count": None,
                                   "limit_down_count": None} for r in ths_down], False)[:5]
        industry = {
            "up": [_sector_row(b, "行业") for b in up_rows],
            "down": [_sector_row(b, "行业") for b in down_rows],
            "source": "ths_top10",
            "note": "历史日期行业板块仅同花顺涨跌 Top10，涨停/跌停家数未采集（历史成分股不可回溯）。",
        }

    if em_con:
        con_up = _sort_sector(em_con, True)[:5]
        con_down = _sort_sector(em_con, False)[:5]
        concept = {
            "up": [_sector_row(b, "概念") for b in con_up],
            "down": [_sector_row(b, "概念") for b in con_down],
            "source": "eastmoney_push2",
            "note": "东财概念板块全量样本（当日），涨停/跌停家数按板块真实成分股计算。",
        }
    else:
        concept = {
            "up": None, "down": None, "source": None,
            "note": "概念板块历史数据未采集，暂不生成概念板块涨跌 Top5。",
        }

    return {"industry": industry, "concept": concept}


# --------------------------------------------------------------------------
# 04 成交额≥10亿股票市值分布（六档饼图数据）
# --------------------------------------------------------------------------
MKT_CAP_BUCKETS = [
    ("<50亿", 0, 50),
    ("50-100亿", 50, 100),
    ("100-200亿", 100, 200),
    ("200-500亿", 200, 500),
    ("500-1000亿", 500, 1000),
    (">1000亿", 1000, None),
]


def _build_mktcap_dist(market_stocks):
    """成交额≥10亿股票的总市值六档分布（按家数）。

    market_stocks：全市场股票快照列表 [{code,name,amount,mktcap}]。
    无数据时返回 sample_total=None 并附说明（不复用全A分档）。
    """
    if not market_stocks:
        return {"buckets": [], "sample_total": None, "missing_mktcap": None,
                "note": "当日全市场股票快照缺失，无法计算成交额≥10亿股票的市值分布。"}

    over10 = [s for s in market_stocks if s.get("amount") is not None and s["amount"] >= 10]
    valid = [s for s in over10 if s.get("mktcap") is not None]
    missing = len(over10) - len(valid)

    buckets = []
    for label, lo, hi in MKT_CAP_BUCKETS:
        if hi is None:
            cnt = sum(1 for s in valid if s["mktcap"] >= lo)
        else:
            cnt = sum(1 for s in valid if lo <= s["mktcap"] < hi)
        buckets.append({
            "label": label,
            "count": cnt,
            "pct": round(cnt / len(valid) * 100, 2) if valid else None,
        })

    return {
        "buckets": buckets,
        "sample_total": len(valid),
        "missing_mktcap": missing,
        "note": (f"成交额≥10亿股票共 {len(over10)} 家，其中 {len(valid)} 家有市值数据参与分档"
                 f"{'，' + str(missing) + ' 家缺市值单独说明' if missing else ''}。"),
    }


# --------------------------------------------------------------------------
# 05 事件（公告 / 监管 / 媒体）
# --------------------------------------------------------------------------
def _collect_events(trade_date, with_events):
    """采集公告/监管/媒体事件。返回 (risk_events, source_coverage_extra)。"""
    base = {
        "events": [],
        "coverage_status": "not_checked",
        "message": "",
        "sources": [],
    }
    cov = {}

    if not with_events:
        base["coverage_status"] = "not_checked"
        base["message"] = "本轮未执行事件采集（--collect-events 未开启）。"
        return base, cov

    # 1) 巨潮公告（可回溯历史）
    if cninfo_announcements is not None:
        ann_events, ann_status, ann_meta = cninfo_announcements.collect(trade_date)
        base["events"].extend(ann_events)
        base["sources"].append({
            "name": "巨潮资讯网", "url": "https://www.cninfo.com.cn/",
            "status": ann_status, "meta": ann_meta,
        })
        cov["cninfo_announcements"] = {
            "status": "available" if ann_status == "success_with_events"
                      else ("available" if ann_status == "success_no_match" else "unavailable"),
            "detail": f"巨潮公告（采集 {ann_meta.get('collected', 0)} 条，重点 {ann_meta.get('important_events', 0)} 条）。",
        }
    else:
        base["sources"].append({"name": "巨潮资讯网", "url": "https://www.cninfo.com.cn/", "status": "unavailable",
                                "meta": {"detail": "采集适配器不可用"}})

    # 2) 交易所 + 证监会监管
    if regulators is not None:
        for s in regulators.SOURCES:
            evs, st, meta = s["fn"](trade_date)
            base["events"].extend(evs)
            base["sources"].append({"name": s["name"], "url": s["url"], "status": st, "meta": meta})
            cov[f"regulator_{s['key']}"] = {"status": "available" if st.startswith("success") else "unavailable",
                                            "detail": meta.get("detail", "")}
    else:
        for name, url in [("上交所监管措施", "https://www.sse.com.cn/"),
                          ("深交所监管信息公开", "https://www.szse.cn/"),
                          ("证监会行政处罚", "http://www.csrc.gov.cn/")]:
            base["sources"].append({"name": name, "url": url, "status": "unavailable",
                                    "meta": {"detail": "采集适配器不可用"}})

    # 去重（同一公司同一事项多源转载只保留一条）
    if event_lib is not None:
        base["events"] = event_lib.deduplicate(base["events"])

    # 公告分组：①公司回购 ②风险事项/监管/股东减持（保留完整 events 溯源）
    base["groups"] = _group_events(base["events"])
    base["total_events"] = len(base["events"])
    base["displayed_events"] = sum(len(v) for v in base["groups"].values())

    # 覆盖状态判定
    statuses = [s["status"] for s in base["sources"]]
    if not statuses:
        base["coverage_status"] = "not_checked"
    elif all(st == "unavailable" for st in statuses):
        base["coverage_status"] = "unavailable"
    elif any(st.startswith("success") for st in statuses) and any(st == "unavailable" for st in statuses):
        base["coverage_status"] = "partial"
    elif all(st.startswith("success") or st == "success_no_match" for st in statuses):
        base["coverage_status"] = "complete"
    else:
        base["coverage_status"] = "partial"

    displayed = base["displayed_events"]
    if displayed:
        nb = len(base["groups"].get("buyback", []))
        nr = len(base["groups"].get("risk", []))
        base["message"] = f"本次采集范围内共 {displayed} 条重点事件（公司回购 {nb} 条，风险/监管/减持 {nr} 条）。"
    elif base["coverage_status"] in ("complete", "success"):
        base["message"] = "本次采集范围内未发现符合筛选条件的事件。"
    elif base["coverage_status"] == "partial":
        base["message"] = "部分信息来源暂不可用，本次信息覆盖不完整。"
    else:
        base["message"] = "公告、监管及媒体信息来源均不可用，本次信息覆盖不完整，无法判定「无事件」。"

    return base, cov


def _group_events(events, buyback_n=12, risk_n=18):
    """公告分两组：①公司回购 ②风险事项/监管/股东减持。同公司同类别合并去重，各取前 N 条。"""
    buyback = []
    risk = []
    seen_buyback = set()
    seen_risk = set()
    for e in sorted(events, key=lambda x: (x.get("published_at") or ""), reverse=True):
        title = e.get("title") or ""
        code = e.get("stock_code") or ""
        if "回购" in title:
            if code not in seen_buyback and len(buyback) < buyback_n:
                seen_buyback.add(code)
                buyback.append(e)
        elif e.get("category_group") == "risk" or "减持" in title or "质押" in title:
            key = f"{code}|{e.get('event_category')}"
            if key not in seen_risk and len(risk) < risk_n:
                seen_risk.add(key)
                risk.append(e)
    return {"buyback": buyback, "risk": risk}


def _build_events_message(events):
    n = len(events)
    cats = {}
    for e in events:
        cats[e.get("event_category")] = cats.get(e.get("event_category"), 0) + 1
    cat_str = "、".join(f"{k} {v} 条" for k, v in sorted(cats.items(), key=lambda x: -x[1]))
    return f"本次采集范围内共 {n} 条经筛选的重点事件（{cat_str}）。"


# --------------------------------------------------------------------------
# 06 今日综合观察（客观中性）
# --------------------------------------------------------------------------
def _build_comprehensive(daily, m, resonance, rankings, risk):
    parts = []
    bench = _benchmark_change(daily)
    if bench is not None:
        if bench > 0.5:
            parts.append(f"市场整体收涨（全A基准 {bench:+.2f}%）。")
        elif bench < -0.5:
            parts.append(f"市场整体收跌（全A基准 {bench:+.2f}%）。")
        else:
            parts.append("市场整体窄幅震荡。")

    ta = m["total_amount"]
    if ta["value"] is not None and ta["change"] is not None:
        parts.append(f"两市成交额 {ta['value']:.0f} 亿元，较上一交易日{'增加' if ta['change'] > 0 else '减少'} "
                     f"{abs(ta['change']):.0f} 亿元。")

    b = resonance.get("board")
    if b and resonance.get("qualified_full"):
        parts.append(f"{b['category']}板块中，「{b['name']}」综合统计排名居前（涨幅 {b['change']:+.2f}%"
                     f"{'，相对大盘 ' + format(b['relative_strength'], '+.2f') + '%' if b['relative_strength'] is not None else ''}"
                     f"，数据覆盖 {b['valid_count']}/5 项有效指标）。")
    elif b:
        parts.append(f"行业板块中，「{b['name']}」当日涨幅 {b['change']:+.2f}%（简版观察，未达完整共振门槛）。")

    ir = rankings.get("industry", {})
    red = ir.get("red") or []
    black = ir.get("black") or []
    if red and black:
        parts.append(f"行业板块涨幅居前为「{red[0]['name']}」，跌幅居前为「{black[0]['name']}」。")

    if risk.get("events"):
        parts.append(risk["message"])
    elif risk.get("coverage_status") in ("unavailable", "partial"):
        parts.append(risk["message"])

    parts.append("以上为基于当日真实行情数据、上市公司公告及公开信息的客观记录，不构成任何投资建议或买卖意见。")
    return "".join(parts)


# --------------------------------------------------------------------------
# 数据源覆盖
# --------------------------------------------------------------------------
def _build_source_coverage(daily, sector_top5, em_data, events_cov):
    o = daily.get("overview", {})
    ind = daily.get("industry") or {}
    cov = {
        "core_metrics": {
            "status": "available" if o.get("total_amount") is not None else "missing",
            "detail": "两市成交额、涨跌停、10亿以上家数、Top50集中度、两融来自现有每日快照。",
        },
        "indexes": {
            "status": "available" if any(i.get("close") is not None for i in _build_indexes(daily)) else "missing",
            "detail": "六大指数收盘与涨跌幅（上证/深成/创业板指/科创50/中证500/中证1000），涨跌点数按涨跌幅反推。",
        },
        "industry_board": {
            "status": "available" if (em_data and em_data.get("industry")) or (ind.get("top10_up") or ind.get("top10_down")) else "missing",
            "detail": ("东财行业板块全量样本（含涨跌停家数）。" if (em_data and em_data.get("industry"))
                       else f"行业板块涨跌 Top10（源：{ind.get('source', '—')}，无涨跌停家数）。"),
        },
        "concept_board": {
            "status": "available" if (em_data and em_data.get("concept")) else "unavailable",
            "detail": "东财概念板块全量样本。" if (em_data and em_data.get("concept")) else "概念板块数据尚未接入（仅当日可采集，历史不可回溯）。",
        },
        "market_mktcap": {
            "status": "available" if (events_cov.get("market_stocks") or {}).get("status") == "available" else "unavailable",
            "detail": "成交额≥10亿股票市值分布（东财全市场快照，当日；历史不可回溯）。",
        },
        "risk_events": {
            "status": "available" if events_cov else "unavailable",
            "detail": "上市公司公告、交易所监管采集状态见 risk_events.sources。",
        },
    }
    cov.update(events_cov or {})
    return cov


def _build_warnings(daily, sector_top5, mktcap_dist, risk):
    warnings = []
    ind_src = (sector_top5.get("industry") or {}).get("source")
    if ind_src == "ths_top10":
        warnings.append("行业板块为历史 Top10（同花顺），涨停/跌停家数未采集，板块涨跌停数据缺失。")
    if (sector_top5.get("concept") or {}).get("up") is None:
        warnings.append("概念板块历史数据未采集，概念涨跌 Top5 暂缺。")
    if mktcap_dist.get("sample_total") is None:
        warnings.append("成交额≥10亿股票市值分布数据缺失（当日全市场快照不可回溯，历史未采集）。")
    if risk.get("coverage_status") in ("unavailable", "partial"):
        warnings.append("公告/监管信息覆盖不完整：部分来源暂不可用，无法判定「无事件」。")
    return warnings


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------
def build_observation(date, dates, with_events=False, with_boards=False):
    daily_path = os.path.join(DAILY_DIR, f"{date}.json")
    if not os.path.exists(daily_path):
        return None
    daily = _read_json(daily_path)
    prev_date = _prev_trading_day(dates, date)
    prev = None
    if prev_date:
        ppath = os.path.join(DAILY_DIR, f"{prev_date}.json")
        if os.path.exists(ppath):
            prev = _read_json(ppath)

    # 当日板块 + 全市场股票采集：仅当 with_boards 且采集日 == 交易日期（保证数据日期一致）
    em_data = None
    market_stocks = None
    em_board_cov = {}
    if with_boards and eastmoney_boards is not None:
        today = datetime.now(_CN_TZ).strftime("%Y%m%d")
        if today == date:
            try:
                ind_boards, ind_st, _ = eastmoney_boards.collect("industry")
                con_boards, con_st, _ = eastmoney_boards.collect("concept")
                em_data = {"industry": ind_boards, "concept": con_boards}
                em_board_cov = {
                    "eastmoney_industry": {"status": "available" if ind_boards else "unavailable",
                                           "detail": f"东财行业板块（{len(ind_boards)} 个）。"},
                    "eastmoney_concept": {"status": "available" if con_boards else "unavailable",
                                          "detail": f"东财概念板块（{len(con_boards)} 个）。"},
                }
            except Exception as exc:  # noqa: BLE001
                em_data = None
                em_board_cov = {"eastmoney_boards": {"status": "unavailable", "detail": str(exc)}}
            # 全市场股票快照（市值饼图）
            try:
                market_stocks, _ms_total = eastmoney_boards.fetch_market_stocks()
                em_board_cov["market_stocks"] = {
                    "status": "available" if market_stocks else "unavailable",
                    "detail": f"全市场股票快照（{len(market_stocks)} 只，含成交额与总市值）。"}
            except Exception as exc:  # noqa: BLE001
                em_board_cov["market_stocks"] = {"status": "unavailable", "detail": str(exc)}
        else:
            em_board_cov = {"eastmoney_boards": {
                "status": "unavailable",
                "detail": f"东财板块/全市场股票为实时数据（今日 {today}），与交易日 {date} 不一致，未采用，"
                          "板块与市值分布数据以复盘台快照为准。"}}

    m = _build_market_metrics(daily, prev)
    indexes = _build_indexes(daily)
    sector_top5 = _build_sector_top5(daily, em_data)
    mktcap_dist = _build_mktcap_dist(market_stocks)
    risk, events_cov = _collect_events(date, with_events)

    now = _now_cn()
    prev_date_iso = _fmt_date(prev_date) if prev_date else ""

    return {
        "trade_date": date,
        "generated_at": now,
        "report_trade_date": date,
        "coverage_window_start": prev_date_iso,
        "coverage_cutoff_at": now,
        "market_metrics": m,
        "indexes": indexes,
        "market_summary": _build_market_summary(m, indexes, sector_top5, date),
        "sector_top5": sector_top5,
        "mktcap_dist": mktcap_dist,
        "risk_events": risk,
        "source_coverage": _build_source_coverage(daily, sector_top5, em_data, {**em_board_cov, **events_cov}),
        "data_warnings": _build_warnings(daily, sector_top5, mktcap_dist, risk),
        "ai_generated": False,
        "generation_mode": "规则自动生成（未接入 AI Provider）",
        "disclaimer": "本材料根据公开行情、上市公司公告、交易所及监管信息和公开媒体报道整理，"
                      "仅作当日市场信息记录与事实展示，不构成投资建议、证券买卖意见或收益承诺。",
    }


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--date", help="单个交易日 YYYYMMDD")
    g.add_argument("--all", action="store_true", help="为所有存在快照的交易日生成")
    ap.add_argument("--collect-events", action="store_true", help="采集公告/监管/媒体事件（仅对最新交易日建议开启）")
    ap.add_argument("--collect-boards", action="store_true", help="采集东财板块（仅当日有效）")
    args = ap.parse_args()

    dates = _load_trading_days()
    os.makedirs(OUT_DIR, exist_ok=True)

    if args.all:
        targets = sorted(d.replace(".json", "") for d in os.listdir(DAILY_DIR) if d.endswith(".json"))
    else:
        targets = [args.date]

    written = 0
    for date in targets:
        obs = build_observation(date, dates,
                                with_events=args.collect_events,
                                with_boards=args.collect_boards)
        if obs is None:
            print(f"[skip] {date}: 快照缺失")
            continue
        out = os.path.join(OUT_DIR, f"{date}.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(obs, f, ensure_ascii=False, indent=2)
        written += 1
        ind_up = (obs["sector_top5"].get("industry") or {}).get("up") or []
        ind_down = (obs["sector_top5"].get("industry") or {}).get("down") or []
        nb = len(obs["risk_events"].get("groups", {}).get("buyback", []))
        nr = len(obs["risk_events"].get("groups", {}).get("risk", []))
        top = ind_up[0]["name"] if ind_up else "无"
        print(f"[ok] {date}: 行业涨榜首={top}, 板块Top5(涨{len(ind_up)}/跌{len(ind_down)}), "
              f"回购{nb}条 风险{nr}条")
    print(f"完成：写入 {written} 个。输出目录 {OUT_DIR}")


if __name__ == "__main__":
    main()
