#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复盘台数据构建脚本（本地/CI 双模式）

用法：
  python scripts/build.py --date 20260925    # 单日快照模式（指定交易日）
  python scripts/build.py --incremental      # 增量模式（自动取最近一个已收盘交易日）
  python scripts/build.py --date 20260925 --backfill-days 20   # 本地回补（含序列窗口）

硬性规则：
- 历史回补只在本地跑；CI 只做每日增量
- 单接口最多重试 2 次、间隔 5s；每 50 次请求 sleep 2s
- 全部写入 *.tmp，校验通过后原子替换
- 任一日失败 → 保留旧数据、写 data/meta/last_error.log、exit 0
"""
import argparse
import datetime
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.common import (DATA_DIR, REPO_ROOT, atomic_write_json, log,  # noqa: E402
                            now_iso, record_error, retry)
from modules import calendar_mod, compute, index_mod, industry_mod, margin_mod, notify, spot_mod, zt_mod  # noqa: E402


# 北京时间（UTC+8）。GitHub Actions runner 的本地时间是 UTC，
# 若用 naive now() 判定 16:00 收盘阈值，UTC 下全天都会被视为「今日未收盘」，
# 流水线将永远指向前一交易日，并连带使「行情日期须等于目标交易日」的腾讯通道失效。
_CST = datetime.timezone(datetime.timedelta(hours=8))


def last_closed_trade_date(dates: list) -> str:
    """最近一个已收盘的交易日（北京时间 16:00 前视为未收盘）"""
    now = datetime.datetime.now(_CST)
    today = now.strftime("%Y%m%d")
    cutoff = now.replace(hour=16, minute=0, second=0, microsecond=0)
    past = [d for d in dates if d <= today]
    if not past:
        raise RuntimeError("交易日历为空")
    if past[-1] == today and now < cutoff and len(past) >= 2:
        return past[-2]
    return past[-1]


def _previous_trade_day(date: str, dates: list) -> str | None:
    """返回 date 在交易日历中的上一个交易日。"""
    if date not in dates:
        return None
    i = dates.index(date)
    return dates[i - 1] if i > 0 else None


def _load_daily(date: str):
    """读取 daily/{date}.json 全量快照；不存在或损坏返回 None"""
    import json
    p = os.path.join(DATA_DIR, "daily", f"{date}.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def _load_industry_from_daily(date: str):
    """从指定日期的 daily 文件中读取 industry 字段。"""
    import json
    p = os.path.join(DATA_DIR, "daily", f"{date}.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d.get("industry")
    except Exception:  # noqa: BLE001
        return None


def build_one(date: str, dates: list, backfill_days: int = 0):
    """构建单日快照并维护序列；任何异常向上抛出"""
    log(f"===== 构建交易日 {date} =====")
    spot_df = spot_mod.get_spot(date)

    # ---- 序列读取工具（指数降级需要「最近交易日真实值」，须先定义）----
    def series_points(key: str) -> list:
        import json
        p = os.path.join(DATA_DIR, "series", f"{key}.json")
        if not os.path.exists(p):
            return []
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f).get("points", [])

    def series_values(key: str) -> list:
        return [pt["value"] for pt in series_points(key)]

    def last_known_point(code: str):
        """序列中最近一个早于 date 的已知真实值 → (value, date)；无则 (None, None)"""
        for pt in reversed(series_points(f"index_amount_{code}")):
            if pt["date"] < date and pt.get("value") is not None:
                return pt["value"], pt["date"]
        return None, None

    # ---- 指数/宽基成交额（含当日 + 降级：最近交易日 / ETF 代理）----
    def fetch_index_rows(d: str):
        rows_idx, rows_wide = [], []

        def make_row(code: str, base_approx: bool):
            amt, amt_date, note = index_mod.get_index_amount_resilient(
                code, d, last_known_point(code))
            chg = index_mod.get_index_change_pct(code, d)
            close = index_mod.get_index_close(code, d)
            return {"name": index_mod.INDEX_CODES[code], "code": code,
                    "amount": amt, "amount_date": amt_date, "note": note,
                    "change_pct": chg, "close": close,
                    "amount_change": None, "close_change": None,
                    "rank_year": None, "rank_1y": None, "pctile_all": None,
                    "approx": (base_approx and amt is not None) or note != ""}

        for code in ["sh000001", "sz399001", "sz399006", "sh000688", "bj899050"]:
            rows_idx.append(make_row(code, code == "bj899050"))
        for code in ["sh000016", "sh000300", "sz399673", "sh000688", "sh000905",
                     "sh000906", "sh000852", "sh932000", "sh000985", "hstech_513180"]:
            rows_wide.append(make_row(code, code == "hstech_513180"))
        # 微盘代理：第 11 格（前端宽基矩阵已不展示，但保留底层序列与数据）
        micro_amt, micro_n = compute.microcap_proxy_amount(spot_df)
        rows_wide.append({"name": "微盘代理(自建)", "code": "micro_proxy",
                          "amount": micro_amt, "amount_date": date, "note": "",
                          "change_pct": None, "amount_change": None,
                          "rank_1y": None, "pctile_all": None, "approx": False})
        log(f"微盘代理：市值后10%（N={micro_n}）等权日均成交 {micro_amt} 亿")
        return rows_idx, rows_wide

    idx_rows, wide_rows = fetch_index_rows(date)

    # ---- 加载上一交易日快照（用于「较昨日变化」与流动性数量变化）----
    prev_daily = None
    prev_date = _previous_trade_day(date, dates)
    if prev_date:
        prev_daily = _load_daily(prev_date)

    def _delta(cur, prev_v):
        """当前值与上一交易日值的差；任一侧缺失返回 None（不按 0 计）"""
        if cur is None or prev_v is None:
            return None
        return round(cur - prev_v, 2)

    if prev_daily:
        prev_idx = {}
        for r in (prev_daily.get("index_volume") or []) + (prev_daily.get("widebase") or []):
            prev_idx[r["code"]] = r
        for r in idx_rows + wide_rows:
            pr = prev_idx.get(r["code"]) or {}
            r["amount_change"] = _delta(r.get("amount"), pr.get("amount"))
            r["close_change"] = _delta(r.get("close"), pr.get("close"))

    # ---- 两融（T+1 发布，返回 (余额亿元, 实际统计日期)）----
    margin, margin_date = margin_mod.get_margin(date)

    # ---- 涨跌停（返回完整列表，按成交额门槛切分）----
    limit_up, limit_down, lu_rows, ld_rows = zt_mod.get_limit_pools(date, spot_df)
    lu_over10e = sorted((r for r in lu_rows if r["amount"] >= 10), key=lambda x: -x["amount"])[:30]
    ld_over10e = sorted((r for r in ld_rows if r["amount"] >= 10), key=lambda x: -x["amount"])[:30]
    lu_over5e_count = sum(1 for r in lu_rows if r["amount"] >= 5)
    ld_over5e_count = sum(1 for r in ld_rows if r["amount"] >= 5)

    # ---- 高活跃个股（当日成交额≥5亿 且 涨幅≥5%，供「上板与上涨」列表 + 导出）----
    active_stocks = []
    if {"amount", "change_pct", "close"}.issubset(spot_df.columns):
        lu_codes = {r["code"] for r in lu_rows}
        adf = spot_df.dropna(subset=["amount", "change_pct", "close"])
        adf = adf[(adf["amount"] >= 5e8) & (adf["change_pct"] >= 5)]
        adf = adf.sort_values("change_pct", ascending=False)
        for _, r in adf.iterrows():
            code = str(r["code"])
            active_stocks.append({
                "code": code, "name": str(r["name"]),
                "close": round(float(r["close"]), 2),
                "change_pct": round(float(r["change_pct"]), 2),
                "amount": round(float(r["amount"]) / 1e8, 2),
                "is_limit_up": code in lu_codes,
            })
    log(f"高活跃个股（≥5亿且涨幅≥5%）：{len(active_stocks)} 只")

    # ---- 概览 / 流动性 / 集中度 ----
    total_amount = round(float(spot_df["amount"].dropna().sum()) / 1e8, 2)
    over_cnt, over_ratio, stock_count = compute.over_10e(spot_df)
    conc = compute.concentration(spot_df)
    # 个股集中度 Top10/Top20/Top50 累计占比较上一交易日变化（百分点差）
    if conc is not None:
        prev_conc = (prev_daily or {}).get("concentration") or {}
        conc["top10_change"] = _delta(conc.get("top10_total"), prev_conc.get("top10_total"))
        conc["top20_change"] = _delta(conc.get("top20_cum_pct"), prev_conc.get("top20_cum_pct"))
        conc["top50_change"] = _delta(conc.get("top50_cum_pct"), prev_conc.get("top50_cum_pct"))

    # ---- 行业板块（东财 → 同花顺，当日涨跌TOP10）----
    industry = industry_mod.get_industry_daily(total_amount)
    if industry is None:
        # 两个数据源均失败：继承上一交易日有效数据，并标明真实数据日期（不伪装当日）
        prev = _previous_trade_day(date, dates)
        if prev:
            inherited = _load_industry_from_daily(prev)
            if inherited:
                inherited = dict(inherited)
                inherited["note"] = f"口径：继承自上一交易日 {prev}（当日数据源失败）"
                inherited["as_of"] = prev
                industry = inherited
                log(f"行业板块继承自上一交易日 {prev}")
        if industry is None:
            log(f"行业板块 {date} 获取失败且无前值可继承，置为空")

    overview = {
        "total_amount": total_amount,
        "total_amount_rank_year": None, "total_amount_rank_all": None,
        "total_amount_pctile_all": None,
        "margin_balance": margin, "margin_date": margin_date,
        "margin_rank_year": None, "margin_pctile_all": None,
        "limit_up": limit_up, "limit_down": limit_down,
        "over_10e_count": over_cnt, "over_10e_ratio": over_ratio,
        "stock_count": stock_count,
    }

    # ---- 序列维护（当日 + 可选回补窗口；重算后回填排名/百分位）----
    # 注：series_points / series_values 已在上方定义（指数降级需要提前读取序列）
    compute.update_series("total_amount", "两市成交额", "亿元", date, total_amount)
    pts = series_points("total_amount")
    vals = [p["value"] for p in pts]
    overview["total_amount_rank_all"] = compute.rank_of(vals, total_amount)
    overview["total_amount_pctile_all"] = compute.pctile(vals, total_amount)
    year_vals = [p["value"] for p in pts if p["date"].startswith(date[:4])]
    overview["total_amount_rank_year"] = compute.rank_of(year_vals, total_amount) if year_vals else None

    if margin is not None and margin_date is not None:
        # 按「实际统计日期」写入序列（两融 T+1，实际日期可能早于当日）
        compute.update_series("margin", "两融余额", "亿元", margin_date, margin)
        mvals = series_values("margin")
        overview["margin_rank_year"] = compute.rank_of(mvals, margin)
        overview["margin_pctile_all"] = compute.pctile(mvals, margin)

    compute.update_series("limit_up_down", "涨停家数", "家", date, limit_up)
    compute.update_series("limit_down", "跌停家数", "家", date, limit_down)
    compute.update_series("over_10e_count", "10亿以上家数", "家", date, over_cnt)
    if conc:
        # 头部抱团度序列（前10成交占比 %）
        compute.update_series("top10_concentration", "前10成交占比", "%",
                              date, conc["top10_total"])
    for r in idx_rows + wide_rows:
        if r["amount"] is None:
            continue
        # ETF 代理值与指数自身历史量级不可比，不写序列、不做历史排名/百分位
        if r.get("note") == "etf_proxy":
            continue
        key = f"index_amount_{r['code']}"
        # 仅当日真实抓取成功才写入序列；降级值（最近交易日）不写，避免污染历史口径
        if r.get("amount_date") == date and not r.get("note"):
            compute.update_series(key, r["name"], "亿元", date, r["amount"])
        svals = series_values(key)
        if r.get("rank_1y") is None:
            # 近一年排名 = 最近 244 个交易日窗口内的降序排位（与 series 内 rank_1y、
            # 前端 oneYearSampleN() 的 244 窗口口径一致；全历史排名另用 rank_all）
            r["rank_1y"] = compute.rank_of(svals[-244:], r["amount"])
        r["pctile_all"] = compute.pctile(svals, r["amount"])

    # ---- 指数观察（YTD + 本周/本月/年内均额 + 较昨日变化）----
    index_observation = []
    for r in idx_rows + wide_rows:
        index_observation.append({
            "code": r["code"], "name": r["name"],
            "ytd_pct": index_mod.get_index_ytd_pct(r["code"], date, dates),
            "avg_week_amount": compute.avg_index_amount(r["code"], date, dates, "week"),
            "avg_month_amount": compute.avg_index_amount(r["code"], date, dates, "month"),
            "avg_year_amount": compute.avg_index_amount(r["code"], date, dates, "year"),
        })
    prev_obs = {}
    if prev_daily:
        for o in prev_daily.get("index_observation") or []:
            prev_obs[o["code"]] = o
    for o in index_observation:
        po = prev_obs.get(o["code"])
        o["ytd_pct_change"] = _delta(o["ytd_pct"], po.get("ytd_pct")) if po else None
        o["avg_week_change"] = _delta(o["avg_week_amount"], po.get("avg_week_amount")) if po else None
        o["avg_month_change"] = _delta(o["avg_month_amount"], po.get("avg_month_amount")) if po else None
        o["avg_year_change"] = _delta(o["avg_year_amount"], po.get("avg_year_amount")) if po else None

    # ---- 行业周涨跌排名 ----
    industry_week_rank = industry_mod.get_industry_week_rank(date, dates)

    # ---- sparklines（近20日，供 M0 迷你折线）----
    def spark(key: str, n=20):
        import json
        p = os.path.join(DATA_DIR, "series", f"{key}.json")
        if not os.path.exists(p):
            return []
        with open(p, "r", encoding="utf-8") as f:
            pts = json.load(f).get("points", [])
        return [{"date": pt["date"], "value": pt["value"]} for pt in pts[-n:]]

    lud = spark("limit_up_down")
    # limit_up_down 序列只有涨停值；补充跌停序列（单独 key）
    compute.update_series("limit_down", "跌停家数", "家", date, limit_down)
    lud_down = spark("limit_down")
    down_map = {p["date"]: p["value"] for p in lud_down}
    spark_lud = [{"date": p["date"], "up": p["value"], "down": down_map.get(p["date"], 0)} for p in lud]

    # ---- 流动性结构：分档表「较昨日股票数量变化」+「百分比变化」----
    # 同一分档口径（成交额门槛/市值分档/区间边界）取上一交易日快照中的 count / pct，
    # 缺上一交易日 → *_change=None（前端显示「—」），绝不按 0 计。
    def _attach_changes(buckets, prev_buckets):
        pmap = {b["label"]: b for b in (prev_buckets or [])}
        for b in buckets:
            p = pmap.get(b["label"])
            b["count_change"] = (b["count"] - p["count"]) if p and p.get("count") is not None else None
            b["pct_change"] = _delta(b.get("pct"), p.get("pct")) if p else None
        return buckets

    prev_liq = (prev_daily or {}).get("liquidity") or {}
    amount_buckets = _attach_changes(
        compute.amount_buckets(spot_df), prev_liq.get("amount_buckets"))
    o10e_mc_buckets = _attach_changes(
        compute.over_10e_marketcap_buckets(spot_df), prev_liq.get("over_10e_marketcap_buckets"))
    o10e_mc_value_buckets = _attach_changes(
        compute.over_10e_marketcap_value_buckets(spot_df), prev_liq.get("over_10e_marketcap_value_buckets"))
    mktcap_buckets = _attach_changes(
        compute.mktcap_buckets(spot_df), prev_liq.get("mktcap_buckets"))

    daily = {
        "trade_date": date,
        "overview": overview,
        "index_volume": idx_rows,
        "widebase": wide_rows,
        "index_observation": index_observation,
        "industry": industry,
        "industry_week_rank": industry_week_rank,
        "concentration": conc or {"top_n": [10, 20, 50], "top10": [], "top20": [],
                                  "top50": [], "top20_cum_pct": 0, "top50_cum_pct": 0,
                                  "top10_total_pctile_hist": None},
        "liquidity": {
            "over_10e_count": over_cnt, "over_10e_ratio": over_ratio,
            "pctile_count": compute.pctile(series_values("over_10e_count"), over_cnt),
            "mktcap_buckets": mktcap_buckets,
            "amount_buckets": amount_buckets,
            "over_10e_marketcap_buckets": o10e_mc_buckets,
            "over_10e_marketcap_value_buckets": o10e_mc_value_buckets,
        },
        "emotion": {
            "limit_up": limit_up, "limit_down": limit_down,
            "lu_pctile": compute.pctile(series_values("limit_up_down"), limit_up),
            "ld_pctile": compute.pctile(series_values("limit_down"), limit_down),
            "lu_ratio_of_total": round(limit_up / stock_count * 100, 2) if stock_count else 0,
            "ld_ratio_of_total": round(limit_down / stock_count * 100, 2) if stock_count else 0,
            "lu_ratio_of_over10e": round(len(lu_over10e) / over_cnt * 100, 1) if over_cnt else 0,
            "ld_ratio_of_over10e": round(len(ld_over10e) / over_cnt * 100, 1) if over_cnt else 0,
            "lu_over5e_count": lu_over5e_count, "ld_over5e_count": ld_over5e_count,
            "lu_over10e": lu_over10e, "ld_over10e": ld_over10e,
        },
        "active_stocks": active_stocks,
        "sparklines": {
            "total_amount": spark("total_amount"),
            "margin": spark("margin"),
            "limit_up_down": spark_lud,
            "over_10e_count": spark("over_10e_count"),
        },
    }
    daily["concentration"]["top10_total_pctile_hist"] = compute.pctile(
        [sum(p["pct_of_total"] for p in c["top10"]) for c in []] or
        _top10_hist_pctile_vals(), conc["top10_total"]) if conc else None

    # 市值分档序列（堆叠面积图用，滚动保留 400 点）
    compute.append_bucket_series(date, daily["liquidity"]["mktcap_buckets"])
    # 指数月/年均值预聚合表（四档切换单请求）
    compute.build_index_agg()

    atomic_write_json(os.path.join(DATA_DIR, "daily", f"{date}.json"), daily)

    # ---- 元数据 ----
    atomic_write_json(os.path.join(DATA_DIR, "latest.json"),
                      {"latest": date, "updated_at": now_iso()})
    atomic_write_json(os.path.join(DATA_DIR, "meta", "trading_days.json"),
                      {"list": dates, "latest": date, "updated_at": now_iso(),
                       "source_versions": _source_versions()})
    log(f"===== {date} 构建完成 =====")


def _top10_hist_pctile_vals():
    """历史 top10 占比序列（简化：若 daily 目录有历史文件则读取，否则空样本 → pctile=None）"""
    import json
    out = []
    ddir = os.path.join(DATA_DIR, "daily")
    if os.path.isdir(ddir):
        for fn in sorted(os.listdir(ddir)):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(ddir, fn), "r", encoding="utf-8") as f:
                    d = json.load(f)
                s = sum(x["pct_of_total"] for x in d.get("concentration", {}).get("top10", []))
                if s:
                    out.append(s)
            except Exception:  # noqa: BLE001
                continue
    return out


def _source_versions() -> dict:
    versions = {}
    try:
        import akshare
        versions["akshare"] = akshare.__version__
    except Exception:  # noqa: BLE001
        versions["akshare"] = "unknown"
    try:
        import baostock
        versions["baostock"] = getattr(baostock, "__version__", "ok")
    except Exception:  # noqa: BLE001
        versions["baostock"] = "not-installed"
    try:
        import tushare
        versions["tushare"] = tushare.__version__
    except Exception:  # noqa: BLE001
        versions["tushare"] = "not-installed"
    return versions


def main():
    ap = argparse.ArgumentParser(description="复盘台数据构建")
    ap.add_argument("--date", help="指定交易日 YYYYMMDD（单日快照模式）")
    ap.add_argument("--incremental", action="store_true", help="增量模式：自动取最近已收盘交易日")
    ap.add_argument("--backfill-days", type=int, default=0, help="本地回补最近 N 个交易日（勿在 CI 使用）")
    ap.add_argument("--industry-backfill", metavar="CSV",
                    help="申万行业历史回填：提供对齐表 CSV（列：east_name,sw_code,sw_name），仅本地使用")
    args = ap.parse_args()

    dates = calendar_mod.get_trade_dates()

    if args.industry_backfill:
        from modules import industry_mod
        target0 = last_closed_trade_date(dates)
        i = dates.index(target0)
        industry_mod.backfill_industry(args.industry_backfill,
                                       dates[max(0, i - 249)], target0)
        return

    if args.date:
        target = args.date
        if target not in dates:
            raise RuntimeError(f"{target} 不是交易日")
    elif args.incremental or True:
        target = last_closed_trade_date(dates)

    days = [target]
    if args.backfill_days > 0:
        # 历史回补只在本地跑：序列层回补（成交额=沪+深指数代理、两融、涨跌停、指数成交额）
        # 当日全市场快照仅实时可得，over_10e/市值分档/集中度无法历史回补，自启用日起累积
        from modules import backfill
        i = dates.index(target)
        window = dates[max(0, i - args.backfill_days + 1): i + 1]
        backfill.backfill_series(window, dates)
        return

    failed = 0
    for d in days:
        try:
            build_one(d, dates, args.backfill_days)
        except Exception as e:  # noqa: BLE001
            failed += 1
            record_error(f"日期 {d} 构建失败: {e}")
            notify.notify_failure("复盘台数据更新失败", f"日期 {d} 构建失败: {e}")
            log(f"日期 {d} 构建失败（已保留旧数据）：{e}")
            if failed >= 2:
                log("连续失败 2 次，终止本次构建")
                break
    if failed == 0:
        log("全部日期构建成功")
    else:
        log(f"{failed} 个日期失败，详情见 data/meta/last_error.log")


def run() -> int:
    """进程入口（__main__ 与测试共用）。

    FATAL 也遵守同一套容错约定：保留旧数据、记录 last_error.log、
    推送失败通知（notify.notify_failure）、返回 0（网站仍显示上一交易日数据）。"""
    try:
        main()
    except Exception as e:  # noqa: BLE001
        record_error(f"FATAL: {e}\n{traceback.format_exc()}")
        notify.notify_failure("复盘台数据更新失败（FATAL）", str(e))
        log(f"构建失败（已保留旧数据）：{e}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
