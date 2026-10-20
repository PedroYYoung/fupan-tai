# -*- coding: utf-8 -*-
"""序列/快照完整性收尾修补（幂等）。

处理三件事：

1. **非交易日点清理**：序列里若出现非交易日（例：20261010 是周六，曾被
   `--date` 手动跑过一次，东财对非交易日返回「0 家」且接口不报错），
   这类点既不是行情也不是缺口，属于污染点，直接删除并重算排名/百分位。
   （「接口成功但 0 家」必须靠交易日校验挡掉，不能靠值域判断。）

2. **两市成交额口径归一**：total_amount 应恒等于 上证指数 + 深证成指 成交额。
   实测有 2 天（20261015/20261016）因写入时点不同产生 0.02% 尾差，
   这里按 sh + sz 全历史重算，保证口径唯一；sh000985（沪深合计代理）同步。

3. **旧快照结构补齐**：20260928 缺 data_quality/active_stocks、20261009/20261013
   缺 active_stocks，会让前端「数据质量」与「高活跃个股」两处读不到字段。
   补齐空结构，data_quality 不编造生成时间（generated_at=null + note 说明）。

运行：python scripts/repair_series_sanity.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules import calendar_mod, compute  # noqa: E402
from modules.common import DATA_DIR, atomic_write_json, log  # noqa: E402

SERIES = os.path.join(DATA_DIR, "series")
DAILY = os.path.join(DATA_DIR, "daily")


def _recompute(points):
    """按 (date, value) 重算 rank_all / pctile / rank_year / rank_1y（与 compute 同口径）"""
    vals = [p["value"] for p in points]
    dates = [p["date"] for p in points]
    for i, p in enumerate(points):
        v = p["value"]
        p["rank_all"] = compute.rank_of(vals, v)
        p["pctile"] = compute.pctile(vals, v)
        year_vals = [q["value"] for q, d in zip(points, dates) if d.startswith(p["date"][:4])]
        p["rank_year"] = compute.rank_of(year_vals, v) if year_vals else None
        lo = max(0, i - 243)
        p["rank_1y"] = compute.rank_of(vals[lo:i + 1], v)
    return points


def drop_nontrading(dates_set):
    removed = 0
    for f in sorted(os.listdir(SERIES)):
        if not f.endswith(".json"):
            continue
        p = os.path.join(SERIES, f)
        with open(p, encoding="utf-8") as fh:
            obj = json.load(fh)
        pts = obj.get("points") or []
        keep = [pt for pt in pts if pt["date"] in dates_set]
        bad = [(pt["date"], pt.get("value")) for pt in pts if pt["date"] not in dates_set]
        if not bad:
            continue
        log(f"{f}: 删除非交易日点 {bad}")
        removed += len(bad)
        obj["points"] = _recompute(keep)
        atomic_write_json(p, obj)
    log(f"非交易日点清理完成：共删除 {removed} 个")


def normalize_total():
    """total_amount = 上证指数 + 深证成指（全历史同口径），sh000985 同步"""
    def vals(key):
        p = os.path.join(SERIES, f"{key}.json")
        if not os.path.exists(p):
            return {}
        with open(p, encoding="utf-8") as fh:
            return {pt["date"]: pt["value"] for pt in json.load(fh).get("points", [])
                    if pt.get("value") is not None}

    sh, sz = vals("index_amount_sh000001"), vals("index_amount_sz399001")
    total = {d: round(sh[d] + sz[d], 2) for d in sh if d in sz}
    if not total:
        log("上证/深证序列缺失，跳过总成交额归一")
        return {}

    old = vals("total_amount")
    diff = [(d, old.get(d), total[d]) for d in total
            if d in old and abs(old[d] - total[d]) > 0.01]
    log(f"total_amount：重算 {len(total)} 点，与旧值有尾差 {len(diff)} 处"
        f"（最大 {max((abs(a - b) for _, a, b in diff), default=0):.2f} 亿）")
    compute.write_series_merge("total_amount", "两市成交额", "亿元", total)

    # sh000985 = 沪深合计代理，必须与 total 同值；保留已有 meta（proxy/source/note）
    sp = os.path.join(SERIES, "index_amount_sh000985.json")
    meta = {}
    if os.path.exists(sp):
        with open(sp, encoding="utf-8") as fh:
            meta = {k: v for k, v in json.load(fh).items() if k != "points"}
    meta.setdefault("source", "proxy_sh_sz")
    meta.setdefault("proxy", True)
    meta.setdefault("proxy_of", "total_amount")
    meta.update({"coverage_start": min(total), "coverage_end": max(total),
                 "sample_n": len(total)})
    compute.write_series_merge(
        "index_amount_sh000985", "中证全指(沪深合计代理)", "亿元", total, meta=meta)
    return total


def complete_snapshots():
    fixed = []
    for f in sorted(os.listdir(DAILY)):
        if not f.endswith(".json"):
            continue
        d = f[:-5]
        p = os.path.join(DAILY, f)
        with open(p, encoding="utf-8") as fh:
            snap = json.load(fh)
        changed = False
        if "active_stocks" not in snap:
            snap["active_stocks"] = []
            changed = True
        if "data_quality" not in snap:
            snap["data_quality"] = {
                "spot_derived": "unavailable",
                "note": "该快照构建于质量标记机制上线前，未记录 spot 派生状态；"
                        "字段保留为 unavailable，不补造生成时间。",
                "generated_at": None,
                "business_date": d,
                "date_rule": "asia_shanghai",
            }
            changed = True
        else:
            q = snap["data_quality"]
            # 口径标识与业务日期是客观属性（不是生成时间），旧快照缺失时补齐；
            # generated_at 缺失则保持缺失——绝不编造一个不存在的构建时间。
            if "date_rule" not in q:
                q["date_rule"] = "asia_shanghai"
                changed = True
            if "business_date" not in q:
                q["business_date"] = d
                changed = True
        if changed:
            atomic_write_json(p, snap)
            fixed.append(d)
    log(f"快照结构补齐：{len(fixed)} 份 {fixed}")


def sync_snapshots(total: dict):
    """快照的指数成交额/总成交额对齐到序列（同一指标不能在两个视图给出两个数）。

    实测差异集中在：20261014 的 sh000688（919.73 vs 序列 576.23）、bj899050
    （163.27 vs 121.98）——是盘中生成的快照未回填收盘值；以及 20261015/16 的
    总成交额 0.02% 尾差。全部以序列（已核验）为准。

    两轮处理：先同步 amount 与排名，再按相邻快照重算 amount_change（绝对差）。
    """
    def ser_of(code):
        p = os.path.join(SERIES, f"index_amount_{code}.json")
        if not os.path.exists(p):
            return {}
        with open(p, encoding="utf-8") as fh:
            return {pt["date"]: pt["value"] for pt in json.load(fh).get("points", [])
                    if pt.get("value") is not None}

    cache, snaps, touched = {}, {}, []
    for f in sorted(os.listdir(DAILY)):
        if not f.endswith(".json"):
            continue
        d = f[:-5]
        with open(os.path.join(DAILY, f), encoding="utf-8") as fh:
            snaps[d] = json.load(fh)
    if not snaps:
        return

    for d in sorted(snaps):
        snap = snaps[d]
        changed = False
        for r in (snap.get("index_volume") or []) + (snap.get("widebase") or []):
            code = r.get("code")
            if not code:
                continue
            if code not in cache:
                cache[code] = ser_of(code)
            s = cache[code]
            if d not in s or r.get("amount") == s[d]:
                continue
            log(f"  快照 {d} {code}: {r.get('amount')} → {s[d]}（对齐序列）")
            r["amount"] = s[d]
            r["amount_date"] = d
            r["note"] = ""
            hist = [s[k] for k in sorted(k for k in s if k <= d)]
            r["pctile_all"] = compute.pctile(hist, s[d])
            r["rank_1y"] = compute.rank_of(hist[-244:], s[d])
            changed = True
        ov = snap.get("overview") or {}
        if d in total and ov.get("total_amount") != total[d]:
            log(f"  快照 {d} 总成交额: {ov.get('total_amount')} → {total[d]}")
            ov["total_amount"] = total[d]
            hist = [total[k] for k in sorted(k for k in total if k <= d)]
            ov["total_amount_pctile_all"] = compute.pctile(hist, total[d])
            ov["total_amount_rank_all"] = compute.rank_of(hist, total[d])
            yr = [total[k] for k in sorted(total) if k <= d and k.startswith(d[:4])]
            ov["total_amount_rank_year"] = compute.rank_of(yr, total[d])
            for pt in (snap.get("sparklines") or {}).get("total_amount", []):
                if pt.get("date") == d:
                    pt["value"] = total[d]
            changed = True
        if changed:
            touched.append(d)

    # 第二轮：按相邻快照重算 amount_change（绝对值差），避免留下旧差值
    ordered = sorted(snaps)
    for i in range(1, len(ordered)):
        prev, cur = snaps[ordered[i - 1]], snaps[ordered[i]]
        pmap = {r.get("code"): r.get("amount")
                for r in (prev.get("index_volume") or []) + (prev.get("widebase") or [])}
        for r in (cur.get("index_volume") or []) + (cur.get("widebase") or []):
            code = r.get("code")
            a, b = r.get("amount"), pmap.get(code)
            r["amount_change"] = (round(a - b, 2) if a is not None and b is not None else None)

    for i, d in enumerate(ordered):
        if d in touched or i > 0:
            atomic_write_json(os.path.join(DAILY, f"{d}.json"), snaps[d])
    log(f"快照→序列对齐：{len(touched)} 份快照数值更新（{touched}）")


def main():
    dates_set = set(calendar_mod.get_trade_dates())
    drop_nontrading(dates_set)
    total = normalize_total()
    complete_snapshots()
    if total:
        sync_snapshots(total)
    log("完整性收尾修补完成")


if __name__ == "__main__":
    main()
