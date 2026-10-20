#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清除「示例数据残留」——把 make_sample_data.py 合成的假历史从真实序列里剔除。

背景（证据链）
--------------
`scripts/make_sample_data.py`（早期演示数据生成器，`random.seed(20260925)`，区间
20200102~20260925）会直接写入 `public/data/series/*.json`。其中 4 条序列至今仍混有
合成点，与真实采集值拼在同一条线上，造成「口径断层」：

  · index_amount_micro_proxy ：2020-01-02~2026-09-24 全部为合成值（基准 130 亿元/只 + AR 随机游走），
    真实值约 0.46 亿元/只 → 相差约 280 倍，且与两市成交额相关系数仅 0.02（真实指标不可能如此）。
  · index_amount_bj899050    ：同区间全部为合成值（北证50 指数 2022-11-21 才发布，2020~2022 客观不存在）。
  · index_amount_sh000688    ：2026 年内（0105~0924）178 个点为合成值，2020-2025 为真实回补值。
  · index_amount_sh932000    ：同上（中证2000 指数 2023-08 才发布）。

判定方法：用同一 seed 重跑旧版生成器，与现有文件**逐值精确比对**（2 位小数全等），
命中率 1633/1637 与 178/178，远非巧合。本脚本把上述区间的合成点删除，
只保留真实点，并重算排名/百分位（样本 n<30 时排名置空，不做无意义的百分位）。

可重复执行（幂等）：已删除的区间再跑一次不会有任何变化。

用法：
  python scripts/repair_demo_residue.py --dry-run     # 只报告
  python scripts/repair_demo_residue.py               # 执行
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.common import DATA_DIR, atomic_write_json, log, now_iso  # noqa: E402
from modules import compute  # noqa: E402

MIN_RANK_SAMPLE = 30

# 已确认的合成区间（含首尾）。删除后不再重建，缺口如实保留。
DEMO_RANGES = {
    "index_amount_micro_proxy": ("20200102", "20260924"),
    "index_amount_bj899050": ("20200102", "20260924"),
    "index_amount_sh000688": ("20260105", "20260924"),
    "index_amount_sh932000": ("20260105", "20260924"),
}

SERIES_NOTE = {
    "index_amount_micro_proxy": (
        "自建微盘代理＝全A按总市值升序后10%的等权平均成交额（亿元/只），仅自 20261014 起有真实采集；"
        "此前无可靠历史源，已移除全部示例数据，不做平滑、不做回填。"),
    "index_amount_bj899050": (
        "北证50指数成交额：该指数 2022-11-21 才发布，2020~2022 无真实数据；"
        "早期历史为示例数据，已全部移除，仅保留真实采集点。"),
    "index_amount_sh000688": (
        "科创50指数成交额：2020-2025 为真实回补值；2026 年内（0105~0924）早期被示例数据覆盖，"
        "已移除并保留缺口（东财/中证官网/baostock 在本次修复时均不可达，不做伪造）。"),
    "index_amount_sh932000": (
        "中证2000指数成交额：2015-2025 为真实回补值；2026 年内（0105~0924）早期被示例数据覆盖，"
        "已移除并保留缺口（同上，不做伪造）。"),
}


def _load(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _recompute(points):
    """按剩余点重算排名/百分位；样本 < MIN_RANK_SAMPLE 时置空（百分位没有统计意义）"""
    pts = sorted((p for p in points if p.get("value") is not None), key=lambda p: p["date"])
    vals = [p["value"] for p in pts]
    dates = [p["date"] for p in pts]
    n = len(pts)
    for i, p in enumerate(pts):
        if n < MIN_RANK_SAMPLE:
            p["rank_all"] = None
            p["pctile"] = None
            p["rank_year"] = None
            p["rank_1y"] = None
            continue
        v = p["value"]
        p["rank_all"] = compute.rank_of(vals, v)
        p["pctile"] = compute.pctile(vals, v)
        year_vals = [v2 for v2, d in zip(vals, dates) if d.startswith(p["date"][:4])]
        p["rank_year"] = compute.rank_of(year_vals, v) if year_vals else None
        lo = max(0, i - 243)
        p["rank_1y"] = compute.rank_of(vals[lo:i + 1], v)
    return pts


def repair_series(dry_run: bool) -> dict:
    report = {}
    for key, (lo, hi) in DEMO_RANGES.items():
        path = os.path.join(DATA_DIR, "series", f"{key}.json")
        if not os.path.exists(path):
            log(f"{key}: 文件不存在，跳过")
            continue
        obj = _load(path)
        pts = obj.get("points", [])
        keep = [p for p in pts if not (lo <= p["date"] <= hi)]
        dropped = len(pts) - len(keep)
        report[key] = {"before": len(pts), "dropped": dropped, "after": len(keep),
                       "coverage_start": keep[0]["date"] if keep else None,
                       "coverage_end": keep[-1]["date"] if keep else None}
        log(f"{key}: {len(pts)} → {len(keep)} 点（移除合成区间 {lo}~{hi} 共 {dropped} 点）")
        if dry_run or dropped == 0:
            continue
        new_pts = _recompute(keep)
        out = dict(obj)
        out["points"] = new_pts
        out["updated_at"] = now_iso()
        out["coverage_start"] = new_pts[0]["date"] if new_pts else None
        out["coverage_end"] = new_pts[-1]["date"] if new_pts else None
        out["sample_n"] = len(new_pts)
        out["source"] = "real_collected"
        out["note"] = SERIES_NOTE.get(key, "")
        out["demo_removed"] = {"range": [lo, hi], "count": dropped,
                               "reason": "make_sample_data.py 合成的示例数据"}
        atomic_write_json(path, out)
    return report


def _snapshot_rank_from_series():
    """用修复后的序列刷新快照里受影响的 rank/pctile 与周期均额"""
    series = {}
    for key in DEMO_RANGES:
        p = os.path.join(DATA_DIR, "series", f"{key}.json")
        if os.path.exists(p):
            series[key[13:]] = _load(p)["points"]

    ddir = os.path.join(DATA_DIR, "daily")
    touched = []
    if not os.path.isdir(ddir):
        return touched
    with open(os.path.join(DATA_DIR, "meta", "trading_days.json"), encoding="utf-8") as f:
        dates = json.load(f)["list"]
    for fn in sorted(os.listdir(ddir)):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(ddir, fn)
        d = _load(path)
        date = d.get("trade_date") or fn[:8]
        changed = False
        for section in ("index_volume", "widebase"):
            for row in d.get(section) or []:
                pts = series.get(row.get("code"))
                if not pts:
                    continue
                vals = [p["value"] for p in pts if p.get("value") is not None]
                if len(vals) < MIN_RANK_SAMPLE:
                    row["rank_1y"] = None
                    row["pctile_all"] = None
                elif row.get("amount") is not None:
                    row["rank_1y"] = compute.rank_of(vals[-244:], row["amount"])
                    row["pctile_all"] = compute.pctile(vals, row["amount"])
                changed = True
        for obs in d.get("index_observation") or []:
            code = obs.get("code")
            if code not in series:
                continue
            for period, field, chg in (("week", "avg_week_amount", "avg_week_change"),
                                       ("month", "avg_month_amount", "avg_month_change"),
                                       ("year", "avg_year_amount", "avg_year_change")):
                obs[field] = compute.avg_index_amount(code, date, dates, period)
                if obs[field] is None:
                    obs[chg] = None     # 基准值缺失时变化量必须为 None，不能留旧差值
            changed = True
        if changed:
            atomic_write_json(path, d)
            touched.append(fn)

    # 第二轮：按「上一交易日快照」重算 *_change（第一轮写盘后，前一日的值已是修复后的值）
    for fn in touched:
        path = os.path.join(ddir, fn)
        d = _load(path)
        date = d.get("trade_date") or fn[:8]
        if date not in dates:
            continue
        i = dates.index(date)
        if i == 0:
            continue
        prev_path = os.path.join(ddir, f"{dates[i - 1]}.json")
        if not os.path.exists(prev_path):
            continue
        prev_obs = {o["code"]: o for o in (_load(prev_path).get("index_observation") or [])}
        for obs in d.get("index_observation") or []:
            po = prev_obs.get(obs.get("code"))
            for field, chg in (("avg_week_amount", "avg_week_change"),
                               ("avg_month_amount", "avg_month_change"),
                               ("avg_year_amount", "avg_year_change"),
                               ("ytd_pct", "ytd_pct_change")):
                cur, prev = obs.get(field), (po or {}).get(field)
                obs[chg] = None if (cur is None or prev is None) else round(cur - prev, 2)
        atomic_write_json(path, d)
    return touched


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    log("===== 示例数据残留清理 =====")
    rep = repair_series(args.dry_run)
    if args.dry_run:
        log(f"dry-run 汇总：{json.dumps(rep, ensure_ascii=False)}")
        return 0

    touched = _snapshot_rank_from_series()
    log(f"快照 rank/均额刷新：{len(touched)} 份 {touched}")
    compute.build_index_agg()
    log("index_agg 已按修复后序列重建")
    log(f"汇总：{json.dumps(rep, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
