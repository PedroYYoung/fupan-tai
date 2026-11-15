# -*- coding: utf-8 -*-
"""交易日列表：AKShare 新浪交易日历。"""
import akshare as ak
from .common import retry, log


def get_trade_dates() -> list:
    """返回 YYYYMMDD 字符串升序列表（1990 至今）。

    akshare 1.20.45 起 tool_trade_date_hist_sina 更名为 calendar_trade_date_hist_sina，
    此处兼容新旧两个接口名，避免依赖版本差异导致交易日历获取失败。
    """
    fn = getattr(ak, "tool_trade_date_hist_sina", None) \
        or getattr(ak, "calendar_trade_date_hist_sina", None)
    if fn is None:
        raise RuntimeError("akshare 未提供交易日历接口")
    df = retry(lambda: fn(), what="交易日历")
    dates = [str(d).replace("-", "") for d in df["trade_date"].tolist()]
    dates = sorted(set(d for d in dates if len(d) == 8))
    log(f"交易日历共 {len(dates)} 天，范围 {dates[0]} ~ {dates[-1]}")
    return dates
