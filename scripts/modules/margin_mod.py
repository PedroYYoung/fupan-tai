# -*- coding: utf-8 -*-
"""两融余额：AKShare stock_margin_sse(date) + stock_margin_szse(date) 汇总"""
import akshare as ak
from .common import retry, log


def _to_yi(v) -> float:
    """源单位为元 → 亿元"""
    return round(float(str(v).replace(",", "")) / 1e8, 2)


def get_margin(date: str):
    """两融余额 = 沪市汇总余额 + 深市汇总余额（亿元）；失败返回 None"""
    try:
        sse = retry(lambda: ak.stock_margin_sse(date=date), what=f"两融沪市{date}")
        szse = retry(lambda: ak.stock_margin_szse(date=date), what=f"两融深市{date}")
        sse_sum = _to_yi(sse["融资融券余额"].sum()) if "融资融券余额" in sse.columns else _to_yi(sse.iloc[-1]["融资融券余额"])
        szse_col = "融资融券余额" if "融资融券余额" in szse.columns else "合计融资融券余额"
        szse_sum = _to_yi(szse[szse_col].sum())
        total = round(sse_sum + szse_sum, 2)
        log(f"{date} 两融余额 {total} 亿（沪 {sse_sum} + 深 {szse_sum}）")
        return total
    except Exception as e:  # noqa: BLE001
        log(f"{date} 两融获取失败：{e}")
        return None
