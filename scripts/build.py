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


def last_closed_trade_date(dates: list) -> str:
    """最近一个已收盘的交易日（今天 16:00 前视为未收盘）"""
    now = datetime.datetime.now()
    today = now.strftime("%Y%m%d")
    cutoff = now.replace(hour=16, minute=0, second=0, microsecond=0)
    past = [d for d in dates if d <= today]
    if not past:
        raise RuntimeError("交易日历为空")
    if past[-1] == today and now < cutoff and len(past) >= 2:
        return past[-2]
    return past[-1]


def build_one(date: str, dates: list, backfill_days: int = 0):
    """构建单日快照并维护序列；任何异常向上抛出"""
    log(f"===== 构建交易日 {date} =====")
    spot_df = spot_mod.get_spot()

    # ---- 指数/宽基成交额（含当日 + 回补窗口）----
    def fetch_index_rows(d: str):
        rows_idx, rows_wide = [], []
        for code in ["sh000001", "sz399001", "sz399006", "sh000688", "bj899050"]:
            amt = index_mod.get_index_amount(code, d)
            rows_idx.append({"name": index_mod.INDEX_CODES[code], "code": code,
                             "amount": amt, "rank_year": None, "rank_1y": None,
                             "pctile_all": None, "approx": code == "bj899050" and amt is not None})
        for code in ["sh000016", "sh000300", "sz399673", "sh000688", "sh000905",
                     "sh000906", "sh000852", "sh932000", "sh000985", "hstech_513180"]:
            amt = index_mod.get_index_amount(code, d)
            rows_wide.append({"name": index_mod.INDEX_CODES[code], "code": code,
                              "amount": amt, "rank_1y": None, "pctile_all": None,
                              "approx": code == "hstech_513180"})
        # 微盘代理：第 11 格
        micro_amt, micro_n = compute.microcap_proxy_amount(spot_df)
        rows_wide.append({"name": "微盘代理(自建)", "code": "micro_proxy",
                          "amount": micro_amt, "rank_1y": None, "pctile_all": None,
                          "approx": False})
        log(f"微盘代理：市值后10%（N={micro_n}）等权日均成交 {micro_amt} 亿")
        return rows_idx, rows_wide

    idx_rows, wide_rows = fetch_index_rows(date)

    # ---- 两融 ----
    margin = margin_mod.get_margin(date)

    # ---- 涨跌停 ----
    limit_up, limit_down, lu10, ld10 = zt_mod.get_limit_pools(date, spot_df)

    # ---- 概览 / 流动性 / 集中度 ----
    total_amount = round(float(spot_df["amount"].dropna().sum()) / 1e8, 2)
    over_cnt, over_ratio, stock_count = compute.over_10e(spot_df)
    conc = compute.concentration(spot_df)

    # ---- 行业板块（东财行业当日涨跌TOP10）----
    industry = industry_mod.get_industry_daily(total_amount)

    overview = {
        "total_amount": total_amount,
        "total_amount_rank_year": None, "total_amount_rank_all": None,
        "total_amount_pctile_all": None,
        "margin_balance": margin, "margin_rank_year": None, "margin_pctile_all": None,
        "limit_up": limit_up, "limit_down": limit_down,
        "over_10e_count": over_cnt, "over_10e_ratio": over_ratio,
        "stock_count": stock_count,
    }

    # ---- 序列维护（当日 + 可选回补窗口；重算后回填排名/百分位）----
    def series_points(key: str) -> list:
        import json
        p = os.path.join(DATA_DIR, "series", f"{key}.json")
        if not os.path.exists(p):
            return []
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f).get("points", [])

    def series_values(key: str) -> list:
        return [pt["value"] for pt in series_points(key)]

    compute.update_series("total_amount", "两市成交额", "亿元", date, total_amount)
    pts = series_points("total_amount")
    vals = [p["value"] for p in pts]
    overview["total_amount_rank_all"] = compute.rank_of(vals, total_amount)
    overview["total_amount_pctile_all"] = compute.pctile(vals, total_amount)
    year_vals = [p["value"] for p in pts if p["date"].startswith(date[:4])]
    overview["total_amount_rank_year"] = compute.rank_of(year_vals, total_amount) if year_vals else None

    if margin is not None:
        compute.update_series("margin", "两融余额", "亿元", date, margin)
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
        if r["amount"] is not None:
            key = f"index_amount_{r['code']}"
            compute.update_series(key, r["name"], "亿元", date, r["amount"])
            svals = series_values(key)
            if r.get("rank_1y") is None:
                r["rank_1y"] = compute.rank_of(svals, r["amount"])
            r["pctile_all"] = compute.pctile(svals, r["amount"])

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

    daily = {
        "trade_date": date,
        "overview": overview,
        "index_volume": idx_rows,
        "widebase": wide_rows,
        "industry": industry,
        "concentration": conc or {"top_n": [10, 20, 50], "top10": [], "top20": [],
                                  "top50": [], "top20_cum_pct": 0, "top50_cum_pct": 0,
                                  "top10_total_pctile_hist": None},
        "liquidity": {
            "over_10e_count": over_cnt, "over_10e_ratio": over_ratio,
            "pctile_count": compute.pctile(series_values("over_10e_count"), over_cnt),
            "mktcap_buckets": compute.mktcap_buckets(spot_df),
        },
        "emotion": {
            "limit_up": limit_up, "limit_down": limit_down,
            "lu_pctile": compute.pctile(series_values("limit_up_down"), limit_up),
            "ld_pctile": compute.pctile(series_values("limit_down"), limit_down),
            "lu_ratio_of_total": round(limit_up / stock_count * 100, 2) if stock_count else 0,
            "ld_ratio_of_total": round(limit_down / stock_count * 100, 2) if stock_count else 0,
            "lu_ratio_of_over10e": round(len(lu10) / over_cnt * 100, 1) if over_cnt else 0,
            "ld_ratio_of_over10e": round(len(ld10) / over_cnt * 100, 1) if over_cnt else 0,
            "lu_over10e": lu10, "ld_over10e": ld10,
        },
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
            notify_failure("复盘台数据更新失败", f"日期 {d} 构建失败: {e}")
            log(f"日期 {d} 构建失败（已保留旧数据）：{e}")
            if failed >= 2:
                log("连续失败 2 次，终止本次构建")
                break
    if failed == 0:
        log("全部日期构建成功")
    else:
        log(f"{failed} 个日期失败，详情见 data/meta/last_error.log")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        # 任一日失败：保留旧数据、记录错误、exit 0（网站仍显示上一交易日数据）
        record_error(f"FATAL: {e}\n{traceback.format_exc()}")
        notify_failure("复盘台数据更新失败（FATAL）", str(e))
        log(f"构建失败（已保留旧数据）：{e}")
        sys.exit(0)
