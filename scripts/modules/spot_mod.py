# -*- coding: utf-8 -*-
"""全市场快照：AKShare stock_zh_a_spot_em()（主源）；efinance 为备源"""
import akshare as ak
from .common import retry, log

COLUMNS = {
    "代码": "code", "名称": "name", "最新价": "close", "涨跌幅": "change_pct",
    "成交额": "amount", "总市值": "mktcap", "流通市值": "float_mktcap",
}


def get_spot():
    """全市场 A 股快照，列名归一为 code/name/close/change_pct/amount/mktcap（元）"""
    try:
        df = retry(lambda: ak.stock_zh_a_spot_em(), what="全市场快照(em)")
    except Exception as e:  # noqa: BLE001
        log(f"东财快照失败（{e}），切换 efinance 备源")
        import efinance as ef
        df = retry(lambda: ef.stock.get_realtime_quotes(), what="全市场快照(efinance)")
        df = df.rename(columns={
            "股票代码": "代码", "股票名称": "名称", "最新价": "最新价",
            "涨跌幅": "涨跌幅", "成交额": "成交额", "总市值": "总市值"})
    df = df.rename(columns=COLUMNS)
    for col in ("close", "change_pct", "amount", "mktcap"):
        df[col] = df[col].astype(str).str.replace(",", "", regex=False)
        df[col] = df[col].replace({"nan": None, "": None, "-": None})
        df[col] = df[col].map(lambda v: float(v) if v is not None else None)
    df = df[df["code"].str.match(r"^\d{6}$")]
    log(f"快照共 {len(df)} 只个股")
    return df
