# -*- coding: utf-8 -*-
"""序列层历史回补（只在本地跑，勿在 CI 使用）

可回补：
- total_amount：上证指数 + 深证成指 日成交额之和（历史两市成交额标准代理口径）
- margin：stock_margin_sse/szse 按日回补（接口允许历史日期）
- limit_up_down / limit_down：涨跌停池按日回补（东财池数据 2022 年起较全）

不可回补（依赖当日全市场快照，东财仅实时可得，自建每日累积）：
- over_10e_count、mktcap_buckets、top10_concentration、index_*（指数本身可回补）
"""
import akshare as ak
from .common import log, retry
from . import compute, margin_mod, zt_mod

_PROXY_CODES = {"sh": "000001", "sz": "399001"}


def _index_amount_series(market: str, start: str, end: str) -> dict:
    """指数日线 → {date: 成交额亿}"""
    df = retry(lambda: ak.index_zh_a_hist(symbol=_PROXY_CODES[market], period="daily",
                                          start_date=start, end_date=end),
               what=f"指数回补{market}", times=2)
    out = {}
    for _, r in df.iterrows():
        d = str(r["日期"]).replace("-", "")
        out[d] = round(float(r["成交额"]) / 1e8, 2)
    return out


def backfill_series(window: list, dates: list):
    """window: 升序 YYYYMMDD 列表（不含最新日也可）"""
    start, end = window[0], window[-1]
    log(f"===== 序列回补 {start} ~ {end}（共 {len(window)} 天）=====")

    # 1) 两市成交额（沪+深指数代理）
    sh = _index_amount_series("sh", start, end)
    sz = _index_amount_series("sz", start, end)
    done = 0
    for d in window:
        if d in sh and d in sz:
            v = round(sh[d] + sz[d], 2)
            compute.update_series("total_amount", "两市成交额", "亿元", d, v)
            done += 1
    log(f"两市成交额回补 {done} 天（代理口径：上证+深成指成交额）")

    # 2) 两融 / 3) 涨跌停（逐日，内置限速）
    for i, d in enumerate(window):
        log(f"-- 逐日回补 {d}（{i+1}/{len(window)}）")
        m = margin_mod.get_margin(d)
        if m is not None:
            compute.update_series("margin", "两融余额", "亿元", d, m)
        try:
            lu, ld, _, _ = zt_mod.get_limit_pools(d)
            compute.update_series("limit_up_down", "涨停家数", "家", d, lu)
            compute.update_series("limit_down", "跌停家数", "家", d, ld)
        except Exception as e:  # noqa: BLE001
            log(f"{d} 涨跌停回补失败：{e}")

    # 4) 指数/宽基成交额序列（可回补）
    from . import index_mod
    for code in index_mod.INDEX_CODES:
        ok = 0
        try:
            if code == "hstech_513180":
                df = retry(lambda: ak.fund_etf_hist_em(symbol="513180", period="daily",
                            start_date=start, end_date=end, adjust=""), what="ETF回补")
                amounts = {str(r["日期"]).replace("-", ""): round(float(r["成交额"]) / 1e8, 2)
                           for _, r in df.iterrows()}
            else:
                pure = code[2:]
                df = retry(lambda: ak.index_zh_a_hist(symbol=pure, period="daily",
                            start_date=start, end_date=end), what=f"指数回补{code}")
                col = "成交额" if "成交额" in df.columns else "amount"
                amounts = {str(r["日期"]).replace("-", ""): round(float(r[col]) / 1e8, 2)
                           for _, r in df.iterrows()}
            for d in window:
                if d in amounts:
                    compute.update_series(f"index_amount_{code}", index_mod.INDEX_CODES[code],
                                          "亿元", d, amounts[d])
                    ok += 1
        except Exception as e:  # noqa: BLE001
            log(f"{code} 回补失败：{e}")
        log(f"{code} 回补 {ok} 天")

    log("===== 序列回补完成（over_10e/市值分档/集中度无法历史回补，自今日起累积）=====")
