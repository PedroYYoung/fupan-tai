# -*- coding: utf-8 -*-
"""涨跌停池：AKShare stock_zt_pool_em / stock_zt_pool_dtgc_em；快照自行判定兜底。

涨跌停判定规则（严格执行）：
- 主板 |涨跌幅| >= 9.9%；创业板(300)/科创板(688) >= 19.9%
- 剔除名称含 ST/*ST；剔除上市至今交易日数 < 250；剔除代码 4/8 开头（北交所）

数据可用性（**关键**）：
- 涨停池 `stock_zt_pool_em(date)` 支持任意历史交易日
- 跌停池 `stock_zt_pool_dtgc_em(date)` **只支持最近 30 个自然日**（服务端只保留近期数据，
  akshare 在客户端也做了同样的 30 天拦截）——因此历史跌停家数**无法事后回补**，
  只能在当日采集。缺口必须保留为「无数据」，不得补 0。
- 「接口成功但返回 0 家」与「接口失败」必须区分：前者是真实的 0（如普涨日无跌停），
  后者是缺失。本模块用 `ok` 标记区分，调用方据此决定写 0 还是写 None。
"""
import akshare as ak
from .common import retry, log

# 跌停池服务端保留窗口（自然日）。超过该窗口的日期只能拿 0 或报错，均不可信。
DT_POOL_RETENTION_DAYS = 30


def _eligible(code: str, name: str) -> bool:
    if not code or code[0] in ("4", "8"):
        return False
    if "ST" in name.upper():
        return False
    return True


def _threshold(code: str) -> float:
    return 19.9 if code.startswith(("300", "688")) else 9.9


def _rows(df, is_up: bool) -> list:
    out = []
    for _, r in df.iterrows():
        code, name = str(r["代码"]), str(r["名称"])
        if _eligible(code, name):
            out.append(_row(r, code, name, is_up))
    return out


def fetch_pools(date: str, spot_df=None) -> dict:
    """抓取涨跌停池，返回带可用性标记的结果。

    返回 dict:
      lu / ld            : int 或 None（None = 数据不可得，**不是 0**）
      lu_rows / ld_rows  : 明细列表（按成交额门槛由调用方切分）
      lu_ok / ld_ok      : bool，接口是否成功返回（0 家也算成功）
      lu_src / ld_src    : "eastmoney" | "spot" | None
      ld_reason          : 跌停不可用的原因（用于快照 note / 排查）
    """
    out = {"lu": None, "ld": None, "lu_rows": [], "ld_rows": [],
           "lu_ok": False, "ld_ok": False,
           "lu_src": None, "ld_src": None, "ld_reason": None}

    # ---- 涨停池（历史可用）----
    try:
        zt = retry(lambda: ak.stock_zt_pool_em(date=date), what=f"涨停池{date}")
        out["lu_rows"] = _rows(zt, True)
        out["lu"], out["lu_ok"], out["lu_src"] = len(out["lu_rows"]), True, "eastmoney"
    except Exception as e:  # noqa: BLE001
        log(f"涨停池失败（{type(e).__name__}: {e}）")
        if spot_df is not None:
            # 仅实时交易日允许用快照兜底（历史日期传 spot_df=None，绝不伪造）
            out["lu_rows"] = _from_spot(spot_df, True)
            out["lu"], out["lu_src"] = len(out["lu_rows"]), "spot"
            log(f"涨停池由快照兜底判定：{out['lu']} 家")
        else:
            log(f"涨停池不可用：{date} 置为 None（不写 0）")

    # ---- 跌停池（仅最近 30 自然日）----
    # 注意：超出窗口是**确定性错误**（akshare 直接抛 ValueError），重试没有意义，
    # 只对网络类异常走 retry，避免每天白等 10 秒。
    try:
        try:
            dt = ak.stock_zt_pool_dtgc_em(date=date)
        except ValueError as e:
            if "30" in str(e):
                raise
            dt = retry(lambda: ak.stock_zt_pool_dtgc_em(date=date), what=f"跌停池{date}")
        out["ld_rows"] = _rows(dt, False)
        # 接口成功返回：可能是 0 家（真实），此时 ld=0 是合法值
        out["ld"], out["ld_ok"], out["ld_src"] = len(out["ld_rows"]), True, "eastmoney"
    except Exception as e:  # noqa: BLE001
        msg = str(e)
        limited = ("30 个交易日" in msg) or ("30个交易日" in msg)
        out["ld_reason"] = ("东财跌停股池只保留最近 %d 个自然日，%s 已超出窗口，无法回补"
                            % (DT_POOL_RETENTION_DAYS, date)) if limited else \
                           f"跌停池接口失败：{type(e).__name__}"
        log(f"跌停池失败（{type(e).__name__}: {msg[:60]}）→ {out['ld_reason']}")
        if spot_df is not None:
            out["ld_rows"] = _from_spot(spot_df, False)
            out["ld"], out["ld_src"] = len(out["ld_rows"]), "spot"
            log(f"跌停池由快照兜底判定：{out['ld']} 家")
        else:
            log(f"跌停池不可用：{date} 置为 None（不写 0、不写入序列）")

    lu5 = sum(1 for r in out["lu_rows"] if r["amount"] >= 5)
    ld5 = sum(1 for r in out["ld_rows"] if r["amount"] >= 5)
    log(f"{date} 涨停 {out['lu']} / 跌停 {out['ld']}；≥5亿 涨{lu5} 跌{ld5}")
    return out


def get_limit_pools(date: str, spot_df=None):
    """兼容旧签名：返回 (limit_up, limit_down, lu_rows, ld_rows)。

    注意 limit_up / limit_down 可能为 None（数据不可得），调用方必须区分 None 与 0。
    """
    r = fetch_pools(date, spot_df)
    return r["lu"], r["ld"], r["lu_rows"], r["ld_rows"]


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
