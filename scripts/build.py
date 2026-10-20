#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复盘台数据构建脚本（本地/CI 双模式）

用法：
  python scripts/build.py --date 20260925    # 单日快照模式（指定交易日）
  python scripts/build.py --incremental      # 增量模式（自动取最近一个已收盘交易日）
  python scripts/build.py --date 20260925 --backfill-days 20   # 本地回补（含序列窗口）

硬性规则：
- 历史回补只在本地跑；CI 只做每日增量
- 实时快照接口不接受历史日期：仅当目标日 == 最近已收盘交易日时才抓取全市场行情，
  否则写 data_quality.spot_derived=unavailable/carried_over，绝不把当前会话行情写进历史
- 单接口最多重试 2 次、间隔 5s；每 50 次请求 sleep 2s
- 全部写入 *.tmp，校验通过后原子替换
- 任一日失败 → 保留旧数据、写 data/meta/last_error.log、exit 0
"""
import argparse
import copy
import datetime
import os
import sys
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.common import (CST, DATA_DIR, REPO_ROOT, atomic_write_json, log,  # noqa: E402
                            now_cst, now_iso, record_error, retry)
from modules import calendar_mod, compute, index_mod, industry_mod, margin_mod, notify, spot_mod, zt_mod  # noqa: E402


# 北京时间（UTC+8，固定偏移，不依赖 tzdata）。GitHub Actions runner 的本地时间是 UTC，
# 若用 naive now() 判定收盘阈值，UTC 下全天都会被视为「今日未收盘」，
# 流水线将永远指向前一交易日，并连带使「行情日期须等于目标交易日」的腾讯通道失效。
_CST = CST

# A 股连续竞价 15:00 收盘；留 5 分钟给收盘集合竞价结果与源端落库，避免拿到未定稿数据。
CLOSE_HOUR, CLOSE_MINUTE = 15, 5


def last_closed_trade_date(dates: list, now: datetime.datetime | None = None) -> str:
    """最近一个「已收盘」的交易日（北京时间 15:05 前视为当日未收盘）

    注意：这里判断的是**行情所属交易日**，与「数据生成时间」是两个概念。
    未收盘时返回上一交易日，绝不用「今天」的日期去标注尚未完成的行情。
    """
    now = now or now_cst()
    today = now.strftime("%Y%m%d")
    cutoff = now.replace(hour=CLOSE_HOUR, minute=CLOSE_MINUTE, second=0, microsecond=0)
    past = [d for d in dates if d <= today]
    if not past:
        raise RuntimeError("交易日历为空")
    if past[-1] == today and now < cutoff and len(past) >= 2:
        return past[-2]
    return past[-1]


def _previous_trade_day(date: str, dates: list) -> str | None:
    """返回 date 在交易日历中的上一个交易日。"""
    if date not in dates:
        return None
    i = dates.index(date)
    return dates[i - 1] if i > 0 else None


# ---- 实时派生数据状态（写入 daily/{date}.json 的 data_quality.spot_derived）----
SPOT_REALTIME = "realtime"        # 本次由实时快照抓取（目标日 = 最近已收盘交易日）
SPOT_CARRIED = "carried_over"     # 历史日期重建：沿用旧快照中当时写入的真实值
SPOT_UNAVAILABLE = "unavailable"  # 无可靠历史来源：相关字段置空、不下发

_NOTE_UNAVAILABLE = ("该交易日的全市场个股快照无可靠历史来源（实时接口只返回当前会话），"
                     "集中度/流动性结构/10亿以上家数等字段已置空，未做任何估算或填充")


def is_realtime_session_target(date: str, dates: list) -> bool:
    """目标日期是否为「最近一个已收盘交易日」——实时快照写入的唯一闸门。

    原因：全市场快照接口（ak.stock_zh_a_spot_em / efinance / 腾讯批量）都不接受
    历史日期参数，永远返回**当前会话**行情。只有当目标日恰好是最近已收盘交易日时，
    抓到的数据才确实属于该日期；用 `--date` 重跑更早的交易日会把「今天」的行情
    写进历史快照（20261009/20261013/20261014 三份快照即由此被污染）。
    """
    return date == last_closed_trade_date(dates)


def _carried_spot_state(existing):
    """历史日期重建时，决定实时派生字段的处置方式 → (state, note)。

    · 旧快照已标记不可用 → 保持不可用（不得因重跑而复活错误数据）
    · 旧快照有全市场字段 → carried_over，原样沿用（不重算、不清空）
    · 无旧快照 / 旧快照无该字段 → unavailable
    """
    q = (existing or {}).get("data_quality") or {}
    if q.get("spot_derived") == SPOT_UNAVAILABLE:
        return SPOT_UNAVAILABLE, q.get("note") or _NOTE_UNAVAILABLE
    if existing and ((existing.get("concentration") or {}).get("top10")):
        return SPOT_CARRIED, ("实时快照仅覆盖最近交易日；本日沿用重建前快照中记录的全市场字段"
                              "（本次未重新抓取，未做任何改写）")
    return SPOT_UNAVAILABLE, _NOTE_UNAVAILABLE


def _carry_row(existing, code: str):
    """从旧快照的 index_volume/widebase 中取回指定 code 的行（深拷贝）；无则 None"""
    for r in ((existing or {}).get("index_volume") or []) + ((existing or {}).get("widebase") or []):
        if r.get("code") == code:
            row = copy.deepcopy(r)
            row["amount_change"] = None
            row["close_change"] = None
            return row
    return None


def _empty_concentration() -> dict:
    """集中度「不可用」占位：结构与正常一致，数值为 None、列表为空（前端显示「—」）"""
    return {"top_n": [10, 20, 50], "top10": [], "top20": [], "top50": [],
            "top20_cum_pct": None, "top50_cum_pct": None, "top10_total": None,
            "top10_total_pctile_hist": None}


def _empty_liquidity() -> dict:
    """流动性「不可用」占位：分档表为空、家数为 None（绝不写 0 冒充真实值）"""
    return {"over_10e_count": None, "over_10e_ratio": None, "pctile_count": None,
            "mktcap_buckets": [], "amount_buckets": [],
            "over_10e_marketcap_buckets": [], "over_10e_marketcap_value_buckets": []}



def _load_daily(date: str):
    """读取 daily/{date}.json 全量快照；不存在或损坏返回 None"""
    import json
    p = os.path.join(DATA_DIR, "daily", f"{date}.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def _load_industry_from_daily(date: str):
    """从指定日期的 daily 文件中读取 industry 字段。"""
    import json
    p = os.path.join(DATA_DIR, "daily", f"{date}.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d.get("industry")
    except Exception:  # noqa: BLE001
        return None


def _resolve_total_amount(spot_df, idx_rows: list, date: str):
    """两市成交额口径：优先「上证综指 + 深证成指」指数口径。

    原因：series/total_amount 全历史均按沪+深指数成交额定义（可被 baostock 逐日核验），
    而快照口径为全市场个股求和，个别交易日会因源端缺行/串会话偏离 10% 以上。
    仅当两只指数当日均为真实抓取值（amount_date == date 且无降级标记）时采用指数口径，
    否则回退快照口径，保证任何情况下都不写入缺失/降级值。

    spot_df=None 表示本次**没有**可用的当日实时快照（历史日期重建）。此时只接受
    指数口径；指数也不可用则返回 None，由调用方沿用旧值或标记不可用，绝不填 0。
    """
    spot_total = (round(float(spot_df["amount"].dropna().sum()) / 1e8, 2)
                  if spot_df is not None else None)
    idx = {r.get("code"): r for r in idx_rows}
    sh, sz = idx.get("sh000001"), idx.get("sz399001")
    usable = all(r is not None and r.get("amount") is not None
                 and r.get("amount_date") == date and not r.get("note")
                 for r in (sh, sz))
    if not usable:
        if spot_total is None:
            log(f"两市成交额：{date} 快照与指数口径均不可用（不做估算）")
            return None
        log(f"指数成交额当日不可用，两市成交额回退快照口径 {spot_total}")
        return spot_total
    total = round(sh["amount"] + sz["amount"], 2)
    if spot_total and abs(total - spot_total) / spot_total > 0.05:
        log(f"⚠ 成交额口径分叉：指数口径 {total} vs 快照口径 {spot_total}"
            f"（快照偏离 {round((spot_total - total) / total * 100, 2)}%），采用指数口径")
    return total


def build_one(date: str, dates: list, backfill_days: int = 0):
    """构建单日快照并维护序列；任何异常向上抛出

    **日期保护**：只有「目标日 == 最近已收盘交易日」时才允许调用实时快照接口。
    对更早的日期重跑（如 --date 20261014），所有依赖实时全市场行情的字段
    （个股集中度 / 流动性分档 / 10亿以上家数 / 涨跌停兜底判定 / 微盘代理 /
    高活跃个股 / 行业板块当日快照 / 两市成交额快照口径）一律不抓取、不写入：
      · 旧快照已有该字段 → 原样沿用（不清空、不重算、不伪造）
      · 旧快照没有 → 置 None / 空列表，并写 data_quality.spot_derived=unavailable
    指数成交额、两融、涨跌停池、行业周排名等「按日期查询」的数据源不受影响，
    历史日期依然可以用它们更新对应历史数据。
    """
    log(f"===== 构建交易日 {date} =====")
    # 非交易日防线：东财对非交易日返回「涨停 0 家 / 跌停 0 家」且 HTTP 200，
    # 值域上完全合法 —— 一旦写进序列就是一个看起来真实的假点（20261010 周六即如此）。
    # 因此日期合法性必须在写任何数据之前判定，不能靠「值是否为 0」兜底。
    if date not in dates:
        raise RuntimeError(f"{date} 不是交易日：拒绝构建与写入（防止非交易日 0 值污染序列）")
    realtime = is_realtime_session_target(date, dates)
    existing = _load_daily(date)

    spot_df = None
    if realtime:
        spot_df = spot_mod.get_spot(date)
    else:
        log(f"{date} 非最近已收盘交易日（{last_closed_trade_date(dates)}）："
            "实时快照只返回当前会话行情，本日不抓取、不写入实时派生字段")

    # ---- 序列读取工具（指数降级需要「最近交易日真实值」，须先定义）----
    def series_points(key: str) -> list:
        import json
        p = os.path.join(DATA_DIR, "series", f"{key}.json")
        if not os.path.exists(p):
            return []
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f).get("points", [])

    def series_values(key: str) -> list:
        return [pt["value"] for pt in series_points(key)]

    def last_known_point(code: str):
        """序列中最近一个早于 date 的已知真实值 → (value, date)；无则 (None, None)"""
        for pt in reversed(series_points(f"index_amount_{code}")):
            if pt["date"] < date and pt.get("value") is not None:
                return pt["value"], pt["date"]
        return None, None

    # ---- 指数/宽基成交额（含当日 + 降级：最近交易日 / ETF 代理）----
    def fetch_index_rows(d: str):
        rows_idx, rows_wide = [], []

        def make_row(code: str, base_approx: bool):
            amt, amt_date, note = index_mod.get_index_amount_resilient(
                code, d, last_known_point(code))
            chg = index_mod.get_index_change_pct(code, d)
            close = index_mod.get_index_close(code, d)
            return {"name": index_mod.INDEX_CODES[code], "code": code,
                    "amount": amt, "amount_date": amt_date, "note": note,
                    "change_pct": chg, "close": close,
                    "amount_change": None, "close_change": None,
                    "rank_year": None, "rank_1y": None, "pctile_all": None,
                    "approx": (base_approx and amt is not None) or note != ""}

        for code in ["sh000001", "sz399001", "sz399006", "sh000688", "bj899050"]:
            rows_idx.append(make_row(code, code == "bj899050"))
        for code in ["sh000016", "sh000300", "sz399673", "sh000688", "sh000905",
                     "sh000906", "sh000852", "sh932000", "sh000985", "hstech_513180"]:
            rows_wide.append(make_row(code, code == "hstech_513180"))

        # sh000985（中证全指）没有可用的全历史成交额源：序列层（index_amount_sh000985）
        # 一直与 total_amount 同值，即「沪深两市指数成交额合计」代理口径。
        # 快照层此前直接取东财 000985 的当日值（与序列差约 3%），同一指标出现两个数；
        # 这里统一为代理口径（= 上证 + 深证 当日值），并在名称/approx 上明示，避免口径分裂。
        by_code = {r["code"]: r for r in rows_idx}
        sh_row, sz_row = by_code.get("sh000001"), by_code.get("sz399001")
        if sh_row and sz_row and sh_row["amount"] is not None and sz_row["amount"] is not None:
            for r in rows_wide:
                if r["code"] == "sh000985":
                    r["amount"] = round(sh_row["amount"] + sz_row["amount"], 2)
                    r["amount_date"] = d
                    r["note"] = ""
                    r["approx"] = True
        return rows_idx, rows_wide

    idx_rows, wide_rows = fetch_index_rows(date)

    # 微盘代理：第 11 格（前端宽基矩阵已不展示，但保留底层序列与数据）
    # 依赖实时全市场快照（市值后10%等权成交额），历史日期不得重算。
    micro_row = None
    if spot_df is not None:
        micro_amt, micro_n = compute.microcap_proxy_amount(spot_df)
        if micro_amt is None:
            log(f"微盘代理：样本不足（N={micro_n} < {compute.MICRO_MIN_UNIVERSE}），本日不写入")
            micro_row = _carry_row(existing, "micro_proxy")
        else:
            micro_row = {"name": "微盘代理(自建)", "code": "micro_proxy",
                         "amount": micro_amt, "amount_date": date, "note": "",
                         "change_pct": None, "amount_change": None,
                         "rank_1y": None, "pctile_all": None, "approx": False,
                         "universe_n": micro_n, "src": "spot"}
            log(f"微盘代理：市值后10%（N={micro_n}）等权日均成交 {micro_amt} 亿")
    else:
        micro_row = _carry_row(existing, "micro_proxy")
        log("微盘代理：历史日期不重算（沿用旧值或留空）")
    if micro_row is not None:
        wide_rows.append(micro_row)

    # ---- 加载上一交易日快照（用于「较昨日变化」与流动性数量变化）----
    prev_daily = None
    prev_date = _previous_trade_day(date, dates)
    if prev_date:
        prev_daily = _load_daily(prev_date)

    def _delta(cur, prev_v):
        """当前值与上一交易日值的差；任一侧缺失返回 None（不按 0 计）"""
        if cur is None or prev_v is None:
            return None
        return round(cur - prev_v, 2)

    if prev_daily:
        prev_idx = {}
        for r in (prev_daily.get("index_volume") or []) + (prev_daily.get("widebase") or []):
            prev_idx[r["code"]] = r
        for r in idx_rows + wide_rows:
            pr = prev_idx.get(r["code"]) or {}
            r["amount_change"] = _delta(r.get("amount"), pr.get("amount"))
            r["close_change"] = _delta(r.get("close"), pr.get("close"))

    # ---- 两融（T+1 发布，返回 (余额亿元, 实际统计日期)）----
    margin, margin_date = margin_mod.get_margin(date)

    # ---- 涨跌停（返回完整列表，按成交额门槛切分）----
    # 涨停池支持历史日期；跌停池（东财）只保留最近 30 天 → 历史日期拿不到就写 None，
    # 绝不写 0。两者分别用 lu_ok / ld_ok 区分「接口成功但 0 家」与「接口失败」。
    pools = zt_mod.fetch_pools(date, spot_df)
    limit_up, limit_down = pools["lu"], pools["ld"]
    lu_rows, ld_rows = pools["lu_rows"], pools["ld_rows"]
    if spot_df is None and not pools["lu_ok"] and not pools["ld_ok"]:
        # 历史日期且两个池都失败：沿用旧快照的涨跌停，否则置空（不写 0）
        old_ov = (existing or {}).get("overview") or {}
        if old_ov.get("limit_up") is not None or old_ov.get("limit_down") is not None:
            limit_up, limit_down = old_ov.get("limit_up"), old_ov.get("limit_down")
            log(f"涨跌停池不可用：{date} 沿用旧快照 {limit_up}/{limit_down}")
        else:
            limit_up = limit_down = None
            log(f"涨跌停池不可用：{date} 无旧值可沿用，置空（不写 0）")
    limit_pool_quality = {
        "limit_up_src": pools["lu_src"], "limit_up_ok": pools["lu_ok"],
        "limit_down_src": pools["ld_src"], "limit_down_ok": pools["ld_ok"],
        "limit_down_note": pools["ld_reason"],
    }

    # ---- 源优先级保护：降级口径不得覆盖此前直接取自东财池的有效值 ----
    # 真实案例：20261020 首次构建时东财跌停池成功（6 家）；几小时后重跑，池接口 SSLError，
    # 走「快照兜底判定」得 9 家。若直接写回序列，就是用低可信源覆盖了已核验值，
    # 且同一日期在序列与旧快照之间出现两个数。规则：新值可信度更低时保留旧值并留痕。
    old_q = ((existing or {}).get("data_quality") or {}).get("limit_pool") or {}
    old_emo = (existing or {}).get("emotion") or {}

    def _keep_previous(field: str, src_key: str, ok_key: str, got):
        """新值来自降级路径、而旧快照有东财直采值 → 返回旧值；否则原样返回 got"""
        if got is None or old_q.get(ok_key) is not True or old_emo.get(field) is None:
            return got
        log(f"{field} 本次为降级口径({limit_pool_quality[src_key]}) 得 {got}，"
            f"保留已有东财值 {old_emo[field]}，不覆盖")
        limit_pool_quality[ok_key] = True
        limit_pool_quality[src_key] = old_q.get(src_key)
        return old_emo[field]

    if not pools["lu_ok"]:
        kept = _keep_previous("limit_up", "limit_up_src", "limit_up_ok", limit_up)
        if kept != limit_up:
            limit_up = kept
            lu_rows = copy.deepcopy(old_emo.get("lu_over10e") or [])
    if not pools["ld_ok"]:
        kept = _keep_previous("limit_down", "limit_down_src", "limit_down_ok", limit_down)
        if kept != limit_down:
            limit_down = kept
            ld_rows = copy.deepcopy(old_emo.get("ld_over10e") or [])
            limit_pool_quality["limit_down_note"] = "kept_previous_eastmoney"

    lu_over10e = sorted((r for r in lu_rows if r["amount"] >= 10), key=lambda x: -x["amount"])[:30]
    ld_over10e = sorted((r for r in ld_rows if r["amount"] >= 10), key=lambda x: -x["amount"])[:30]
    # 门槛家数：数据不可得时必须是 None，不能因为 ld_rows 为空就算出 0 家
    lu_over5e_count = (sum(1 for r in lu_rows if r["amount"] >= 5)
                       if limit_up is not None else None)
    ld_over5e_count = (sum(1 for r in ld_rows if r["amount"] >= 5)
                       if limit_down is not None else None)
    if limit_down is None:
        ld_over10e = []

    # ---- 高活跃个股（当日成交额≥5亿 且 涨幅≥5%，供「上板与上涨」列表 + 导出）----
    active_stocks = []
    if spot_df is not None and {"amount", "change_pct", "close"}.issubset(spot_df.columns):
        lu_codes = {r["code"] for r in lu_rows}
        adf = spot_df.dropna(subset=["amount", "change_pct", "close"])
        adf = adf[(adf["amount"] >= 5e8) & (adf["change_pct"] >= 5)]
        adf = adf.sort_values("change_pct", ascending=False)
        for _, r in adf.iterrows():
            code = str(r["code"])
            active_stocks.append({
                "code": code, "name": str(r["name"]),
                "close": round(float(r["close"]), 2),
                "change_pct": round(float(r["change_pct"]), 2),
                "amount": round(float(r["amount"]) / 1e8, 2),
                "is_limit_up": code in lu_codes,
            })
    elif spot_df is None:
        # 历史日期：沿用旧快照中的列表（存在才写），不重新计算
        active_stocks = copy.deepcopy((existing or {}).get("active_stocks") or [])
        if active_stocks:
            log(f"高活跃个股：历史日期沿用旧快照 {len(active_stocks)} 只")
    log(f"高活跃个股（≥5亿且涨幅≥5%）：{len(active_stocks)} 只")

    # ---- 概览 / 流动性 / 集中度 ----
    total_amount = _resolve_total_amount(spot_df, idx_rows, date)
    if total_amount is None:
        total_amount = ((existing or {}).get("overview") or {}).get("total_amount")
        if total_amount is not None:
            log(f"两市成交额：{date} 指数口径不可用，沿用旧快照 {total_amount}")

    # 实时派生字段（集中度/家数/分档）：本次抓取 → 沿用旧值 → 明确不可用
    if spot_df is not None:
        spot_state, spot_note = SPOT_REALTIME, ""
        over_cnt, over_ratio, stock_count = compute.over_10e(spot_df)
        conc = compute.concentration(spot_df)
    else:
        spot_state, spot_note = _carried_spot_state(existing)
        if spot_state == SPOT_CARRIED:
            _ov = (existing or {}).get("overview") or {}
            over_cnt = _ov.get("over_10e_count")
            over_ratio = _ov.get("over_10e_ratio")
            stock_count = _ov.get("stock_count")
            conc = copy.deepcopy((existing or {}).get("concentration")) or None
            log(f"集中度/家数：{date} 沿用旧快照（over_10e={over_cnt}, N={stock_count}）")
        else:
            over_cnt = over_ratio = stock_count = None
            conc = None
            log(f"集中度/家数：{date} 无可靠历史来源，置空并标记 unavailable")
    # 个股集中度 Top10/Top20/Top50 累计占比较上一交易日变化（百分点差）
    if conc is not None:
        prev_conc = (prev_daily or {}).get("concentration") or {}
        conc["top10_change"] = _delta(conc.get("top10_total"), prev_conc.get("top10_total"))
        conc["top20_change"] = _delta(conc.get("top20_cum_pct"), prev_conc.get("top20_cum_pct"))
        conc["top50_change"] = _delta(conc.get("top50_cum_pct"), prev_conc.get("top50_cum_pct"))

    # ---- 行业板块（东财 → 同花顺，当日涨跌TOP10）----
    # 两个数据源都是**当日板块快照**（不接受历史日期），历史日期重建时不得调用。
    if realtime:
        industry = industry_mod.get_industry_daily(total_amount, date)
    else:
        industry = copy.deepcopy((existing or {}).get("industry"))
        log(f"行业板块：{date} 为历史日期，日快照接口不适用，"
            f"{'沿用旧值' if industry else '保持为空'}")
    if realtime and industry is None:
        # 两个数据源均失败：继承上一交易日有效数据，并标明真实数据日期（不伪装当日）
        prev = _previous_trade_day(date, dates)
        if prev:
            inherited = _load_industry_from_daily(prev)
            if inherited:
                inherited = dict(inherited)
                inherited["note"] = f"口径：继承自上一交易日 {prev}（当日数据源失败）"
                inherited["as_of"] = prev
                industry = inherited
                log(f"行业板块继承自上一交易日 {prev}")
        if industry is None:
            # 兜底第 2 层：模块缓存（最近一次成功抓取），即使无上一交易日快照也不置空
            cached, as_of = industry_mod.load_industry_cache()
            if cached:
                cached = dict(cached)
                cached["note"] = f"口径：数据源不可用，使用最近一次成功抓取的行业快照（{as_of or '日期未知'}）"
                cached["as_of"] = as_of
                cached["stale"] = True
                industry = cached
                log(f"行业板块启用缓存兜底（as_of={as_of}）")
        if industry is None:
            log(f"行业板块 {date} 获取失败且无前值/缓存可继承，置为空")

    overview = {
        "total_amount": total_amount,
        "total_amount_rank_year": None, "total_amount_rank_all": None,
        "total_amount_pctile_all": None,
        "margin_balance": margin, "margin_date": margin_date,
        "margin_rank_year": None, "margin_pctile_all": None,
        "limit_up": limit_up, "limit_down": limit_down,
        "over_10e_count": over_cnt, "over_10e_ratio": over_ratio,
        "stock_count": stock_count,
    }

    # ---- 序列维护（当日 + 可选回补窗口；重算后回填排名/百分位）----
    # 注：series_points / series_values 已在上方定义（指数降级需要提前读取序列）
    # 值为 None 时**不写序列**：缺失就是缺失，不能以 0 或旧值冒充当日真实值。
    if total_amount is not None:
        compute.update_series("total_amount", "两市成交额", "亿元", date, total_amount)
        pts = series_points("total_amount")
        vals = [p["value"] for p in pts]
        overview["total_amount_rank_all"] = compute.rank_of(vals, total_amount)
        overview["total_amount_pctile_all"] = compute.pctile(vals, total_amount)
        year_vals = [p["value"] for p in pts if p["date"].startswith(date[:4])]
        overview["total_amount_rank_year"] = compute.rank_of(year_vals, total_amount) if year_vals else None

    if margin is not None and margin_date is not None:
        # 按「实际统计日期」写入序列（两融 T+1，实际日期可能早于当日）
        compute.update_series("margin", "两融余额", "亿元", margin_date, margin)
        mvals = series_values("margin")
        overview["margin_rank_year"] = compute.rank_of(mvals, margin)
        overview["margin_pctile_all"] = compute.pctile(mvals, margin)

    if limit_up is not None:
        compute.update_series("limit_up_down", "涨停家数", "家", date, limit_up)
    if limit_down is not None:
        compute.update_series("limit_down", "跌停家数", "家", date, limit_down)
    if over_cnt is not None:
        compute.update_series("over_10e_count", "10亿以上家数", "家", date, over_cnt)
    if conc and conc.get("top10_total") is not None:
        # 头部抱团度序列（前10成交占比 %）
        compute.update_series("top10_concentration", "前10成交占比", "%",
                              date, conc["top10_total"])
    for r in idx_rows + wide_rows:
        if r["amount"] is None:
            continue
        # ETF 代理值与指数自身历史量级不可比，不写序列、不做历史排名/百分位
        if r.get("note") == "etf_proxy":
            continue
        key = f"index_amount_{r['code']}"
        # 仅当日真实抓取成功才写入序列；降级值（最近交易日）不写，避免污染历史口径
        if r.get("amount_date") == date and not r.get("note"):
            compute.update_series(key, r["name"], "亿元", date, r["amount"])
        svals = series_values(key)
        if r.get("rank_1y") is None:
            # 近一年排名 = 最近 244 个交易日窗口内的降序排位（与 series 内 rank_1y、
            # 前端 oneYearSampleN() 的 244 窗口口径一致；全历史排名另用 rank_all）
            r["rank_1y"] = compute.rank_of(svals[-244:], r["amount"])
        r["pctile_all"] = compute.pctile(svals, r["amount"])

    # ---- 指数观察（YTD + 本周/本月/年内均额 + 较昨日变化）----
    # idx_rows 与 wide_rows 可能包含同一指数（如科创50 同为主要指数与宽基成分），
    # 按 code 去重，避免 index_observation 出现重复行（前端 obsMap 虽按 code 覆盖，仍保持数据整洁）。
    index_observation = []
    _seen_obs = set()
    for r in idx_rows + wide_rows:
        if r["code"] in _seen_obs:
            continue
        _seen_obs.add(r["code"])
        index_observation.append({
            "code": r["code"], "name": r["name"],
            "ytd_pct": index_mod.get_index_ytd_pct(r["code"], date, dates),
            "avg_week_amount": compute.avg_index_amount(r["code"], date, dates, "week"),
            "avg_month_amount": compute.avg_index_amount(r["code"], date, dates, "month"),
            "avg_year_amount": compute.avg_index_amount(r["code"], date, dates, "year"),
        })
    prev_obs = {}
    if prev_daily:
        for o in prev_daily.get("index_observation") or []:
            prev_obs[o["code"]] = o
    for o in index_observation:
        po = prev_obs.get(o["code"])
        o["ytd_pct_change"] = _delta(o["ytd_pct"], po.get("ytd_pct")) if po else None
        o["avg_week_change"] = _delta(o["avg_week_amount"], po.get("avg_week_amount")) if po else None
        o["avg_month_change"] = _delta(o["avg_month_amount"], po.get("avg_month_amount")) if po else None
        o["avg_year_change"] = _delta(o["avg_year_amount"], po.get("avg_year_amount")) if po else None

    # ---- 行业周涨跌排名 ----
    industry_week_rank = industry_mod.get_industry_week_rank(date, dates)

    # ---- sparklines（近20日，供 M0 迷你折线）----
    def spark(key: str, n=20):
        import json
        p = os.path.join(DATA_DIR, "series", f"{key}.json")
        if not os.path.exists(p):
            return []
        with open(p, "r", encoding="utf-8") as f:
            pts = json.load(f).get("points", [])
        return [{"date": pt["date"], "value": pt["value"]} for pt in pts[-n:]]

    lud = spark("limit_up_down")
    # limit_up_down 序列只有涨停值；补充跌停序列（单独 key）
    if limit_down is not None:
        compute.update_series("limit_down", "跌停家数", "家", date, limit_down)
    lud_down = spark("limit_down")
    # 跌停序列存在真实缺口（东财跌停池只保留最近 30 天，历史日期无法回补），
    # 缺口必须保持为 None —— 前端画成断点，绝不按 0 补（0 家跌停是独立事实，不是缺失）。
    down_map = {p["date"]: p["value"] for p in lud_down}
    spark_lud = [{"date": p["date"], "up": p["value"], "down": down_map.get(p["date"])} for p in lud]

    # ---- 流动性结构：分档表「较昨日股票数量变化」+「百分比变化」----
    # 同一分档口径（成交额门槛/市值分档/区间边界）取上一交易日快照中的 count / pct，
    # 缺上一交易日 → *_change=None（前端显示「—」），绝不按 0 计。
    # 分档表本身依赖实时全市场快照：历史日期不重算，沿用旧快照或留空。
    def _attach_changes(buckets, prev_buckets):
        pmap = {b["label"]: b for b in (prev_buckets or [])}
        for b in buckets:
            p = pmap.get(b["label"])
            b["count_change"] = (b["count"] - p["count"]) if p and p.get("count") is not None else None
            b["pct_change"] = _delta(b.get("pct"), p.get("pct")) if p else None
        return buckets

    if spot_df is not None:
        prev_liq = (prev_daily or {}).get("liquidity") or {}
        amount_buckets = _attach_changes(
            compute.amount_buckets(spot_df), prev_liq.get("amount_buckets"))
        o10e_mc_buckets = _attach_changes(
            compute.over_10e_marketcap_buckets(spot_df), prev_liq.get("over_10e_marketcap_buckets"))
        o10e_mc_value_buckets = _attach_changes(
            compute.over_10e_marketcap_value_buckets(spot_df), prev_liq.get("over_10e_marketcap_value_buckets"))
        mktcap_buckets = _attach_changes(
            compute.mktcap_buckets(spot_df), prev_liq.get("mktcap_buckets"))
        liquidity = {
            "over_10e_count": over_cnt, "over_10e_ratio": over_ratio,
            "pctile_count": (compute.pctile(series_values("over_10e_count"), over_cnt)
                             if over_cnt is not None else None),
            "mktcap_buckets": mktcap_buckets,
            "amount_buckets": amount_buckets,
            "over_10e_marketcap_buckets": o10e_mc_buckets,
            "over_10e_marketcap_value_buckets": o10e_mc_value_buckets,
        }
    elif spot_state == SPOT_CARRIED:
        liquidity = copy.deepcopy((existing or {}).get("liquidity")) or _empty_liquidity()
    else:
        liquidity = _empty_liquidity()

    def _ratio(num, den, digits=2):
        """比率：任一侧缺失即 None（不写 0，避免把「未知」伪装成「0%」）"""
        if num is None or not den:
            return None
        return round(num / den * 100, digits)

    daily = {
        "trade_date": date,
        "overview": overview,
        "index_volume": idx_rows,
        "widebase": wide_rows,
        "index_observation": index_observation,
        "industry": industry,
        "industry_week_rank": industry_week_rank,
        "concentration": conc if conc is not None else _empty_concentration(),
        "liquidity": liquidity,
        "emotion": {
            "limit_up": limit_up, "limit_down": limit_down,
            "lu_pctile": (compute.pctile(series_values("limit_up_down"), limit_up)
                          if limit_up is not None else None),
            "ld_pctile": (compute.pctile(series_values("limit_down"), limit_down)
                          if limit_down is not None else None),
            "lu_ratio_of_total": _ratio(limit_up, stock_count),
            "ld_ratio_of_total": _ratio(limit_down, stock_count),
            "lu_ratio_of_over10e": (_ratio(len(lu_over10e), over_cnt, 1)
                                    if limit_up is not None else None),
            "ld_ratio_of_over10e": (_ratio(len(ld_over10e), over_cnt, 1)
                                    if limit_down is not None else None),
            "lu_over5e_count": lu_over5e_count, "ld_over5e_count": ld_over5e_count,
            "lu_over10e": lu_over10e, "ld_over10e": ld_over10e,
        },
        "active_stocks": active_stocks,
        # 数据质量标记：标明本快照的「实时全市场行情」部分来自 实时抓取 / 沿用旧值 / 不可用
        "data_quality": {
            "spot_derived": spot_state,
            "note": spot_note,
            "generated_at": now_iso(),          # 北京时间 ISO8601（+08:00）
            "business_date": date,              # 行情所属交易日（标识，不做时区换算）
            "date_rule": "asia_shanghai",
            "limit_pool": limit_pool_quality,
        },
        "sparklines": {
            "total_amount": spark("total_amount"),
            "margin": spark("margin"),
            "limit_up_down": spark_lud,
            "over_10e_count": spark("over_10e_count"),
        },
    }
    if conc is not None and conc.get("top10_total") is not None:
        daily["concentration"]["top10_total_pctile_hist"] = compute.pctile(
            _top10_hist_pctile_vals(), conc["top10_total"])

    # 市值分档序列（堆叠面积图用，滚动保留 400 点）：无分档数据时不写空点
    if liquidity.get("mktcap_buckets"):
        compute.append_bucket_series(date, liquidity["mktcap_buckets"])
    # 指数月/年均值预聚合表（四档切换单请求）
    compute.build_index_agg()

    atomic_write_json(os.path.join(DATA_DIR, "daily", f"{date}.json"), daily)

    # ---- 元数据 ----
    atomic_write_json(os.path.join(DATA_DIR, "latest.json"),
                      {"latest": date, "updated_at": now_iso()})
    atomic_write_json(os.path.join(DATA_DIR, "meta", "trading_days.json"),
                      {"list": dates, "latest": date, "updated_at": now_iso(),
                       "source_versions": _source_versions()})
    log(f"===== {date} 构建完成 =====")


def _top10_hist_pctile_vals():
    """历史 top10 占比序列（简化：若 daily 目录有历史文件则读取，否则空样本 → pctile=None）"""
    import json
    out = []
    ddir = os.path.join(DATA_DIR, "daily")
    if os.path.isdir(ddir):
        for fn in sorted(os.listdir(ddir)):
            if not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(ddir, fn), "r", encoding="utf-8") as f:
                    d = json.load(f)
                s = sum(x["pct_of_total"] for x in d.get("concentration", {}).get("top10", []))
                if s:
                    out.append(s)
            except Exception:  # noqa: BLE001
                continue
    return out


def _source_versions() -> dict:
    versions = {}
    try:
        import akshare
        versions["akshare"] = akshare.__version__
    except Exception:  # noqa: BLE001
        versions["akshare"] = "unknown"
    try:
        import baostock
        versions["baostock"] = getattr(baostock, "__version__", "ok")
    except Exception:  # noqa: BLE001
        versions["baostock"] = "not-installed"
    try:
        import tushare
        versions["tushare"] = tushare.__version__
    except Exception:  # noqa: BLE001
        versions["tushare"] = "not-installed"
    return versions


def main():
    ap = argparse.ArgumentParser(description="复盘台数据构建")
    ap.add_argument("--date", help="指定交易日 YYYYMMDD（单日快照模式）")
    ap.add_argument("--incremental", action="store_true", help="增量模式：自动取最近已收盘交易日")
    ap.add_argument("--backfill-days", type=int, default=0, help="本地回补最近 N 个交易日（勿在 CI 使用）")
    ap.add_argument("--days", type=int, default=1,
                    help="构建最近 N 个交易日的快照（默认 1；历史日自动禁用实时 spot）")
    ap.add_argument("--industry-backfill", metavar="CSV",
                    help="申万行业历史回填：提供对齐表 CSV（列：east_name,sw_code,sw_name），仅本地使用")
    args = ap.parse_args()

    dates = calendar_mod.get_trade_dates()

    if args.industry_backfill:
        from modules import industry_mod
        target0 = last_closed_trade_date(dates)
        i = dates.index(target0)
        industry_mod.backfill_industry(args.industry_backfill,
                                       dates[max(0, i - 249)], target0)
        return

    if args.date:
        target = args.date
        if target not in dates:
            raise RuntimeError(f"{target} 不是交易日")
    else:
        # 未指定 --date 时统一取「最近已收盘交易日」：--incremental / --days N / 无参 共用同一口径，
        # 避免把盘中（15:05 前）的未完成行情写成当日快照。
        target = last_closed_trade_date(dates)

    days = [target]
    if args.backfill_days > 0:
        # 历史回补只在本地跑：序列层回补（成交额=沪+深指数代理、两融、涨跌停、指数成交额）
        # 当日全市场快照仅实时可得，over_10e/市值分档/集中度无法历史回补，自启用日起累积
        from modules import backfill
        i = dates.index(target)
        window = dates[max(0, i - args.backfill_days + 1): i + 1]
        backfill.backfill_series(window, dates)
        return

    if args.days > 1:
        i = dates.index(target)
        days = dates[max(0, i - args.days + 1): i + 1]
    elif args.incremental and not args.date:
        # 增量模式自动补齐「最近连续缺失」的交易日（最多回溯 5 个），
        # 避免某天整体失败后留下永久空洞（补出来的历史日不会抓实时 spot，
        # 只写按日期可得的可靠源，并把 spot_derived 标记为 unavailable）。
        i = dates.index(target)
        back = []
        for d in reversed(dates[max(0, i - 4):i]):
            if os.path.exists(os.path.join(DATA_DIR, "daily", f"{d}.json")):
                break
            back.append(d)
        if back:
            days = sorted(back) + [target]
            log(f"增量模式检测到 {len(back)} 个缺失交易日，一并补齐：{days}")

    # 涨跌停自愈：东财跌停池只保留最近 30 天，一旦某日漏采就永久丢失，
    # 因此每次增量都补采最近窗口内「只有涨停没有跌停」的日期（只补缺口，不重抓已有值）。
    try:
        from modules import backfill
        backfill.heal_recent_limit_pools(dates, target)
    except Exception as e:  # noqa: BLE001
        log(f"涨跌停窗口自愈跳过（{type(e).__name__}: {e}）")

    failed = 0
    for d in days:
        try:
            build_one(d, dates, args.backfill_days)
        except Exception as e:  # noqa: BLE001
            failed += 1
            record_error(f"日期 {d} 构建失败: {e}")
            notify.notify_failure("复盘台数据更新失败", f"日期 {d} 构建失败: {e}")
            log(f"日期 {d} 构建失败（已保留旧数据）：{e}")
            if failed >= 2:
                log("连续失败 2 次，终止本次构建")
                break
    if failed == 0:
        log("全部日期构建成功")
    else:
        log(f"{failed} 个日期失败，详情见 data/meta/last_error.log")


def run() -> int:
    """进程入口（__main__ 与测试共用）。

    FATAL 也遵守同一套容错约定：保留旧数据、记录 last_error.log、
    推送失败通知（notify.notify_failure）、返回 0（网站仍显示上一交易日数据）。"""
    try:
        main()
    except Exception as e:  # noqa: BLE001
        record_error(f"FATAL: {e}\n{traceback.format_exc()}")
        notify.notify_failure("复盘台数据更新失败（FATAL）", str(e))
        log(f"构建失败（已保留旧数据）：{e}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
