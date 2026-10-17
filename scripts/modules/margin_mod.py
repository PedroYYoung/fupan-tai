# -*- coding: utf-8 -*-
"""两融余额：上交所 + 深交所官网汇总。

数据源（均为交易所官网，非东财、可被 GitHub Actions 访问）：
- 沪市：ak.stock_margin_sse(start_date, end_date)，单位「元」
- 深市：ak.stock_margin_szse(date)，单位「亿元」

关键口径 / 已知坑：
- 两融余额 = 沪市汇总余额 + 深市汇总余额（亿元）
- 沪市/深市单位不同：沪市为元（需 /1e8），深市为亿元（不得再除）
- 两融数据 T+1 发布：目标交易日当日通常未就绪，需回退到最近一个已发布交易日
"""
import akshare as ak
from .common import retry, log


def _to_yi(v) -> float:
    """源单位为元 → 亿元"""
    return round(float(str(v).replace(",", "")) / 1e8, 2)


def _fmt8(date: str) -> str:
    """统一转成 YYYYMMDD（支持 2026-10-10 或 20261010 输入）。"""
    return str(date).replace("-", "")


def get_margin(date: str, lookback_days: int = 15):
    """返回 (两融余额亿元, 实际统计日期 YYYYMMDD)；失败返回 (None, None)

    目标日数据未发布（T+1）时，自动回退到最近一个两所均已发布的交易日。
    深市缺失但沪市可用时，退化为仅沪市并如实记录（绝不把沪市当全市场）。
    """
    import datetime
    d8 = _fmt8(date)
    end = datetime.datetime.strptime(d8, "%Y%m%d")
    start = end - datetime.timedelta(days=lookback_days)
    start8 = start.strftime("%Y%m%d")

    # 沪市：区间查询一次，取范围内所有已发布日（元 → 亿）
    sse_map = {}
    try:
        sse = retry(lambda: ak.stock_margin_sse(start_date=start8, end_date=d8),
                    what="两融沪市区间")
        for _, r in sse.iterrows():
            d = _fmt8(str(r["信用交易日期"]))
            sse_map[d] = _to_yi(r["融资融券余额"])
    except Exception as e:  # noqa: BLE001
        log(f"两融沪市区间获取失败：{e}")
        return None, None
    if not sse_map:
        log(f"两融沪市 {start8}~{d8} 无已发布数据")
        return None, None

    # 深市：逐日查询（深交所单日接口，单位亿元）
    szse_map = {}
    for i in range(lookback_days + 1):
        dd = (end - datetime.timedelta(days=i)).strftime("%Y%m%d")
        try:
            z = ak.stock_margin_szse(date=dd)
            col = "融资融券余额" if "融资融券余额" in z.columns else "合计融资融券余额"
            szse_map[dd] = float(z[col].iloc[0])
        except Exception:  # noqa: BLE001
            continue

    common = sorted(set(sse_map) & set(szse_map), reverse=True)
    if not common:
        d = max(sse_map)
        log(f"两融：深市数据缺失，仅返回沪市 {d}（{sse_map[d]} 亿）")
        return round(sse_map[d], 2), d
    d = common[0]
    total = round(sse_map[d] + szse_map[d], 2)
    log(f"{d} 两融余额 {total} 亿（沪 {sse_map[d]} + 深 {szse_map[d]}）")
    return total, d
