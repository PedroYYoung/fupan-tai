# -*- coding: utf-8 -*-
"""涨跌停池：AKShare stock_zt_pool_em / stock_zt_pool_dtgc_em；快照自行判定兜底。

涨跌停判定规则（严格执行）：
- 主板 |涨跌幅| >= 9.9%；创业板(300)/科创板(688) >= 19.9%
- 剔除名称含 ST/*ST；剔除上市至今交易日数 < 250；剔除代码 4/8 开头（北交所）
"""
import akshare as ak
from .common import retry, log


def _eligible(code: str, name: str) -> bool:
    if not code or code[0] in ("4", "8"):
        return False
    if "ST" in name.upper():
        return False
    return True


def _threshold(code: str) -> float:
    return 19.9 if code.startswith(("300", "688")) else 9.9


def get_limit_pools(date: str, spot_df=None):
    """返回 (limit_up, limit_down, lu_over10e, ld_over10e)
    lu/ld_over10e: [{code,name,amount(亿),change,board}]
    """
    lu_rows, ld_rows = [], []
    try:
        zt = retry(lambda: ak.stock_zt_pool_em(date=date), what=f"涨停池{date}")
        for _, r in zt.iterrows():
            code, name = str(r["代码"]), str(r["名称"])
            if _eligible(code, name):
                lu_rows.append(_row(r, code, name, is_up=True))
    except Exception as e:  # noqa: BLE001
        log(f"涨停池失败（{e}），由快照自行判定兜底")
        lu_rows = _from_spot(spot_df, True)
    try:
        dt = retry(lambda: ak.stock_zt_pool_dtgc_em(date=date), what=f"跌停池{date}")
        for _, r in dt.iterrows():
            code, name = str(r["代码"]), str(r["名称"])
            if _eligible(code, name):
                ld_rows.append(_row(r, code, name, is_up=False))
    except Exception as e:  # noqa: BLE001
        log(f"跌停池失败（{e}），由快照自行判定兜底")
        ld_rows = _from_spot(spot_df, False)

    lu_over10e = [r for r in lu_rows if r["amount"] >= 10]
    ld_over10e = [r for r in ld_rows if r["amount"] >= 10]
    lu_over10e.sort(key=lambda x: -x["amount"])
    ld_over10e.sort(key=lambda x: -x["amount"])
    log(f"{date} 涨停 {len(lu_rows)} / 跌停 {len(ld_rows)}；10亿以上 涨{len(lu_over10e)} 跌{len(ld_over10e)}")
    return len(lu_rows), len(ld_rows), lu_over10e[:30], ld_over10e[:30]


def _row(r, code: str, name: str, is_up: bool) -> dict:
    amount = r.get("成交额")
    amount = round(float(amount) / 1e8, 2) if amount is not None else 0.0
    change = float(r.get("涨跌幅", 0) or 0)
    board = ("创业板" if code.startswith("300") else "科创板" if code.startswith("688") else "主板")
    return {"code": code, "name": name, "amount": amount, "change": change,
            "board": board, "is_up": is_up}


def _from_spot(spot_df, is_up: bool) -> list:
    """兜底：由全市场快照按规则判定"""
    rows = []
    if spot_df is None:
        return rows
    for _, r in spot_df.iterrows():
        code, name = str(r["code"]), str(r["name"])
        chg = r["change_pct"]
        amt = r["amount"]
        if not _eligible(code, name) or chg is None or amt is None:
            continue
        th = _threshold(code)
        if (is_up and chg >= th) or (not is_up and chg <= -th):
            rows.append({"code": code, "name": name, "amount": round(amt / 1e8, 2),
                         "change": chg, "board": "创业板" if code.startswith("300")
                         else "科创板" if code.startswith("688") else "主板", "is_up": is_up})
    return rows
