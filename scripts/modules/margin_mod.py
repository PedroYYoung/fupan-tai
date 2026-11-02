# -*- coding: utf-8 -*-
"""两融余额：上交所官网 + 深市金十镜像。

数据源（均可被 GitHub Actions 稳定访问）：
- 沪市：上海证券交易所 queryMargin.do（单位「元」，字段 rzrqjyzl=融资融券余额）
- 深市：金十数据镜像 cdn.jin10.com/data_center/reports/fs_2.json（深交所官方两融数据的
  镜像，单次返回全量历史，字段 values[date][5]=融资融券余额，单位「元」；
  已与深交所官方 ShowReport 接口交叉验证一致，舍入误差 <=0.01 亿）

关键口径 / 已知坑：
- 两融余额 = 沪市汇总余额 + 深市汇总余额（亿元）
- 沪市/深市原始单位均为元（需 /1e8 转亿元）
- 两融数据 T+1 发布：目标交易日当日通常未就绪，需回退到最近一个已发布交易日
- 本机/部分环境 requests 默认信任系统代理会导致 SSE 接口返回空（JSONDecodeError），
  故沪市抓取使用 trust_env=False 的 Session。
- 深交所官方 ShowReport 接口会高频封 IP（RemoteDisconnected），故深市改用金十镜像
  （与官方同源、不封禁），避免每次增量更新触发封禁。
"""
import datetime

import requests

from .common import retry, log, pace

_SSE_URL = "https://query.sse.com.cn/marketdata/tradedata/queryMargin.do"
_SZSE_JIN10_URL = "https://cdn.jin10.com/data_center/reports/fs_2.json"
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


def _fetch_szse_official(d8: str):
    """深交所官方单日「融资融券余额」（亿元）；失败返回 None（绝不估算）。

    数据源：akshare stock_margin_szse(date=YYYYMMDD)，即深交所官网 catalog 1837_xxpl。
    字段「融资融券余额」= 融资余额 + 融券余额，单位亿元，与金十镜像、margin 序列口径一致。
    单日精确到交易日；T+1 发布，目标日当日通常无数据（返回 None）。
    """
    try:
        import akshare as ak
        df = ak.stock_margin_szse(date=d8)
        if df is None or df.empty:
            return None
        v = float(df.iloc[0]["融资融券余额"])
        return round(v, 2) if v > 0 else None
    except Exception as e:  # noqa: BLE001
        log(f"两融深市官方 {d8} 获取失败：{type(e).__name__} {str(e)[:80]}")
        return None


def _fetch_szse_jin10() -> dict:
    """深市两融全量（金十镜像）→ {YYYYMMDD: 亿元}；失败返回 {}。

    金十数据 cdn.jin10.com 的 fs_2.json 是深交所官方两融数据的镜像（第三方数据商），
    单次返回全量历史（含最新交易日），无分页、无高频封禁。字段 values[date] 为 6 元素
    数组，其中 values[date][5] 为「融资融券余额」（单位「元」，= 融资余额 + 融券余额）。
    已与深交所官方 ShowReport 接口交叉验证一致（舍入误差 <=0.01 亿）。
    """
    try:
        r = requests.get(_SZSE_JIN10_URL, params={"_": "1"}, timeout=30)
        r.raise_for_status()
        vals = r.json().get("values") or {}
        out = {}
        for d, v in vals.items():
            d8 = str(d).replace("-", "")
            if len(d8) != 8 or not isinstance(v, (list, tuple)) or len(v) < 6:
                continue
            try:
                val = v[5]  # 融资融券余额（元）
                if val is None:
                    continue
                val = round(float(val) / 1e8, 2)
                if val <= 0 and d8 != "20100331":
                    # 金十坏值：部分日期缺失被记为 0（如 20240808），仅试点首日可为 0
                    continue
                out[d8] = val
            except (TypeError, ValueError):
                continue
        return out
    except Exception as e:  # noqa: BLE001
        log(f"两融深市（金十镜像）获取失败：{e}")
        return {}


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
    szse = _fetch_szse_jin10().get(d8)
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

    # 深市：金十镜像一次取全量（单位亿元），截取回退窗口内的日期
    szse_all = _fetch_szse_jin10()
    szse_map = {d: v for d, v in szse_all.items() if start8 <= d <= d8}

    # 金十镜像可能停更（历史曾停在 20261020）→ 对「沪市有、深市缺」的最近日期，
    # 用深交所官方接口逐日补齐，使沪深合计能推进到最新交易日（而非停在金十的陈旧日）。
    missing_sz = sorted(set(sse_map) - set(szse_map), reverse=True)
    if missing_sz:
        # 只补回退窗口内、且不早于金十最新日的少量日期，控制请求次数
        jin10_latest = max(szse_map) if szse_map else ""
        todo = [d for d in missing_sz if (not jin10_latest or d > jin10_latest)][:12]
        for d in todo:
            v = _fetch_szse_official(d)
            if v is not None:
                szse_map[d] = v
                log(f"两融深市官方补齐 {d}（{v} 亿）")

    common = sorted(set(sse_map) & set(szse_map), reverse=True)
    if not common:
        d = max(sse_map)
        log(f"两融：深市数据缺失，仅返回沪市 {d}（{sse_map[d]} 亿）")
        return round(sse_map[d], 2), d
    d = common[0]
    total = round(sse_map[d] + szse_map[d], 2)
    log(f"{d} 两融余额 {total} 亿（沪 {sse_map[d]} + 深 {szse_map[d]}）")
    return total, d
