# -*- coding: utf-8 -*-
"""把 index_amount_sh000985 统一为「沪深合计代理」口径（幂等）。

背景
----
中证全指（sh000985）没有可用的全历史成交额源：东财只覆盖近年、baostock 不提供、
中证官网亦无稳定接口。项目一直用 total_amount（上证指数 + 深证成指 成交额合计）
作为该序列的代理值写入——7217 个点里 7214 个与 total_amount 完全相同，
仅最近 3 个点混入了东财 000985 的当日真实值（约差 3.7%）。

同一序列混两种口径会制造看不见的断层（本项目此前正是被「示例数据 + 真实值」
拼接坑过），因此：统一回代理口径，并把口径写进序列元信息；
快照层（scripts/build.py fetch_index_rows）同步改为同一口径，名称标注代理。

运行：python scripts/repair_sh000985_proxy.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules import compute  # noqa: E402
from modules.common import DATA_DIR, atomic_write_json, log  # noqa: E402

KEY = "index_amount_sh000985"
NAME = "中证全指(沪深合计代理)"


def main():
    p = os.path.join(DATA_DIR, "series", f"{KEY}.json")
    tp = os.path.join(DATA_DIR, "series", "total_amount.json")
    if not os.path.exists(tp):
        log("total_amount 序列不存在，无法归一（保持原样）")
        return

    with open(tp, encoding="utf-8") as f:
        total = {pt["date"]: pt["value"] for pt in json.load(f).get("points", [])
                 if pt.get("value") is not None}
    old = {}
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            old = {pt["date"]: pt["value"] for pt in json.load(f).get("points", [])
                   if pt.get("value") is not None}

    diff = {d: (old[d], total[d]) for d in old if d in total and abs(old[d] - total[d]) > 0.01}
    log(f"{KEY}：现有 {len(old)} 点，其中与 total_amount 不一致 {len(diff)} 点")
    for d in sorted(diff):
        log(f"  {d}: {diff[d][0]} → {diff[d][1]}（统一为沪深合计代理口径）")

    compute.write_series_merge(
        KEY, NAME, "亿元", total,
        meta={
            "source": "proxy_sh_sz",
            "proxy": True,
            "proxy_of": "total_amount",
            "coverage_start": min(total) if total else None,
            "coverage_end": max(total) if total else None,
            "sample_n": len(total),
            "note": "中证全指(sh000985)无稳定全历史源：本序列＝上证指数+深证成指成交额合计"
                    "（沪深两市代理口径），与中证全指成分股口径量级相近但不等价，"
                    "故名称与 approx 标记均写明「沪深合计代理」，不与真实中证全指混用。",
        })

    fix_snapshots(total)
    log("完成：序列与快照口径已统一为「沪深合计代理」")


def fix_snapshots(total: dict):
    """快照层（widebase 中的 sh000985 行）同步为代理口径。

    序列改了但快照不改，前端「指数矩阵（当日）」与「趋势图（序列）」就会给出两个数
    ——正是本轮要消除的口径分裂。amount_change（绝对值差）按上一份快照重算，
    rank_1y / pctile_all 按新序列（等值于 total_amount）重算。
    """
    import glob

    from modules import compute

    files = sorted(glob.glob(os.path.join(DATA_DIR, "daily", "*.json")))
    if not files:
        return
    keys = sorted(total)
    prev = None
    changed = 0
    for fp in files:
        d = os.path.basename(fp)[:-5]
        with open(fp, encoding="utf-8") as f:
            snap = json.load(f)
        row = next((r for r in (snap.get("widebase") or []) if r.get("code") == "sh000985"), None)
        if row is None:
            prev = None
            continue
        if d in total:
            new = total[d]
            if row.get("amount") != new:
                log(f"  快照 {d}: sh000985 {row.get('amount')} → {new}")
                changed += 1
            row["amount"] = new
            row["amount_date"] = d
            row["note"] = ""
            row["name"] = NAME
            row["approx"] = True
            row["amount_change"] = (round(new - prev, 2)
                                    if prev is not None and new is not None else None)
            hist = [total[k] for k in keys if k <= d]
            row["pctile_all"] = compute.pctile(hist, new)
            row["rank_1y"] = compute.rank_of(hist[-244:], new)
            atomic_write_json(fp, snap)
            prev = new
        else:
            prev = row.get("amount")
    log(f"快照层：{len(files)} 份检查完毕，{changed} 份 sh000985 行改为代理口径")


if __name__ == "__main__":
    main()
