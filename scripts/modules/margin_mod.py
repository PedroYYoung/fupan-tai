# -*- coding: utf-8 -*-
"""两融余额：AKShare stock_margin_sse(start_date,end_date) + stock_margin_szse(date) 汇总

AKShare 函数签名（实测）：
- stock_margin_sse(start_date: str, end_date: str)，日期格式 YYYYMMDD
- stock_margin_szse(date: str)，日期格式 YYYYMMDD
"""
import akshare as ak
from .common import retry, log


def _to_yi(v) -> float:
    """源单位为元 → 亿元"""
    return round(float(str(v).replace(",", "")) / 1e8, 2)


def _fmt8(date: str) -> str:
    """统一转成 YYYYMMDD（支持 2026-10-10 或 20261010 输入）。"""
    return date.replace("-", "")


def get_margin(date: str):
    """两融余额 = 沪市汇总余额 + 深市汇总余额（亿元）；失败返回 None"""
    d8 = _fmt8(date)
    try:
        sse = retry(lambda: ak.stock_margin_sse(start_date=d8, end_date=d8), what=f"两融沪市{date}")
        szse = retry(lambda: ak.stock_margin_szse(date=d8), what=f"两融深市{date}")
        sse_sum = _to_yi(sse["融资融券余额"].sum()) if "融资融券余额" in sse.columns else _to_yi(sse.iloc[-1]["融资融券余额"])
        szse_col = "融资融券余额" if "融资融券余额" in szse.columns else "合计融资融券余额"
        szse_sum = _to_yi(szse[szse_col].sum())
        total = round(sse_sum + szse_sum, 2)
        log(f"{date} 两融余额 {total} 亿（沪 {sse_sum} + 深 {szse_sum}）")
        return total
    except Exception as e:  # noqa: BLE001
        log(f"{date} 两融获取失败：{e}")
        return None
