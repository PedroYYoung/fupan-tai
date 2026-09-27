# -*- coding: utf-8 -*-
"""指数日线成交额：AKShare index_zh_a_hist（主）/ baostock（备）。
恒生科技以 ETF 513180 成交额近似（UI 标注「近似值」）。
"""
import akshare as ak
from .common import retry, log

# 行固定：5 指数 + 11 宽基（code: 指数代码）
INDEX_CODES = {
    "sh000001": "上证指数", "sz399001": "深证成指", "sz399006": "创业板指",
    "sh000688": "科创50", "bj899050": "北证50",
    "sh000016": "上证50", "sh000300": "沪深300", "sz399673": "创业板50",
    "sh000905": "中证500", "sh000906": "中证800", "sh000852": "中证1000",
    "sh932000": "中证2000", "sh000985": "中证全指", "hstech_513180": "恒生科技(513180近似)",
}


def get_index_amount(code: str, date: str):
    """返回当日成交额（亿元）；源无成交额或失败返回 None"""
    try:
        if code == "hstech_513180":
            df = retry(lambda: ak.fund_etf_hist_em(symbol="513180", period="daily",
                       start_date=date, end_date=date, adjust=""), what=f"ETF{code}")
            amt_col = "成交额"
        else:
            pure = code[2:]  # 去掉 sh/sz/bj 前缀
            df = retry(lambda: ak.index_zh_a_hist(symbol=pure, period="daily",
                       start_date=date, end_date=date), what=f"指数{code}")
            amt_col = "成交额" if "成交额" in df.columns else "amount"
        if df is None or len(df) == 0 or amt_col not in df.columns:
            return None
        v = float(df.iloc[-1][amt_col])
        return round(v / 1e8, 2) if v > 1e6 else round(v, 2)  # 元→亿
    except Exception as e:  # noqa: BLE001
        log(f"指数 {code} {date} 成交额获取失败：{e}")
        return None
