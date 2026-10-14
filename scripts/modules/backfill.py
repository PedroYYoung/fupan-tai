# -*- coding: utf-8 -*-
"""序列层历史回补（云端/本地皆可跑）

设计要点：
- 指数成交额序列：一次性按区间拉取（与窗口大小无关），批量合并写入
- 两融 / 涨跌停池：逐日拉取（窗口内的日期），批量合并写入
- over_10e / 市值分档 / 前10集中度依赖当日全市场快照，不可历史回补（每日增量累积）

数据源（多源回退，缺一不可）：东财 AKShare → 中证指数官网 → baostock。
注意：东财在 GitHub Actions runner 上同样被反爬封锁（并非「云端无限制」），
因此指数历史成交额以 中证官网/baostock 作为 CI 下的实际主力源。
"""
from .common import log
from . import compute, index_mod, margin_mod, zt_mod


def _index_amount_df(market: str, start: str, end: str) -> dict:
    """沪/深指数代理日成交额 {date: 成交额亿}（多源回退：东财 → 中证官网 → baostock）"""
    code = "sh000001" if market == "sh" else "sz399001"
    return index_mod.get_index_amount_history(code, start, end)


def backfill_series(window: list, dates: list):
    """window: 升序 YYYYMMDD 列表；指数/总额按全历史区间拉取，两融/涨跌停仅回补窗口内"""
    target = dates[-1]
    start_all = "20150101"  # 指数序列全历史回补
    log(f"===== 序列回补：窗口 {window[0]} ~ {window[-1]}（{len(window)} 天）；指数全历史 =====")

    # 1) 指数/宽基成交额（全部 14 个代码；多源回退：东财 → baostock → 中证官网）
    for code, name in index_mod.INDEX_CODES.items():
        try:
            vals = index_mod.get_index_amount_history(code, start_all, target)
            if not vals:
                log(f"{code} {name}: 所有历史源均无数据，跳过（保留旧数据）")
                continue
            compute.write_series_merge(f"index_amount_{code}", name, "亿元", vals)
            log(f"{code} {name}: 合并 {len(vals)} 点")
        except Exception as e:  # noqa: BLE001
            log(f"{code} 回补失败：{e}")

    # 2) 两市成交额 = 沪 + 深（指数代理口径）+ 全A代理
    try:
        sh = _index_amount_df("sh", start_all, target)
        sz = _index_amount_df("sz", start_all, target)
        total = {d: round(sh[d] + sz[d], 2) for d in sh if d in sz}
        compute.write_series_merge("total_amount", "两市成交额", "亿元", total)
        compute.write_series_merge("index_amount_sh000985", "中证全指(沪深合计代理)", "亿元", total)
        log(f"两市成交额：合并 {len(total)} 点")
    except Exception as e:  # noqa: BLE001
        log(f"两市成交额回补失败：{e}")

    # 3) 两融 + 涨跌停（逐日，窗口内）
    margin_vals, lu_vals, ld_vals = {}, {}, {}
    for i, d in enumerate(window):
        if (i + 1) % 50 == 0:
            log(f"逐日回补进度 {i + 1}/{len(window)}")
        m = margin_mod.get_margin(d)
        if m is not None:
            margin_vals[d] = m
        try:
            lu, ld, _, _ = zt_mod.get_limit_pools(d)
            lu_vals[d] = lu
            ld_vals[d] = ld
        except Exception as e:  # noqa: BLE001
            log(f"{d} 涨跌停回补失败：{e}")
    if margin_vals:
        compute.write_series_merge("margin", "两融余额", "亿元", margin_vals)
    if lu_vals:
        compute.write_series_merge("limit_up_down", "涨停家数", "家", lu_vals)
    if ld_vals:
        compute.write_series_merge("limit_down", "跌停家数", "家", ld_vals)

    log("===== 序列回补完成（over_10e/市值分档/集中度无法历史回补，自启用日起累积）=====")
