#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重建快照内的 sparklines（重点是涨跌停：缺口日必须为 null，历史上被写成 0）。

为什么需要：`build.py` 早期版本用 `down_map.get(date, 0)` 组装涨跌停迷你折线，
把「没有跌停数据」画成「0 家跌停」，会在情绪曲线上凭空造出「跌停归零」的假信号。
代码已改，但历史快照里的 sparklines 仍是旧结果，这里按序列重建一次。

幂等：结果只取决于 series 文件，重复执行无变化。
用法：python scripts/repair_limit_pool_spark.py [--dry-run]
"""
import argparse
import glob
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.common import DATA_DIR, atomic_write_json, log  # noqa: E402

N = 20


def _tail(key):
    p = os.path.join(DATA_DIR, "series", f"{key}.json")
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        pts = json.load(f).get("points", [])
    return [{"date": x["date"], "value": x["value"]} for x in pts if x.get("value") is not None][-N:]


def rebuild(dry_run=False):
    lu = _tail("limit_up_down")
    ld = {p["date"]: p["value"] for p in _tail("limit_down")}
    others = {k: _tail(k) for k in ("total_amount", "margin", "over_10e_count")}
    spark_ud = [{"date": p["date"], "up": p["value"], "down": ld.get(p["date"])} for p in lu]

    touched, changed_pts = [], 0
    for path in sorted(glob.glob(os.path.join(DATA_DIR, "daily", "*.json"))):
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        sp = d.get("sparklines") or {}
        before = json.dumps(sp, sort_keys=True)
        new_sp = {
            "total_amount": others["total_amount"],
            "margin": others["margin"],
            "limit_up_down": spark_ud,
            "over_10e_count": others["over_10e_count"],
        }
        d["sparklines"] = new_sp
        if json.dumps(new_sp, sort_keys=True) == before:
            continue
        # 统计被纠正为 null 的跌停点
        old_zero = [p for p in sp.get("limit_up_down") or []
                    if p.get("down") == 0 and ld.get(p["date"]) is None]
        changed_pts += len(old_zero)
        touched.append(os.path.basename(path))
        if not dry_run:
            atomic_write_json(path, d)
    log(f"sparklines 重建：{len(touched)} 份快照{'（dry-run 未写盘）' if dry_run else ''}，"
        f"其中 {changed_pts} 个「缺数据被写成 0」的跌停点已改为 null")
    return touched


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    rebuild(args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
