# -*- coding: utf-8 -*-
"""交易日列表：AKShare tool_trade_date_hist_sina()"""
import akshare as ak
from .common import retry, log


def get_trade_dates() -> list:
    """返回 YYYYMMDD 字符串升序列表（1990 至今）"""
    df = retry(lambda: ak.tool_trade_date_hist_sina(), what="交易日历")
    dates = [str(d).replace("-", "") for d in df["trade_date"].tolist()]
    dates = sorted(set(d for d in dates if len(d) == 8))
    log(f"交易日历共 {len(dates)} 天，范围 {dates[0]} ~ {dates[-1]}")
    return dates
