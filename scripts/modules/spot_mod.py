# -*- coding: utf-8 -*-
"""全市场快照：AKShare 东财（主）→ efinance（备）→ 腾讯批量行情（兜底，非东财系通道）

容错约定：
- 单通道最多重试 2 次、间隔 5s（common.retry 内置全局限速）
- 任一通道返回缺列/空表/个股数异常（<_MIN_STOCKS）视为该通道失败，自动降级下一通道
- 三通道全部失败 → 抛出 SpotFetchError；build.py 捕获后保留旧数据、记录
  data/meta/last_error.log、推送失败通知，网站继续显示上一交易日数据
- 绝不返回伪造/随机/硬编码行情
"""
import datetime

import akshare as ak
import pandas as pd

from .common import retry, log, pace

COLUMNS = {
    "代码": "code", "名称": "name", "最新价": "close", "涨跌幅": "change_pct",
    "成交额": "amount", "总市值": "mktcap", "流通市值": "float_mktcap",
}

# 下游 compute/zt 模块依赖的最低限度列
REQUIRED_COLS = ["code", "name", "close", "change_pct", "amount", "mktcap"]

_MIN_STOCKS = 1000  # 全市场快照低于此数量视为通道异常（如仅返回部分市场/空表）


class SpotFetchError(RuntimeError):
    """全市场快照三通道（东财/efinance/腾讯）均不可用。

    构建方应捕获本异常：保留旧数据、记录错误日志、推送失败通知。"""


def _normalize(df, source: str) -> pd.DataFrame:
    """列名归一 + 类型清洗 + 有效性校验；不合格抛 ValueError 触发通道降级"""
    df = df.rename(columns=COLUMNS)
    missing = [c for c in REQUIRED_COLS if c not in df.columns]
    if missing:
        raise ValueError(f"返回缺少必需列 {missing}")
    if "float_mktcap" not in df.columns:
        df["float_mktcap"] = None
    for col in ("close", "change_pct", "amount", "mktcap", "float_mktcap"):
        df[col] = df[col].astype(str).str.replace(",", "", regex=False)
        df[col] = df[col].replace({"nan": None, "": None, "-": None, "None": None})
        df[col] = df[col].map(lambda v: float(v) if v is not None else None)
    df["code"] = df["code"].astype(str)
    df = df[df["code"].str.match(r"^\d{6}$", na=False)]
    if len(df) < _MIN_STOCKS:
        raise ValueError(f"仅返回 {len(df)} 只个股（全市场应≥{_MIN_STOCKS}，疑似残缺数据）")
    log(f"快照共 {len(df)} 只个股（{source}）")
    return df


def get_spot(date: str = None) -> pd.DataFrame:
    """全市场 A 股快照（code/name/close/change_pct/amount/mktcap，金额单位元）。

    date: 交易日 YYYYMMDD（腾讯兜底通道的 baostock 成分清单用）；None 取当天。
    三通道全失败抛 SpotFetchError，由调用方保留旧数据。
    """
    errors = []

    # 通道 1：东财全市场快照（AKShare）
    try:
        df = retry(lambda: ak.stock_zh_a_spot_em(), what="全市场快照(东财)")
        return _normalize(df, "东财")
    except Exception as e:  # noqa: BLE001
        errors.append(f"东财: {type(e).__name__} {e}")
        log(f"东财快照不可用（{e}），降级 efinance 备源")

    # 通道 2：efinance 实时行情（同为东财系接口，可能与通道 1 同时失效）
    try:
        import efinance as ef
        df = retry(lambda: ef.stock.get_realtime_quotes(), what="全市场快照(efinance)")
        df = df.rename(columns={"股票代码": "代码", "股票名称": "名称"})
        return _normalize(df, "efinance")
    except Exception as e:  # noqa: BLE001
        errors.append(f"efinance: {type(e).__name__} {e}")
        log(f"efinance 备源不可用（{e}），降级腾讯批量兜底通道")

    # 通道 3：腾讯批量行情（独立通道，与东财无关联；代码清单取 baostock 当日成分）
    try:
        return _tencent_spot(date)
    except Exception as e:  # noqa: BLE001
        errors.append(f"腾讯: {type(e).__name__} {e}")
        log(f"腾讯兜底通道也不可用（{e}）")

    raise SpotFetchError("全市场快照三通道均失败 || " + " || ".join(errors))


def _tencent_spot(date: str = None) -> pd.DataFrame:
    """腾讯批量行情快照。

    代码清单：baostock query_all_stock（当日沪深 A 股成分，不含北交所）。
    字段（qt.gtimg.cn）：f[1]=名称 f[2]=代码 f[3]=最新价 f[32]=涨跌幅
    f[37]=成交额(万元) f[44]=流通市值(亿) f[45]=总市值(亿)
    """
    import requests
    import baostock as bs

    if date is None:
        date = datetime.datetime.now().strftime("%Y%m%d")
    day = f"{date[:4]}-{date[4:6]}-{date[6:]}" if len(str(date)) == 8 else str(date)

    codes = []
    bs.login()
    try:
        rs = bs.query_all_stock(day=day)
        while getattr(rs, "error_code", "-1") == "0" and rs.next():
            bs_code = rs.get_row_data()[0]
            if bs_code.startswith(("sh.60", "sh.68", "sz.00", "sz.30")):
                codes.append(bs_code.replace(".", ""))
    finally:
        try:
            bs.logout()
        except Exception:  # noqa: BLE001
            pass
    if not codes:
        raise RuntimeError(f"baostock 当日({day})成分清单为空")

    s = requests.Session()
    s.trust_env = False
    rows = []
    for i in range(0, len(codes), 80):
        pace()
        batch = codes[i:i + 80]
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
                rows.append({
                    "code": f[2], "name": f[1],
                    "close": float(f[3]) if f[3] else None,
                    "change_pct": float(f[32]) if f[32] else None,
                    "amount": float(f[37]) * 1e4 if f[37] else None,   # 万元→元
                    "mktcap": float(f[45]) * 1e8 if f[45] else None,   # 亿元→元
                    "float_mktcap": float(f[44]) * 1e8 if f[44] else None,
                })
            except ValueError:
                continue
    df = pd.DataFrame(rows, columns=["code", "name", "close", "change_pct",
                                     "amount", "mktcap", "float_mktcap"])
    return _normalize(df, "腾讯批量")
