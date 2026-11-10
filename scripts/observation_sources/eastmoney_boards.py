# -*- coding: utf-8 -*-
"""东方财富公开板块行情采集适配器（行业 / 概念 / 板块成分股）。

接口（公开 push2 行情接口）：
- 行业板块：fs=m:90+t:2（total≈496）
- 概念板块：fs=m:90+t:3（total≈531）
- 板块成分股：fs=b:BKxxxx（返回该板块全部成分股）

字段口径（以真实返回为准）：
- f3  板块/个股涨跌幅（%，已含符号）
- f6  成交额（元）
- f12 代码（板块 BKxxxx / 个股 6 位代码）
- f14 名称
- f104 上涨家数 / f105 下跌家数（板块内成分股统计）
- f128 领涨股名称 / f140 领涨股代码 / f141 领涨股是否涨停(1/0)

限制：push2 板块接口为「实时行情」，仅反映采集时刻的最新数据，
无法回溯历史交易日；历史日期的板块表现须以复盘台 daily 快照为准。
"""
import time
import urllib.request

from . import events  # noqa: F401  (分类逻辑复用，当前板块采集无需事件分类)

_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "Chrome/120.0 Safari/537.36",
    "Referer": "https://stock.eastmoney.com/",
}

_PUSH2 = "https://push2.eastmoney.com/api/qt/clist/get"

# 板块类型 → fs 参数
SECTOR_FS = {
    "industry": "m:90+t:2",   # 行业板块
    "concept": "m:90+t:3",    # 概念板块
}


def _get_json(url):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=15) as r:
        body = r.read().decode("utf-8", "replace")
    import json
    return json.loads(body)


def fetch_sector_list(sector_type, page_size=100, max_pages=0, delay=0.2):
    """抓取行业/概念板块全量列表（分页）。

    返回板块 dict 列表，每项含：
      code, name, change, amount(亿), up_count, down_count,
      lead_name, lead_code, lead_limit_up
    """
    fs = SECTOR_FS[sector_type]
    fields = "f3,f6,f12,f14,f104,f105,f128,f140,f141"
    page = 1
    out = []
    total = None
    while True:
        url = (f"{_PUSH2}?pn={page}&pz={page_size}&po=1&np=1&fltt=2&invt=2"
               f"&fid=f3&fs={fs}&fields={fields}")
        obj = _get_json(url)
        data = obj.get("data") or {}
        total = data.get("total", 0)
        diff = data.get("diff") or []
        for d in diff:
            amt = d.get("f6")
            out.append({
                "code": d.get("f12"),
                "name": d.get("f14"),
                "change": d.get("f3"),
                "amount": round(amt / 1e8, 2) if amt is not None else None,  # 元 → 亿元
                "up_count": d.get("f104"),
                "down_count": d.get("f105"),
                "lead_name": d.get("f128"),
                "lead_code": d.get("f140"),
                "lead_limit_up": bool(d.get("f141")),
            })
        if total is None or len(out) >= total or not diff:
            break
        if max_pages and page >= max_pages:
            break
        page += 1
        time.sleep(delay)
    return out, total


def _limit_up_threshold(code, name):
    """根据证券代码/名称返回涨停近似阈值（%）。"""
    c = (code or "").upper()
    n = (name or "").upper()
    if "ST" in n:
        return 4.9  # ST 股 5% 涨跌停
    if c.startswith(("30", "688")):   # 创业板 / 科创板
        return 19.9
    if c.startswith(("8", "4", "92")):  # 北交所
        return 29.9
    return 9.9  # 主板


def is_limit_up(code, name, pct):
    """判断单只成分股是否涨停（按涨跌幅阈值近似判断）。"""
    if pct is None:
        return False
    return pct >= _limit_up_threshold(code, name)


def is_limit_down(code, name, pct):
    """判断单只成分股是否跌停（按涨跌幅阈值近似判断）。"""
    if pct is None:
        return False
    return pct <= -_limit_up_threshold(code, name)


def fetch_market_stocks(page_size=500, max_pages=0, delay=0.2):
    """抓取全市场 A 股快照（成交额 + 总市值），用于「成交额≥10亿市值分布」。

    返回 {code, name, amount(亿), mktcap(亿)} 列表。
    """
    fs = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
    fields = "f6,f12,f14,f20"
    page = 1
    out = []
    total = None
    while True:
        url = (f"{_PUSH2}?pn={page}&pz={page_size}&po=1&np=1&fltt=2&invt=2"
               f"&fid=f6&fs={fs}&fields={fields}")
        obj = _get_json(url)
        data = obj.get("data") or {}
        total = data.get("total", 0)
        diff = data.get("diff") or []
        for d in diff:
            amt = d.get("f6")
            cap = d.get("f20")
            out.append({
                "code": d.get("f12"),
                "name": d.get("f14"),
                "amount": round(amt / 1e8, 2) if amt is not None else None,
                "mktcap": round(cap / 1e8, 2) if cap is not None else None,
            })
        if total is None or len(out) >= total or not diff:
            break
        if max_pages and page >= max_pages:
            break
        page += 1
        time.sleep(delay)
    return out, total


def fetch_constituents(bk_code, page_size=200, delay=0.15):
    """抓取板块成分股列表。返回 {code, name, change, amount} 列表。"""
    fields = "f2,f3,f6,f12,f14"
    page = 1
    out = []
    total = None
    while True:
        url = (f"{_PUSH2}?pn={page}&pz={page_size}&po=1&np=1&fltt=2&invt=2"
               f"&fid=f3&fs=b:{bk_code}&fields={fields}")
        obj = _get_json(url)
        data = obj.get("data") or {}
        total = data.get("total", 0)
        diff = data.get("diff") or []
        for d in diff:
            amt = d.get("f6")
            out.append({
                "code": d.get("f12"),
                "name": d.get("f14"),
                "change": d.get("f3"),
                "amount": round(amt / 1e8, 2) if amt is not None else None,
            })
        if total is None or len(out) >= total or not diff:
            break
        page += 1
        time.sleep(delay)
    return out


def collect(sector_type, top_n=30, constituent_delay=0.15):
    """适配器入口：抓取板块列表，并对涨幅榜前 top_n 板块抓成分股计算涨停密度。

    返回 (boards, status, meta)：
      boards  板块列表（涨幅榜前列的板块附加 limit_up_count）
      status  success_with_events / success_no_match / partial / unavailable
    """
    try:
        boards, total = fetch_sector_list(sector_type)
    except Exception as exc:  # noqa: BLE001
        return [], "unavailable", {"error": str(exc)}

    if not boards:
        return [], "success_no_match", {"total": 0}

    # 涨幅榜前 top_n 与跌幅榜前 top_n 都抓成分股，计算板块内涨停/跌停家数
    ranked = sorted(boards, key=lambda b: -(b["change"] if b["change"] is not None else -1e9))
    seen = set()
    targets = []
    for b in ranked[:top_n] + ranked[-top_n:][::-1]:
        if b["code"] not in seen:
            seen.add(b["code"])
            targets.append(b)

    stats = {}
    for b in targets:
        try:
            cons = fetch_constituents(b["code"], delay=constituent_delay)
        except Exception:  # noqa: BLE001
            cons = []
        if cons:
            lu = sum(1 for x in cons if is_limit_up(x["code"], x["name"], x["change"]))
            ld = sum(1 for x in cons if is_limit_down(x["code"], x["name"], x["change"]))
            stats[b["code"]] = {"limit_up_count": lu, "limit_down_count": ld,
                                "constituent_count": len(cons)}
        else:
            stats[b["code"]] = {"limit_up_count": None, "limit_down_count": None,
                                "constituent_count": None}

    for b in boards:
        st = stats.get(b["code"], {})
        b["limit_up_count"] = st.get("limit_up_count")
        b["limit_down_count"] = st.get("limit_down_count")
        b["constituent_count"] = st.get("constituent_count")

    status = "success_with_events" if boards else "success_no_match"
    meta = {
        "total": total,
        "collected": len(boards),
        "constituents_fetched": len([k for k, v in stats.items() if v.get("constituent_count")]),
    }
    return boards, status, meta
