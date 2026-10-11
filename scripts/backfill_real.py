#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复盘台 · 真实数据本地回补（备源通道：baostock / 新浪 / 腾讯 / 交易所）

背景：本机网络对东财 push2 系列接口存在反爬封锁，此脚本用备源完成一次性历史建仓：
  --stage calendar   交易日历（新浪 tool_trade_date_hist_sina）
  --stage index      指数成交额序列 2015 至今（baostock）+ 两市总额(沪+深) + 全A代理
  --stage stocks     全市场逐股日线 2021 至今（baostock，断点续跑）
                     → 涨停/跌停家数、10亿以上家数、前10集中度序列 + 当日明细缓存
  --stage stocks_ext 历史扩展：逐股日线延伸到 1997 起（独立检查点，完成后合并入主聚合并重写序列；
                     创业板按 2020-08-24 注册制分界取 10%/20% 阈值；仅含当前成分股，早期历史有幸存者偏差）
  --stage margin     合并 scripts/_cache/margin_ifind.json → series/margin.json
  --stage snapshot   构建最新交易日 daily/*.json（腾讯总市值 + THS 行业 + 各缓存）
  --stage finalize   重建 index_agg / latest.json

涨跌停判定（与规格一致）：主板 |涨跌幅|>=9.9%；创业板(300/301)/科创板(688) >=19.9%；
剔除 ST/*ST；剔除上市不足 250 个交易日；不含北交所（baostock 无北交所数据）。
"""
import argparse
import datetime
import heapq
import json
import os
import pickle
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from modules.common import DATA_DIR, atomic_write_json, log, now_iso  # noqa: E402
from modules import compute  # noqa: E402

CACHE = os.path.join(HERE, "_cache")
os.makedirs(CACHE, exist_ok=True)

INDEX_START = "2015-01-01"
STOCKS_START = "2021-01-01"
EXTEND_START = "1997-01-01"  # 涨跌停制度 1996-12-16 起，序列向过去延伸到此处
EXTEND_END = "2020-12-31"    # 与主窗口 [STOCKS_START, target] 无缝衔接
TARGET_DATE = None  # 由 calendar 阶段确定（最近已收盘交易日）


# ---------------------------------------------------------------- 通用
def write_series_bulk(key: str, name: str, unit: str, values: dict):
    """批量写序列：一次构建全部点并计算 rank_year/rank_1y/rank_all/pctile（避免逐点 O(n^3)）"""
    points = [{"date": d, "value": v} for d, v in sorted(values.items()) if v is not None]
    vals = [p["value"] for p in points]
    dates = [p["date"] for p in points]
    for i, p in enumerate(points):
        v = p["value"]
        p["rank_all"] = compute.rank_of(vals, v)
        p["pctile"] = compute.pctile(vals, v)
        year_vals = [q["value"] for q, d in zip(points, dates) if d.startswith(p["date"][:4])]
        p["rank_year"] = compute.rank_of(year_vals, v) if year_vals else None
        lo = max(0, i - 243)
        p["rank_1y"] = compute.rank_of(vals[lo:i + 1], v)
    atomic_write_json(os.path.join(DATA_DIR, "series", f"{key}.json"),
                      {"key": key, "name": name, "unit": unit,
                       "updated_at": now_iso(), "points": points})
    log(f"序列 {key} 写入 {len(points)} 点（{dates[0]} ~ {dates[-1]}）" if points else f"序列 {key} 空")


def read_series_points(key: str) -> list:
    p = os.path.join(DATA_DIR, "series", f"{key}.json")
    if not os.path.exists(p):
        return []
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f).get("points", [])


def last_closed(dates: list) -> str:
    now = datetime.datetime.now()
    today = now.strftime("%Y%m%d")
    past = [d for d in dates if d <= today]
    if not past:
        raise RuntimeError("交易日历为空")
    if past[-1] == today and now.hour < 16 and len(past) >= 2:
        return past[-2]
    return past[-1]


# ---------------------------------------------------------------- calendar
def stage_calendar():
    import akshare as ak
    df = ak.tool_trade_date_hist_sina()
    dates = sorted({str(d).replace("-", "") for d in df["trade_date"].tolist()})
    dates = [d for d in dates if "20100101" <= d <= datetime.datetime.now().strftime("%Y%m%d")]
    target = last_closed(dates)
    atomic_write_json(os.path.join(DATA_DIR, "meta", "trading_days.json"),
                      {"list": dates, "latest": target, "updated_at": now_iso(),
                       "source_versions": {"akshare": ak.__version__, "baostock": "ok"}})
    with open(os.path.join(CACHE, "target_date.txt"), "w") as f:
        f.write(target)
    log(f"交易日历 {len(dates)} 天，最新已收盘交易日 {target}")
    return target


def _target() -> str:
    with open(os.path.join(CACHE, "target_date.txt")) as f:
        return f.read().strip()


# ---------------------------------------------------------------- index
BS_INDEX = {
    "sh000001": "上证指数", "sz399001": "深证成指", "sz399006": "创业板指",
    "sh000016": "上证50", "sh000300": "沪深300", "sz399673": "创业板50",
    "sh000905": "中证500", "sh000906": "中证800", "sh000852": "中证1000",
    "hstech_513180": "恒生科技(513180近似)",
}


def stage_index():
    import baostock as bs
    target = _target()
    end = f"{target[:4]}-{target[4:6]}-{target[6:]}"
    bs.login()
    out = {}
    for code, name in BS_INDEX.items():
        bs_code = ("sh.513180" if code == "hstech_513180"
                   else f"{code[:2]}.{code[2:]}")  # sh000001 → sh.000001
        rs = bs.query_history_k_data_plus(bs_code, "date,amount",
                                          start_date=INDEX_START, end_date=end, frequency="d")
        rows = []
        while rs.error_code == "0" and rs.next():
            rows.append(rs.get_row_data())
        vals = {}
        for d, amt in rows:
            if amt:
                vals[d.replace("-", "")] = round(float(amt) / 1e8, 2)
        if vals:
            write_series_bulk(f"index_amount_{code}", name, "亿元", vals)
            out[code] = vals
            log(f"{code} {name}: {len(vals)} 点")
        else:
            log(f"警告：{code} 无数据")
    bs.logout()

    # 两市成交额 = 沪 + 深（指数代理口径）；全A代理(sh000985)同值
    sh, sz = out.get("sh000001", {}), out.get("sz399001", {})
    total = {d: round(sh[d] + sz[d], 2) for d in sh if d in sz}
    write_series_bulk("total_amount", "两市成交额", "亿元", total)
    write_series_bulk("index_amount_sh000985", "中证全指(沪深合计代理)", "亿元", total)
    with open(os.path.join(CACHE, "index_amounts.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    log(f"两市成交额序列 {len(total)} 点")


# ---------------------------------------------------------------- stocks
def _a_share_codes(bs, day: str) -> dict:
    """{bs_code: name}，沪深 A 股（不含北交所/基金/指数）"""
    rs = bs.query_all_stock(day=day)
    out = {}
    while rs.error_code == "0" and rs.next():
        code, _status, name = rs.get_row_data()
        pure = code.split(".")[-1]
        if code.startswith(("sh.60", "sh.68", "sz.00", "sz.30")) and len(pure) == 6:
            out[code] = name
    return out


def _fetch_daily(bs, code, name, start, end):
    """带断线重连重试的日线拉取，返回 rows（3 次重试均失败返回 []）"""
    import time as _time
    rows = []
    err = ""
    for attempt in range(3):
        try:
            rs = bs.query_history_k_data_plus(
                code, "date,close,preclose,pctChg,isST,amount,tradestatus",
                start_date=start, end_date=end, frequency="d", adjustflag="3")
            if rs.error_code == "0":
                rows = []
                while rs.next():
                    rows.append(rs.get_row_data())
                return rows
            err = f"{rs.error_code}:{rs.error_msg}"
        except Exception as e:  # noqa: BLE001
            err = str(e)[:80]
        log(f"{code} {name} 查询失败({err})，重连重试 {attempt + 1}/3")
        try:
            bs.logout()
        except Exception:  # noqa: BLE001
            pass
        _time.sleep(2)
        bs.login()
        _time.sleep(1)
    return rows


def _board_of(code: str) -> str:
    p = code.split(".")[-1][:3]
    if p in ("300", "301"):
        return "创业板"
    if p == "688":
        return "科创板"
    return "主板"


def _limit_threshold(code: str, d: str) -> float:
    """涨跌停阈值：科创板恒为 20%；创业板 2020-08-24 注册制后 20%，此前 10%"""
    p = code.split(".")[-1][:3]
    if p == "688":
        return 19.9
    if p in ("300", "301") and d >= "20200824":
        return 19.9
    return 9.9


def _aggregate_rows(agg, code: str, name: str, rows: list):
    """把一只股票的一段日线 rows 聚合进 agg（涨跌停/10亿+/top60/计数）"""
    for i, (d, close, preclose, pct, is_st, amount, tstatus) in enumerate(rows):
        d = d.replace("-", "")
        if tstatus != "1" or not amount:
            continue
        amt = float(amount)  # 元
        agg["day_count"][d] = agg["day_count"].get(d, 0) + 1
        agg["day_total"][d] = agg["day_total"].get(d, 0.0) + amt
        if amt >= 1e9:
            agg["day_over10"][d] = agg["day_over10"].get(d, 0) + 1
        # top60 堆（按成交额）
        h = agg["day_top60"].setdefault(d, [])
        item = (amt, code.split(".")[-1], name, pct)
        if len(h) < 60:
            heapq.heappush(h, item)
        elif amt > h[0][0]:
            heapq.heapreplace(h, item)
        # 涨跌停判定（规格规则，含创业板注册制分界）
        try:
            pctv = float(pct) if pct else None
        except ValueError:
            pctv = None
        if pctv is None or is_st == "1" or i < 250:
            continue
        limit = _limit_threshold(code, d)
        row = {"code": code.split(".")[-1], "name": name,
               "amount": round(amt / 1e8, 2), "change": pctv, "board": _board_of(code)}
        if pctv >= limit:
            agg["day_lu"][d] = agg["day_lu"].get(d, 0) + 1
            if amt >= 1e9:
                agg["day_lu_over"].setdefault(d, []).append(row)
        elif pctv <= -limit:
            agg["day_ld"][d] = agg["day_ld"].get(d, 0) + 1
            if amt >= 1e9:
                agg["day_ld_over"].setdefault(d, []).append(row)


def _new_agg():
    return {"done": [], "day_count": {}, "day_total": {}, "day_over10": {},
            "day_lu": {}, "day_ld": {}, "day_top60": {}, "day_lu_over": {}, "day_ld_over": {}}


def _write_stock_series(agg):
    """由聚合重写 4 条市场序列（rank/百分位随全历史重算）"""
    write_series_bulk("limit_up_down", "涨停家数", "家", agg["day_lu"])
    write_series_bulk("limit_down", "跌停家数", "家", agg["day_ld"])
    write_series_bulk("over_10e_count", "10亿以上家数", "家", agg["day_over10"])
    top10_pct = {}
    for d, h in agg["day_top60"].items():
        total = agg["day_total"].get(d, 0)
        if total <= 0:
            continue
        top10 = sorted(h, key=lambda x: -x[0])[:10]
        top10_pct[d] = round(sum(x[0] for x in top10) / total * 100, 2)
    write_series_bulk("top10_concentration", "前10成交占比", "%", top10_pct)


def stage_stocks():
    import baostock as bs
    target = _target()
    day = f"{target[:4]}-{target[4:6]}-{target[6:]}"
    ckpt = os.path.join(CACHE, "stocks_agg.pkl")

    agg = _new_agg()
    if os.path.exists(ckpt):
        with open(ckpt, "rb") as f:
            agg = pickle.load(f)
        log(f"断点续跑：已完成 {len(agg['done'])} 只")

    bs.login()
    codes = _a_share_codes(bs, day)
    log(f"沪深 A 股共 {len(codes)} 只（不含北交所）")
    todo = [c for c in codes if c not in set(agg["done"])]

    n = 0
    for code in todo:
        n += 1
        name = codes[code]
        rows = _fetch_daily(bs, code, name, STOCKS_START, day)
        if not rows:
            log(f"{code} {name} 3 次重试仍无数据，跳过")
        _aggregate_rows(agg, code, name, rows)
        agg["done"].append(code)
        if n % 300 == 0:
            with open(ckpt, "wb") as f:
                pickle.dump(agg, f)
            log(f"进度 {n}/{len(todo)}（累计 {len(agg['done'])}/{len(codes)}）")

    with open(ckpt, "wb") as f:
        pickle.dump(agg, f)
    bs.logout()

    _write_stock_series(agg)
    log(f"stocks 阶段完成：{len(agg['day_lu'])} 个交易日聚合")


def stage_stocks_ext():
    """历史扩展：逐股日线向过去延伸到 EXTEND_START（独立检查点，断点续跑）。
    完成后与主聚合 stocks_agg.pkl 加法合并并重写全部序列。"""
    import baostock as bs
    target = _target()
    day = f"{target[:4]}-{target[4:6]}-{target[6:]}"
    ckpt = os.path.join(CACHE, "stocks_ext.pkl")

    agg = _new_agg()
    if os.path.exists(ckpt):
        with open(ckpt, "rb") as f:
            agg = pickle.load(f)
        log(f"历史扩展断点续跑：已完成 {len(agg['done'])} 只")

    bs.login()
    codes = _a_share_codes(bs, day)
    log(f"沪深 A 股共 {len(codes)} 只（不含北交所；历史窗口 {EXTEND_START} ~ {EXTEND_END}）")
    todo = [c for c in codes if c not in set(agg["done"])]

    n = 0
    for code in todo:
        n += 1
        name = codes[code]
        rows = _fetch_daily(bs, code, name, EXTEND_START, EXTEND_END)
        if not rows:
            log(f"{code} {name} 历史窗口无数据/重试失败，跳过")
        _aggregate_rows(agg, code, name, rows)
        agg["done"].append(code)
        if n % 200 == 0:
            with open(ckpt, "wb") as f:
                pickle.dump(agg, f)
            log(f"历史扩展进度 {n}/{len(todo)}（累计 {len(agg['done'])}/{len(codes)}）")

    with open(ckpt, "wb") as f:
        pickle.dump(agg, f)
    bs.logout()
    log(f"历史扩展拉取完成：{len(agg['day_lu'])} 个交易日聚合，开始合并入主聚合")

    # ---- 与主聚合合并（两窗口无重叠，直接相加；堆合并取前60）----
    main_p = os.path.join(CACHE, "stocks_agg.pkl")
    with open(main_p, "rb") as f:
        main = pickle.load(f)
    for key in ("day_count", "day_over10", "day_lu", "day_ld"):
        for d, v in agg[key].items():
            main[key][d] = main[key].get(d, 0) + v
    for d, v in agg["day_total"].items():
        main["day_total"][d] = main["day_total"].get(d, 0.0) + v
    for d, h in agg["day_top60"].items():
        merged = list(main["day_top60"].get(d, [])) + list(h)
        main["day_top60"][d] = heapq.nlargest(60, merged)
    for key in ("day_lu_over", "day_ld_over"):
        for d, lst in agg[key].items():
            main[key].setdefault(d, []).extend(lst)
    main["done"] = sorted(set(main["done"]) | set(agg["done"]))
    with open(main_p, "wb") as f:
        pickle.dump(main, f)

    _write_stock_series(main)
    log(f"===== 历史扩展合并完成：主聚合现覆盖 {min(main['day_count'])} ~ {max(main['day_count'])} =====")


# ---------------------------------------------------------------- margin
def stage_margin():
    src = os.path.join(CACHE, "margin_ifind.json")
    with open(src, "r", encoding="utf-8") as f:
        vals = json.load(f)
    vals = {d: round(float(v), 2) for d, v in vals.items()}
    write_series_bulk("margin", "两融余额", "亿元", vals)


# ---------------------------------------------------------------- snapshot
def _tencent_batch(s, codes: list) -> list:
    """codes: ['sh600519', ...] → 每只 [name, price, change_pct, amount_wan, mktcap_yi]"""
    out = []
    for i in range(0, len(codes), 80):
        batch = codes[i:i + 80]
        r = s.get(f"https://qt.gtimg.cn/q={','.join(batch)}",
                  headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        r.encoding = "gbk"
        for line in r.text.strip().split(";"):
            line = line.strip()
            if "=" not in line:
                continue
            body = line.split("=", 1)[1].strip('"')
            f = body.split("~")
            if len(f) < 49:
                continue
            out.append({"code": f[2], "name": f[1], "price": float(f[3]) if f[3] else None,
                        "change": float(f[32]) if f[32] else None,
                        "mktcap_yi": float(f[45]) if f[45] else None})
    return out


def stage_snapshot():
    import requests
    import akshare as ak
    target = _target()

    with open(os.path.join(CACHE, "index_amounts.json"), encoding="utf-8") as f:
        idx = json.load(f)
    with open(os.path.join(CACHE, "stocks_agg.pkl"), "rb") as f:
        agg = pickle.load(f)

    # ---- 腾讯总市值 + 全市场成交额（微盘代理用）+ 自选股行情 ----
    s = requests.Session()
    s.trust_env = False
    all_codes = [c.replace(".", "") for c in agg["done"]]  # sh.600000 → sh600000
    tx_map = {}
    for i in range(0, len(all_codes), 80):
        batch = all_codes[i:i + 80]
        r = s.get(f"https://qt.gtimg.cn/q={','.join(batch)}",
                  headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        r.encoding = "gbk"
        for line in r.text.strip().split(";"):
            if "=" not in line:
                continue
            f = line.split("=", 1)[1].strip('"').split("~")
            if len(f) < 49 or not f[2]:
                continue
            try:
                tx_map[f[2]] = {
                    "name": f[1],
                    "mktcap_yi": float(f[45]) if f[45] else None,
                    "amount_yi": round(float(f[37]) / 1e4, 2) if f[37] else None,  # 万元→亿
                }
            except ValueError:
                continue
    log(f"腾讯总市值 {len(tx_map)} 只")

    # 自选股 quotes.json
    with open(os.path.join(DATA_DIR, "stocks.json"), encoding="utf-8") as f:
        watch = json.load(f).get("stocks", [])
    wl = []
    for w in watch:
        c = w["code"]
        pre = "sh" if c.startswith("6") else ("sz" if c.startswith(("0", "3")) else "bj")
        wl.append(pre + c)
    quotes = []
    for q in _tencent_batch(s, wl):
        quotes.append({"code": q["code"], "name": q["name"],
                       "price": q["price"], "change": q["change"]})
    atomic_write_json(os.path.join(DATA_DIR, "quotes.json"),
                      {"date": f"{target[:4]}-{target[4:6]}-{target[6:]}", "quotes": quotes})
    log(f"quotes.json：{len(quotes)} 只")

    # ---- 概览 ----
    total_amount = round(idx["sh000001"][target] + idx["sz399001"][target], 2)
    day_total = agg["day_total"].get(target, 0)
    stock_count = agg["day_count"].get(target, 0)
    over_cnt = agg["day_over10"].get(target, 0)
    lu, ld = agg["day_lu"].get(target, 0), agg["day_ld"].get(target, 0)

    ta_pts = {p["date"]: p for p in read_series_points("total_amount")}
    mg_pts = {p["date"]: p for p in read_series_points("margin")}
    mg_dates = sorted(mg_pts)
    mg_date = mg_dates[-1] if mg_dates else None  # 两融 T+1，取最新可得
    margin = mg_pts[mg_date]["value"] if mg_date else None

    def ta_rank(field):
        p = ta_pts.get(target)
        return p.get(field) if p else None

    overview = {
        "total_amount": total_amount,
        "total_amount_rank_year": ta_rank("rank_year"),
        "total_amount_rank_all": ta_rank("rank_all"),
        "total_amount_pctile_all": ta_rank("pctile"),
        "margin_balance": margin, "margin_rank_year": None, "margin_pctile_all": None,
        "margin_note": f"最新可得 {mg_date}（两融 T+1 披露）" if mg_date and mg_date != target else None,
        "limit_up": lu, "limit_down": ld,
        "over_10e_count": over_cnt,
        "over_10e_ratio": round(over_cnt / stock_count * 100, 1) if stock_count else 0,
        "stock_count": stock_count,
    }
    if margin is not None:
        p = mg_pts[mg_date]
        overview["margin_rank_year"] = p.get("rank_year")
        overview["margin_pctile_all"] = p.get("pctile")

    # ---- 指数 / 宽基 ----
    def idx_row(code: str, name: str, approx=False, wide=False):
        vals = idx.get(code, {})
        amt = vals.get(target)
        row = {"name": name, "code": code, "amount": amt,
               "rank_year": None, "rank_1y": None, "pctile_all": None, "approx": approx}
        if amt is not None:
            pts = {p["date"]: p for p in read_series_points(f"index_amount_{code}")}
            p = pts.get(target)
            if p:
                row["rank_year"], row["rank_1y"], row["pctile_all"] = (
                    p.get("rank_year"), p.get("rank_1y"), p.get("pctile"))
        if wide:
            del row["rank_year"]
        return row

    idx_rows = [
        idx_row("sh000001", "上证指数"), idx_row("sz399001", "深证成指"),
        idx_row("sz399006", "创业板指"),
        {"name": "科创50", "code": "sh000688", "amount": None,
         "rank_year": None, "rank_1y": None, "pctile_all": None},
        {"name": "北证50", "code": "bj899050", "amount": None,
         "rank_year": None, "rank_1y": None, "pctile_all": None},
    ]
    wide_rows = [
        idx_row("sh000016", "上证50", wide=True), idx_row("sh000300", "沪深300", wide=True),
        idx_row("sz399673", "创业板50", wide=True),
        {"name": "科创50", "code": "sh000688", "amount": None, "rank_1y": None, "pctile_all": None},
        idx_row("sh000905", "中证500", wide=True), idx_row("sh000906", "中证800", wide=True),
        idx_row("sh000852", "中证1000", wide=True),
        {"name": "中证2000", "code": "sh932000", "amount": None, "rank_1y": None, "pctile_all": None},
        idx_row("sh000985", "中证全指(沪深合计代理)", wide=True),
        idx_row("hstech_513180", "恒生科技(513180近似)", approx=True, wide=True),
    ]

    # ---- 微盘代理（全市场按总市值升序后 10% 等权，腾讯市值+当日成交额）----
    micro_amt = None
    full = [(v["mktcap_yi"], v["amount_yi"]) for v in tx_map.values()
            if v["mktcap_yi"] and v["amount_yi"]]
    if full:
        full.sort()
        k = max(int(len(full) * 0.1), 1)
        micro_amt = round(sum(a for _m, a in full[:k]) / k, 2)
        log(f"微盘代理：市值后10%（N={k}）等权日均成交 {micro_amt} 亿")
    wide_rows.append({"name": "微盘代理(自建)", "code": "micro_proxy", "amount": micro_amt,
                      "rank_1y": None, "pctile_all": None})

    # ---- 集中度 ----
    total_pct_base = day_total if day_total > 0 else 1
    top60 = sorted(agg["day_top60"].get(target, []), key=lambda x: -x[0])

    def conc_rows(k):
        out, cum = [], 0.0
        for amt, code, name, _pct in top60[:k]:
            pct = round(amt / total_pct_base * 100, 2)
            cum += pct
            out.append({"code": code, "name": name, "amount": round(amt / 1e8, 2),
                        "pct_of_total": pct})
        return out
    top10, top20, top50 = conc_rows(10), conc_rows(20), conc_rows(50)
    tc_pts = {p["date"]: p for p in read_series_points("top10_concentration")}
    t10 = round(sum(x["pct_of_total"] for x in top10), 2)
    concentration = {
        "top_n": [10, 20, 50], "top10": top10, "top20": top20, "top50": top50,
        "top20_cum_pct": round(sum(x["pct_of_total"] for x in top20), 2),
        "top50_cum_pct": round(sum(x["pct_of_total"] for x in top50), 2),
        "top10_total_pctile_hist": tc_pts.get(target, {}).get("pctile") if top10 else None,
    }

    # ---- 流动性（市值分档，腾讯总市值）----
    all_caps = [v["mktcap_yi"] for v in tx_map.values() if v["mktcap_yi"]]
    buckets = []
    if all_caps:
        n = len(all_caps)
        edges = [("<50亿", 0, 50), ("50-100亿", 50, 100), ("100-200亿", 100, 200),
                 ("200-500亿", 200, 500), ("500-1000亿", 500, 1000), (">1000亿", 1000, 1e12)]
        for label, lo, hi in edges:
            c = sum(1 for v in all_caps if lo <= v < hi)
            buckets.append({"label": label, "count": c, "pct": round(c / n * 100, 1)})
    o10_pts = {p["date"]: p for p in read_series_points("over_10e_count")}
    liquidity = {"over_10e_count": over_cnt,
                 "over_10e_ratio": overview["over_10e_ratio"],
                 "pctile_count": o10_pts.get(target, {}).get("pctile"),
                 "mktcap_buckets": buckets}

    # ---- 情绪 ----
    lu_pts = {p["date"]: p for p in read_series_points("limit_up_down")}
    ld_pts = {p["date"]: p for p in read_series_points("limit_down")}
    lu10 = sorted(agg["day_lu_over"].get(target, []), key=lambda x: -x["amount"])
    ld10 = sorted(agg["day_ld_over"].get(target, []), key=lambda x: -x["amount"])
    emotion = {
        "limit_up": lu, "limit_down": ld,
        "lu_pctile": lu_pts.get(target, {}).get("pctile"),
        "ld_pctile": ld_pts.get(target, {}).get("pctile"),
        "lu_ratio_of_total": round(lu / stock_count * 100, 2) if stock_count else 0,
        "ld_ratio_of_total": round(ld / stock_count * 100, 2) if stock_count else 0,
        "lu_ratio_of_over10e": round(len(lu10) / over_cnt * 100, 1) if over_cnt else 0,
        "ld_ratio_of_over10e": round(len(ld10) / over_cnt * 100, 1) if over_cnt else 0,
        "lu_over10e": lu10, "ld_over10e": ld10,
    }

    # ---- 行业（同花顺板块）----
    industry = {"top10_up": [], "top10_down": []}
    try:
        df = ak.stock_board_industry_summary_ths()
        rows_i = []
        for _, r in df.iterrows():
            try:
                change = float(r["涨跌幅"])
                amount = float(str(r["总成交额"]).replace(",", ""))
            except (TypeError, ValueError):
                continue
            rows_i.append({"name": str(r["板块"]), "change": change, "amount": amount})
        # 单位识别：深市+沪市 17000 亿级别，若板块中位数过大则为「元」
        med = sorted(x["amount"] for x in rows_i)[len(rows_i) // 2] if rows_i else 0
        if med > 5000:
            for x in rows_i:
                x["amount"] = round(x["amount"] / 1e8, 2)
        for x in rows_i:
            x["ratio"] = round(x["amount"] / total_amount * 100, 2)
        ups = sorted([x for x in rows_i if x["change"] > 0], key=lambda x: -x["change"])[:10]
        downs = sorted([x for x in rows_i if x["change"] < 0], key=lambda x: x["change"])[:10]
        industry = {"top10_up": ups, "top10_down": downs,
                    "note": "口径：同花顺行业板块当日数据"}
        log(f"行业（THS）：涨 {len(ups)} / 跌 {len(downs)}")
    except Exception as e:  # noqa: BLE001
        log(f"行业获取失败：{e}")

    # ---- sparklines ----
    def spark(key, n=20):
        return [{"date": p["date"], "value": p["value"]}
                for p in read_series_points(key)[-n:]]
    down_map = {p["date"]: p["value"] for p in read_series_points("limit_down")}
    spark_lud = [{"date": p["date"], "up": p["value"], "down": down_map.get(p["date"], 0)}
                 for p in read_series_points("limit_up_down")[-20:]]

    daily = {
        "trade_date": target,
        "overview": overview,
        "index_volume": idx_rows,
        "widebase": wide_rows,
        "industry": industry,
        "concentration": concentration,
        "liquidity": liquidity,
        "emotion": emotion,
        "sparklines": {"total_amount": spark("total_amount"), "margin": spark("margin"),
                       "limit_up_down": spark_lud, "over_10e_count": spark("over_10e_count")},
    }
    atomic_write_json(os.path.join(DATA_DIR, "daily", f"{target}.json"), daily)
    atomic_write_json(os.path.join(DATA_DIR, "latest.json"),
                      {"latest": target, "updated_at": now_iso()})
    log(f"===== 快照 {target} 构建完成：成交 {total_amount} 亿 / 涨停 {lu} / 跌停 {ld} / 10亿+ {over_cnt} 家 =====")


# ---------------------------------------------------------------- finalize
def stage_finalize():
    compute.build_index_agg()
    # 旧演示 daily 文件归档（保留真实快照；归档到 gitignore 的 _cache 而非删除，可恢复）
    target = _target()
    ddir = os.path.join(DATA_DIR, "daily")
    arch = os.path.join(CACHE, "old_daily")
    os.makedirs(arch, exist_ok=True)
    for fn in os.listdir(ddir):
        if fn.endswith(".json") and fn[:-5] != target:
            os.replace(os.path.join(ddir, fn), os.path.join(arch, fn))
            log(f"归档旧 daily 文件 {fn} → scripts/_cache/old_daily/")
    # trading_days.latest 同步
    meta_p = os.path.join(DATA_DIR, "meta", "trading_days.json")
    with open(meta_p, encoding="utf-8") as f:
        meta = json.load(f)
    meta["latest"] = target
    meta["updated_at"] = now_iso()
    atomic_write_json(meta_p, meta)
    err_p = os.path.join(DATA_DIR, "meta", "last_error.log")
    if os.path.exists(err_p):
        os.remove(err_p)
    log("finalize 完成")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True,
                    choices=["calendar", "index", "stocks", "stocks_ext", "margin", "snapshot", "finalize"])
    args = ap.parse_args()
    {"calendar": stage_calendar, "index": stage_index, "stocks": stage_stocks,
     "stocks_ext": stage_stocks_ext, "margin": stage_margin, "snapshot": stage_snapshot,
     "finalize": stage_finalize}[args.stage]()


if __name__ == "__main__":
    main()
