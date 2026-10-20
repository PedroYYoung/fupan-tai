# -*- coding: utf-8 -*-
"""收尾修补：① 恢复被降级口径覆盖的跌停值；② 清理「陈旧降级」成交额。

两个问题都是本轮实测暴露的，不是猜的：

① limit_down 20261020：首次构建时东财跌停池成功得到 6 家（快照 data_quality.limit_pool
   .limit_down_ok=True）；几小时后重跑，池接口 SSLError，走「快照兜底判定」得 9 家并写回
   序列 —— 低可信源覆盖了已核验值。这里按快照里的东财值恢复，并保留两侧一致。

② sh932000 20261020：当日全部源失败，旧逻辑「降级复用最近交易日」复用了 20251231 的
   5040.02 亿（滞后 293 天），等于把 9 个月前的数字当成当日成交额展示。凡是滞后超过
   MAX_STALE_DAYS 的降级行，一律置空并标记 unavailable_stale。

幂等：重复执行不产生变化。
"""
import glob
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from modules import compute  # noqa: E402
from modules.common import DATA_DIR, log  # noqa: E402
from modules.index_mod import MAX_STALE_DAYS, _days_between  # noqa: E402


def _load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _dump(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))


def restore_limit_down_from_snapshot():
    """把被降级口径覆盖的跌停值恢复为快照中「东财直采」的值。"""
    series_p = os.path.join(DATA_DIR, "series", "limit_down.json")
    obj = _load(series_p)
    pmap = {p["date"]: p for p in obj["points"]}
    fixed = []
    for fp in sorted(glob.glob(os.path.join(DATA_DIR, "daily", "*.json"))):
        d = os.path.basename(fp)[:-5]
        snap = _load(fp)
        q = (snap.get("data_quality") or {}).get("limit_pool") or {}
        emo = snap.get("emotion") or {}
        em_val = emo.get("limit_down")
        cur = pmap.get(d, {}).get("value")
        if q.get("limit_down_ok") is not True or q.get("limit_down_src") != "eastmoney":
            continue
        if em_val is None or cur is None or cur == em_val:
            continue
        fixed.append((d, cur, em_val))
    if not fixed:
        log("跌停值：无需恢复（序列与东财直采快照一致）")
        return
    compute.write_series_merge("limit_down", obj.get("name", "跌停家数"),
                               obj.get("unit", "家"),
                               {d: v for d, _, v in fixed})
    for d, cur, v in fixed:
        log(f"跌停值恢复：{d} {cur} → {v}（东财池直采值，覆盖来自降级兜底）")


def clear_stale_index_amount():
    """滞后超过 MAX_STALE_DAYS 的「最近交易日降级」行 → 置空，不冒充当日值。"""
    n = 0
    for fp in sorted(glob.glob(os.path.join(DATA_DIR, "daily", "*.json"))):
        d = os.path.basename(fp)[:-5]
        snap = _load(fp)
        changed = False
        for block in ("index_volume", "widebase"):
            for r in snap.get(block) or []:
                if r.get("note") != "last_trading_day":
                    continue
                gap = _days_between(str(r.get("amount_date") or ""), d)
                if gap is None or gap <= MAX_STALE_DAYS:
                    continue
                log(f"陈旧降级置空：{d} {r.get('code')} 原值 {r.get('amount')}"
                    f"（来自 {r.get('amount_date')}，滞后 {gap} 天）")
                r["amount"] = None
                r["amount_date"] = None
                r["note"] = "unavailable_stale"
                r["approx"] = False
                r["amount_change"] = None
                r["pctile_all"] = None
                r["rank_1y"] = None
                r["rank_year"] = None
                changed = True
                n += 1
        if changed:
            _dump(fp, snap)
    if not n:
        log("陈旧降级：无需要清理的行")
    else:
        log(f"陈旧降级：共清理 {n} 行")


def main():
    restore_limit_down_from_snapshot()
    clear_stale_index_amount()
    log("收尾修补完成")


if __name__ == "__main__":
    main()
