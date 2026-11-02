#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""补算流动性分档表的「较上一有效交易日变化」字段。

背景：2026-10-19 作为历史日被重建，由于没有 existing 快照可沿用，
其 liquidity 分档表被写入空列表。这导致 2026-10-20（实时日）无法基于
上一交易日计算 count_change / pct_change，流动性结构页面括号内变化消失。

本脚本不重新采集行情，仅基于已有 daily 快照向前回溯最近一个仍保留
分档表的交易快照，补算目标日期的变化字段。若任一分档缺失或回溯不到
有效基准，则保留 null（前端显示「—」），绝不填 0。
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from modules import calendar_mod, common

def _load_daily(date: str):
    p = os.path.join(common.DATA_DIR, "daily", f"{date}.json")
    if not os.path.exists(p):
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_daily(date: str, obj: dict):
    p = os.path.join(common.DATA_DIR, "daily", f"{date}.json")
    common.atomic_write_json(p, obj)


def _delta(cur, prev):
    if cur is None or prev is None:
        return None
    return round(cur - prev, 2)


def _prev_buckets(date: str, key: str, dates: list) -> list | None:
    """从 date 向前回溯，返回最近一个非空 liquidity[key] 分档表。"""
    if date not in dates:
        return None
    i = dates.index(date)
    for k in range(i - 1, -1, -1):
        prev = _load_daily(dates[k])
        if not prev:
            continue
        buckets = ((prev.get("liquidity") or {}).get(key) or [])
        if buckets:
            return buckets
    return None


def _attach_changes(buckets: list, prev_buckets: list | None) -> list:
    pmap = {b["label"]: b for b in (prev_buckets or [])}
    for b in buckets:
        p = pmap.get(b["label"])
        b["count_change"] = (b["count"] - p["count"]) if p and p.get("count") is not None else None
        b["pct_change"] = _delta(b.get("pct"), p.get("pct")) if p else None
    return buckets


def repair(date: str):
    dates = calendar_mod.get_trade_dates()
    snap = _load_daily(date)
    if not snap:
        raise RuntimeError(f"{date} 快照不存在")
    liq = snap.get("liquidity") or {}
    changed = False
    for key in ("mktcap_buckets", "amount_buckets",
                "over_10e_marketcap_buckets", "over_10e_marketcap_value_buckets"):
        buckets = liq.get(key)
        if not buckets:
            continue
        # 如果已经存在有效的 count_change，则跳过
        if any(b.get("count_change") is not None for b in buckets):
            continue
        prev = _prev_buckets(date, key, dates)
        if not prev:
            common.log(f"{date} {key}: 向前回溯不到有效基准，变化字段保持 null")
            _attach_changes(buckets, None)  # 显式写入 null，避免键缺失
            changed = True
            continue
        _attach_changes(buckets, prev)
        common.log(f"{date} {key}: 基于更早交易日补算变化字段")
        changed = True
    if changed:
        _save_daily(date, snap)
        common.log(f"{date} 流动性变化字段补算完成")
    else:
        common.log(f"{date} 无需补算")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "20261020"
    repair(target)
