# -*- coding: utf-8 -*-
"""行业板块：东财（主）→ 同花顺 THS（备，独立于东财）

数据源：
- 主源 东财：ak.stock_board_industry_name_em()（当日涨跌+成交额）
- 备源 同花顺：ak.stock_board_industry_summary_ths()（板块/涨跌幅/总成交额，独立通道）
  历史周排名备源：ak.stock_board_industry_index_ths(板块名)（同花顺行业指数日线）

口径说明（UI 同步标注）：当日涨跌幅为板块口径，成交额单位亿元，
占两市比 = 板块成交额 / 两市总成交额。
"""
import akshare as ak
from concurrent.futures import ThreadPoolExecutor, as_completed
from .common import retry, log


def _industry_rows(df, total_amount, name_col, change_col, amount_col, amount_in_yi):
    """把行业快照 DataFrame 转成 [{name, change, amount, ratio}]；无有效行返回 None"""
    rows = []
    for _, r in df.iterrows():
        try:
            name = str(r[name_col]).strip()
            change = float(str(r[change_col]).replace("%", "").replace(",", ""))
            amt = float(str(r[amount_col]).replace(",", ""))
        except (TypeError, ValueError, KeyError):
            continue
        if not name:
            continue
        if not amount_in_yi:
            amt = amt / 1e8
        rows.append({
            "name": name, "change": round(change, 2),
            "amount": round(amt, 1),
            "ratio": round(amt / total_amount * 100, 2) if total_amount else 0,
        })
    return rows or None


def _top_bottom(rows):
    """按涨跌幅取上涨/下跌 TOP10（平盘不入列）"""
    ups = sorted([x for x in rows if x["change"] > 0], key=lambda x: -x["change"])[:10]
    downs = sorted([x for x in rows if x["change"] < 0], key=lambda x: x["change"])[:10]
    return ups, downs


def _industry_daily_em(total_amount):
    """东财行业板块（主源）"""
    try:
        df = retry(lambda: ak.stock_board_industry_name_em(), what="东财行业板块")
    except Exception as e:  # noqa: BLE001
        log(f"东财行业板块获取失败：{e}")
        return None
    rows = _industry_rows(df, total_amount, "板块名称", "涨跌幅", "成交额", amount_in_yi=False)
    if not rows:
        log("东财行业板块：解析后无有效行")
        return None
    ups, downs = _top_bottom(rows)
    log(f"行业板块（东财）：{len(rows)} 个，上涨TOP1 {ups[0]['name'] if ups else '-'} "
        f"{ups[0]['change'] if ups else '-'}%")
    return {"top10_up": ups, "top10_down": downs, "source": "eastmoney",
            "note": "口径：东财行业板块当日数据"}


def _industry_daily_ths(total_amount):
    """同花顺行业板块（备源，独立于东财）"""
    try:
        df = retry(lambda: ak.stock_board_industry_summary_ths(), what="同花顺行业板块")
    except Exception as e:  # noqa: BLE001
        log(f"同花顺行业板块获取失败：{e}")
        return None
    rows = _industry_rows(df, total_amount, "板块", "涨跌幅", "总成交额", amount_in_yi=True)
    if not rows:
        log("同花顺行业板块：解析后无有效行")
        return None
    # 单位识别：同花顺「总成交额」通常为亿元；若板块中位数过大则实为「元」，需转亿
    med = sorted(x["amount"] for x in rows)[len(rows) // 2]
    if med > 5000:
        for x in rows:
            x["amount"] = round(x["amount"] / 1e8, 1)
            x["ratio"] = round(x["amount"] / total_amount * 100, 2) if total_amount else 0
    ups, downs = _top_bottom(rows)
    log(f"行业板块（同花顺）：{len(rows)} 个，上涨TOP1 {ups[0]['name'] if ups else '-'} "
        f"{ups[0]['change'] if ups else '-'}%")
    return {"top10_up": ups, "top10_down": downs, "source": "ths",
            "note": "口径：同花顺行业板块当日数据"}


def get_industry_daily(total_amount: float):
    """返回 {top10_up, top10_down, source, note}；东财 → 同花顺，均失败返回 None"""
    data = _industry_daily_em(total_amount)
    if data is None:
        log("东财行业失败，降级同花顺行业板块")
        data = _industry_daily_ths(total_amount)
    return data


def backfill_industry(mapping_csv: str, start: str, end: str):
    """（可选）申万二级行业指数历史回填。需用户提供对齐表 CSV：east_name,sw_code,sw_name"""
    import pandas as pd
    from . import compute
    mp = pd.read_csv(mapping_csv)
    log(f"行业历史回填：{len(mp)} 条对齐（{start}~{end}）")
    for _, r in mp.iterrows():
        code = str(r["sw_code"])
        try:
            df = retry(lambda: ak.index_hist_sw(symbol=code, period="day",
                                                start_date=start, end_date=end),
                       what=f"申万{code}")
            pts = [{"date": str(d).replace("-", ""), "value": round(float(v) / 1e8, 2)}
                   for d, v in zip(df["日期"], df["成交额"])]
            for p in pts:
                compute.update_series(f"industry_sw_{code}", str(r["sw_name"]), "亿元", p["date"], p["value"])
        except Exception as e:  # noqa: BLE001
            log(f"申万 {code} 回填失败：{e}")
    log("行业历史回填完成")


# ------------------------------------------------------------------
# 行业周涨跌排名（东财 → 同花顺）
# ------------------------------------------------------------------
def _week_start(date: str, dates: list) -> str | None:
    """返回当前交易周第一个交易日（周一或之后首个交易日）"""
    import datetime
    d = datetime.datetime.strptime(date, "%Y%m%d")
    mon = d - datetime.timedelta(days=d.weekday())
    start = mon.strftime("%Y%m%d")
    candidates = [x for x in dates if start <= x <= date]
    return candidates[0] if candidates else None


def _week_change_em(name: str, start: str, end: str):
    """单个行业本周涨跌幅（%）；东财板块历史，失败返回 None"""
    try:
        df = ak.stock_board_industry_hist_em(symbol=name, start_date=start, end_date=end,
                                             period="日k", adjust="")
        if df is None or len(df) < 1:
            return None
        first = float(df.iloc[0]["收盘"])
        last = float(df.iloc[-1]["收盘"])
        if first <= 0:
            return None
        return round((last / first - 1) * 100, 2)
    except Exception:  # noqa: BLE001
        return None


def _week_change_ths(name: str, start: str, end: str):
    """单个行业本周涨跌幅（%）；同花顺行业指数日线，失败返回 None"""
    try:
        df = ak.stock_board_industry_index_ths(symbol=name, start_date=start, end_date=end)
        if df is None or len(df) < 1:
            return None
        first = float(df.iloc[0]["收盘价"])
        last = float(df.iloc[-1]["收盘价"])
        if first <= 0:
            return None
        return round((last / first - 1) * 100, 2)
    except Exception:  # noqa: BLE001
        return None


def _industry_week_rank_em(date: str, dates: list):
    try:
        start = _week_start(date, dates)
        if not start:
            log(f"行业周排名：无法确定 {date} 的本周起点")
            return None
        names_df = retry(lambda: ak.stock_board_industry_name_em(), what="东财行业名称列表")
        names = names_df["板块名称"].astype(str).tolist()
        results = []
        with ThreadPoolExecutor(max_workers=5) as ex:
            future_to_name = {ex.submit(_week_change_em, name, start, date): name for name in names}
            for fut in as_completed(future_to_name):
                name = future_to_name[fut]
                chg = fut.result()
                if chg is not None:
                    results.append({"name": name, "change": chg})
        if not results:
            return None
        results.sort(key=lambda x: -x["change"])
        top5 = results[:5]
        bottom5 = results[-5:][::-1]
        log(f"行业周排名（东财）：{len(results)} 个行业，TOP {top5[0]['name']} {top5[0]['change']}%")
        return {"top5": top5, "bottom5": bottom5}
    except Exception as e:  # noqa: BLE001
        log(f"行业周排名（东财）获取失败：{e}")
        return None


def _industry_week_rank_ths(date: str, dates: list):
    try:
        start = _week_start(date, dates)
        if not start:
            return None
        df = retry(lambda: ak.stock_board_industry_summary_ths(), what="同花顺行业名称列表")
        names = df["板块"].astype(str).tolist()
        results = []
        with ThreadPoolExecutor(max_workers=5) as ex:
            future_to_name = {ex.submit(_week_change_ths, name, start, date): name for name in names}
            for fut in as_completed(future_to_name):
                name = future_to_name[fut]
                chg = fut.result()
                if chg is not None:
                    results.append({"name": name, "change": chg})
        if not results:
            return None
        results.sort(key=lambda x: -x["change"])
        top5 = results[:5]
        bottom5 = sorted(results, key=lambda x: x["change"])[:5]
        log(f"行业周排名（同花顺）：{len(results)} 个行业，TOP {top5[0]['name']} {top5[0]['change']}%")
        return {"top5": top5, "bottom5": bottom5}
    except Exception as e:  # noqa: BLE001
        log(f"行业周排名（同花顺）获取失败：{e}")
        return None


def get_industry_week_rank(date: str, dates: list):
    """返回 {top5: [{name, change}], bottom5: [...]}；东财 → 同花顺，均失败返回 None"""
    res = _industry_week_rank_em(date, dates)
    if res is not None:
        return res
    log("东财行业周排名失败，降级同花顺")
    return _industry_week_rank_ths(date, dates)
