# -*- coding: utf-8 -*-
"""两融余额：上交所 + 深交所官网汇总。

数据源（均为交易所官网，非东财、可被 GitHub Actions 访问）：
- 沪市：上海证券交易所 queryMargin.do（单位「元」，字段 rzrqjyzl=融资融券余额）
- 深市：ak.stock_margin_szse(date)（单位「亿元」，字段 融资融券余额）

关键口径 / 已知坑：
- 两融余额 = 沪市汇总余额 + 深市汇总余额（亿元）
- 沪市/深市单位不同：沪市为元（需 /1e8），深市为亿元（不得再除）
- 两融数据 T+1 发布：目标交易日当日通常未就绪，需回退到最近一个已发布交易日
- 本机/部分环境 requests 默认信任系统代理会导致 SSE 接口返回空（JSONDecodeError），
  故沪市抓取使用 trust_env=False 的 Session。
"""
import datetime

import requests

from .common import retry, log, pace

_SSE_URL = "https://query.sse.com.cn/marketdata/tradedata/queryMargin.do"
_SSE_HEADERS = {
    "Referer": "https://www.sse.com.cn/",
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/88.0.4324.150 Safari/537.36"),
}
# trust_env=False：绕过本地系统代理，避免 SSE 接口因代理返回空体
_SSE_SESSION = requests.Session()
_SSE_SESSION.trust_env = False
_SSE_SESSION.headers.update(_SSE_HEADERS)


def _fmt8(date: str) -> str:
    """统一转成 YYYYMMDD（支持 2026-10-10 或 20261010 输入）。"""
    return str(date).replace("-", "")


def _fetch_sse_range(start8: str, end8: str) -> dict:
    """上交所两融区间查询 → {YYYYMMDD: 亿元}；失败返回 {}。

    沪市接口返回的 rzrqjyzl（融资融券余额）单位为「元」，这里统一 /1e8 转亿元。
    """
    params = {
        "isPagination": "true",
        "beginDate": start8,
        "endDate": end8,
        "tabType": "",
        "stockCode": "",
        "pageHelp.pageSize": "5000",
        "pageHelp.pageNo": "1",
        "pageHelp.beginPage": "1",
        "pageHelp.cacheSize": "1",
        "pageHelp.endPage": "5",
    }
    try:
        pace()
        r = _SSE_SESSION.get(_SSE_URL, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
        rows = data.get("result") or []
        out = {}
        for x in rows:
            d = str(x.get("opDate") or "").replace("-", "")
            v = x.get("rzrqjyzl")  # 融资融券余额（元）
            if len(d) == 8 and v is not None:
                try:
                    out[d] = round(float(v) / 1e8, 2)
                except (TypeError, ValueError):
                    continue
        return out
    except Exception as e:  # noqa: BLE001
        log(f"两融沪市区间 {start8}~{end8} 获取失败：{e}")
        return {}


def _fetch_szse(date8: str):
    """深交所两融单日查询 → 亿元；失败返回 None。

    深交所返回的「融资融券余额」单位已为亿元，不得再除 1e8。
    """
    import akshare as ak
    try:
        pace()
        z = ak.stock_margin_szse(date=date8)
        col = "融资融券余额" if "融资融券余额" in z.columns else "合计融资融券余额"
        return float(z[col].iloc[0])
    except Exception:  # noqa: BLE001
        return None


def get_margin_total(date: str):
    """指定交易日的精确两融余额（用于历史回填，不做 T+1 回退）。

    返回 (total_亿, sse_亿, szse_亿, both_available: bool)。
    任一交易所缺失时：
      - both_available=False，total 仍返回可用单边（绝不把单边当双边、也不把缺失当 0 相加）。
    两所均失败返回 (None, None, None, False)。
    """
    d8 = _fmt8(date)
    sse_map = _fetch_sse_range(d8, d8)
    sse = sse_map.get(d8)
    szse = _fetch_szse(d8)
    if sse is None and szse is None:
        return None, None, None, False
    if sse is None or szse is None:
        # 单边缺失：如实返回，标记 both_available=False
        return (round(sse, 2) if sse is not None else round(szse, 2)), sse, szse, False
    return round(sse + szse, 2), sse, szse, True


def get_margin(date: str, lookback_days: int = 15):
    """返回 (两融余额亿元, 实际统计日期 YYYYMMDD)；失败返回 (None, None)

    目标日数据未发布（T+1）时，自动回退到最近一个两所均已发布的交易日。
    深市缺失但沪市可用时，退化为仅沪市并如实记录（绝不把沪市当全市场）。
    """
    d8 = _fmt8(date)
    end = datetime.datetime.strptime(d8, "%Y%m%d")
    start = end - datetime.timedelta(days=lookback_days)
    start8 = start.strftime("%Y%m%d")

    # 沪市：区间查询一次，取范围内所有已发布日（元 → 亿）
    sse_map = _fetch_sse_range(start8, d8)
    if not sse_map:
        log(f"两融沪市 {start8}~{d8} 无已发布数据")
        return None, None

    # 深市：逐日查询（深交所单日接口，单位亿元）
    szse_map = {}
    for i in range(lookback_days + 1):
        dd = (end - datetime.timedelta(days=i)).strftime("%Y%m%d")
        v = _fetch_szse(dd)
        if v is not None:
            szse_map[dd] = v

    common = sorted(set(sse_map) & set(szse_map), reverse=True)
    if not common:
        d = max(sse_map)
        log(f"两融：深市数据缺失，仅返回沪市 {d}（{sse_map[d]} 亿）")
        return round(sse_map[d], 2), d
    d = common[0]
    total = round(sse_map[d] + szse_map[d], 2)
    log(f"{d} 两融余额 {total} 亿（沪 {sse_map[d]} + 深 {szse_map[d]}）")
    return total, d
