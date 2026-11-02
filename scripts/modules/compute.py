# -*- coding: utf-8 -*-
"""计算与派生：排名 / 百分位 / 市值分档 / 微盘代理 / 集中度 / 序列维护

计算规则（严格执行，不得自创）：
- 排名：样本内降序排位，1=最大；并列者日期新者居前
- 百分位：pct = (N - rank) / max(N-1, 1) * 100，保留 1 位小数
- 两融余额 = 沪市汇总余额 + 深市汇总余额
- 10亿以上 = 成交额 >= 10 亿元
- 微盘代理 = 全A按总市值升序取后10%等权合成
"""
from .common import log

MKTCAP_BUCKETS = ["<50亿", "50-100亿", "100-200亿", "200-500亿", "500-1000亿", ">1000亿"]

AMOUNT_BUCKETS = [
    ("100亿+", 1e10, float("inf")),
    ("50-100亿", 5e9, 1e10),
    ("20-50亿", 2e9, 5e9),
    ("10-20亿", 1e9, 2e9),
    ("5-10亿", 5e8, 1e9),
    ("1-5亿", 1e8, 5e8),
    ("<1亿", 0, 1e8),
]


def rank_of(series: list, value: float) -> int:
    """降序排位（1=最大），并列者日期新者居前由调用方保证序列按日期升序"""
    return sum(1 for v in series if v > value) + 1


def pctile(series: list, value: float):
    n = len(series)
    if n < 1:
        return None
    r = rank_of(series, value)
    return round((n - r) / max(n - 1, 1) * 100, 1)


def mktcap_buckets(spot_df):
    """市值 6 档：<50 / 50-100 / 100-200 / 200-500 / 500-1000 / >1000（亿元）"""
    caps = spot_df["mktcap"].dropna() / 1e8  # 元 → 亿
    n = len(caps)
    edges = [50, 100, 200, 500, 1000]
    counts = []
    lo = 0
    for e in edges:
        counts.append(int(((caps >= lo) & (caps < e)).sum()) if lo > 0 else int((caps < e).sum()))
        lo = e
    counts.append(int((caps >= 1000).sum()))
    rows = []
    for label, c in zip(MKTCAP_BUCKETS, counts):
        rows.append({"label": label, "count": c, "pct": round(c / n * 100, 1) if n else 0})
    return rows


def amount_buckets(spot_df):
    """成交额 7 档：100亿+/50-100/20-50/10-20/5-10/1-5/<1亿（基于 spot_df['amount'] 元）"""
    if "amount" not in spot_df.columns:
        return [{"label": label, "count": 0, "pct": 0} for label, _lo, _hi in AMOUNT_BUCKETS]
    amounts = spot_df["amount"].dropna()
    n = len(amounts)
    rows = []
    for label, lo, hi in AMOUNT_BUCKETS:
        c = int(((amounts >= lo) & (amounts < hi)).sum()) if hi != float("inf") else int((amounts >= lo).sum())
        rows.append({"label": label, "count": c, "pct": round(c / n * 100, 1) if n else 0})
    return rows


# 成交额≥10亿股票的市值档位（数量结构 / 市值贡献结构 共用）
OVER10E_MKTCAP_BUCKETS = [
    ("1000亿以上", 1000, float("inf")),
    ("500-1000亿", 500, 1000),
    ("200-500亿", 200, 500),
    ("100-200亿", 100, 200),
    ("50-100亿", 50, 100),
    ("50亿以下", 0, 50),
]


def over_10e_marketcap_buckets(spot_df):
    """成交额≥10亿个股的市值数量结构（基于 spot_df['mktcap'] 元）"""
    if "amount" not in spot_df.columns or "mktcap" not in spot_df.columns:
        return [{"label": label, "count": 0, "pct": 0} for label, _lo, _hi in OVER10E_MKTCAP_BUCKETS]
    active = spot_df.dropna(subset=["amount", "mktcap"])
    active = active[active["amount"] >= 10 * 1e8]
    caps = active["mktcap"] / 1e8
    n = len(caps)
    rows = []
    for label, lo, hi in OVER10E_MKTCAP_BUCKETS:
        c = int(((caps >= lo) & (caps < hi)).sum()) if hi != float("inf") else int((caps >= lo).sum())
        rows.append({"label": label, "count": c, "pct": round(c / n * 100, 1) if n else 0})
    return rows


def over_10e_marketcap_value_buckets(spot_df):
    """成交额≥10亿个股的市值贡献结构：各档合计市值 / 活跃股票总市值（基于 spot_df['mktcap'] 元）"""
    if "amount" not in spot_df.columns or "mktcap" not in spot_df.columns:
        return [{"label": label, "count": 0, "total_value": 0, "pct": 0}
                for label, _lo, _hi in OVER10E_MKTCAP_BUCKETS]
    active = spot_df.dropna(subset=["amount", "mktcap"])
    active = active[active["amount"] >= 10 * 1e8]
    caps = active["mktcap"] / 1e8
    total = float(caps.sum())
    rows = []
    for label, lo, hi in OVER10E_MKTCAP_BUCKETS:
        if hi == float("inf"):
            mask = caps >= lo
        else:
            mask = (caps >= lo) & (caps < hi)
        c = int(mask.sum())
        s = float(caps[mask].sum())
        rows.append({"label": label, "count": c, "total_value": round(s, 2),
                     "pct": round(s / total * 100, 1) if total > 0 else 0})
    return rows


MICRO_MIN_UNIVERSE = 100   # 微盘代理最小样本：后 10% 至少 100 只，否则「后10%」没有统计意义
# 序列排名的可信最小样本：不足 30 个点时 rank/pctile 无统计意义，一律留空（前端显示 —）
MIN_RANK_SAMPLE = 30


def microcap_proxy_amount(spot_df):
    """微盘代理：全A按总市值升序取后10%等权合成，返回其**平均**成交额（亿元/只）。

    口径固定为「每只股票的平均成交额」，量级应随市场活跃度波动（历史区间约 0.2~1.5 亿元/只）。
    若返回值出现两位数量级（如 130 亿元/只），说明统计对象或单位错了，而不是「微盘股变活跃」。
    样本不足 MICRO_MIN_UNIVERSE 时返回 (None, k)，由调用方沿用旧值/留空。
    """
    if spot_df is None or "mktcap" not in spot_df.columns or "amount" not in spot_df.columns:
        return None, 0
    df = spot_df.dropna(subset=["mktcap", "amount"]).copy()
    df = df[df["mktcap"] > 0]
    if df.empty:
        return None, 0
    df = df.sort_values("mktcap")
    k = max(int(len(df) * 0.1), 1)
    if k < MICRO_MIN_UNIVERSE:
        return None, k
    micro = df.head(k)
    return round(float(micro["amount"].mean()) / 1e8, 2), k


def concentration(spot_df):
    """个股集中度：成交额前 10/20/50 及累计占比（前10总占比同时写入 top10_concentration 序列）"""
    df = spot_df.dropna(subset=["amount"]).sort_values("amount", ascending=False)
    total = df["amount"].sum()
    if total <= 0:
        return None
    def rows(k):
        out = []
        for _, r in df.head(k).iterrows():
            pct = round(float(r["amount"]) / total * 100, 2)
            out.append({"code": str(r["code"]), "name": str(r["name"]),
                        "amount": round(float(r["amount"]) / 1e8, 2), "pct_of_total": pct})
        return out
    top10, top20, top50 = rows(10), rows(20), rows(50)
    top10_total = round(sum(x["pct_of_total"] for x in top10), 2)
    return {"top_n": [10, 20, 50], "top10": top10, "top20": top20, "top50": top50,
            "top20_cum_pct": round(sum(x["pct_of_total"] for x in top20), 2),
            "top50_cum_pct": round(sum(x["pct_of_total"] for x in top50), 2),
            "top10_total": top10_total}


def append_bucket_series(date: str, buckets: list, keep=400):
    """市值分档序列（非标量序列，单独维护，仅保留最近 keep 个点）"""
    import json, os
    from .common import DATA_DIR, atomic_write_json, now_iso
    path = os.path.join(DATA_DIR, "series", "mktcap_buckets.json")
    points = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            points = json.load(f).get("points", [])
    points = [p for p in points if p["date"] != date]
    points.append({"date": date, "buckets": buckets})
    points.sort(key=lambda p: p["date"])
    atomic_write_json(path, {"key": "mktcap_buckets", "name": "市值分档结构", "unit": "%",
                             "updated_at": now_iso(), "points": points[-keep:]})
    log(f"市值分档序列共 {min(len(points), keep)} 点")


def build_index_agg(prefix: str = "index_amount_"):
    """重建 data/series/index_agg.json：各指数月/年均值预聚合表（四档切换单请求）"""
    import json, os
    from .common import DATA_DIR, atomic_write_json, now_iso
    sdir = os.path.join(DATA_DIR, "series")
    codes = {}
    for fn in sorted(os.listdir(sdir)):
        if not fn.startswith(prefix) or not fn.endswith(".json"):
            continue
        with open(os.path.join(sdir, fn), "r", encoding="utf-8") as f:
            s = json.load(f)
        pts = [p for p in s.get("points", []) if p.get("value") is not None]
        if not pts:
            continue
        months, years = {}, {}
        for p in pts:
            months.setdefault(p["date"][:6], []).append(p["value"])
            years.setdefault(p["date"][:4], []).append(p["value"])
        vals = [p["value"] for p in pts]
        code = fn[len(prefix):-5]
        codes[code] = {
            "name": s.get("name", code),
            "months": {k: round(sum(v) / len(v), 2) for k, v in months.items()},
            "years": {k: round(sum(v) / len(v), 2) for k, v in years.items()},
            "all_mean": round(sum(vals) / len(vals), 2),
            "count": len(vals),
        }
    atomic_write_json(os.path.join(sdir, "index_agg.json"),
                      {"updated_at": now_iso(), "codes": codes})
    log(f"index_agg 聚合表重建：{len(codes)} 个代码")


def _period_start(date: str, dates: list, period: str):
    """根据交易日历返回周期起点（week/month/year），周期内无交易日则返回 None"""
    import datetime
    d = datetime.datetime.strptime(date, "%Y%m%d")
    if period == "week":
        mon = d - datetime.timedelta(days=d.weekday())
        start = mon.strftime("%Y%m%d")
    elif period == "month":
        start = d.replace(day=1).strftime("%Y%m%d")
    elif period == "year":
        start = d.replace(month=1, day=1).strftime("%Y%m%d")
    else:
        return None
    candidates = [x for x in dates if start <= x <= date]
    return candidates[0] if candidates else None


def avg_index_amount(code: str, date: str, dates: list, period: str):
    """读取 index_amount_{code} 序列，计算周期内（含当日）平均成交额（亿元）"""
    import json, os
    from .common import DATA_DIR
    start = _period_start(date, dates, period)
    if start is None:
        return None
    path = os.path.join(DATA_DIR, "series", f"index_amount_{code}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        pts = json.load(f).get("points", [])
    vals = [p["value"] for p in pts if start <= p["date"] <= date and p.get("value") is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def over_10e(spot_df):
    """10亿以上 = 成交额 >= 10 亿元"""
    df = spot_df.dropna(subset=["amount"])
    cnt = int((df["amount"] >= 10 * 1e8).sum())
    n = len(df)
    return cnt, round(cnt / n * 100, 1) if n else 0, n


def update_series(key: str, name: str, unit: str, date: str, value):
    """读取 data/series/{key}.json，upsert 当日点，重算 rank_year/rank_1y/rank_all/pctile"""
    return write_series_merge(key, name, unit, {date: value})


def write_series_merge(key: str, name: str, unit: str, values: dict, meta: dict | None = None):
    """批量合并：已有序列点 + 新值（新值优先），一次性整体重算排名/百分位后原子写出。
    适合回补场景（避免逐点 update 的 O(n^3) 重算）。

    meta: 附加到文件顶层的元信息（如 coverage_start / source / note / min_sample），
    前端忽略未知字段；用于标明口径与覆盖区间，避免把不完整序列当作全长历史。

    **已有顶层元信息必须保留**：此前实现只写 key/name/unit/updated_at，
    导致每次增量把 coverage_start / proxy / demo_removed 等口径声明抹掉，
    前端于是把 3 个点的序列当成全长历史。现在除 points/updated_at 外整体继承。
    """
    import json, os
    from .common import DATA_DIR, atomic_write_json, now_iso
    path = os.path.join(DATA_DIR, "series", f"{key}.json")
    merged = {}
    inherited = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
        inherited = {k: v for k, v in obj.items()
                     if k not in ("points", "updated_at", "key", "name", "unit")}
        for p in obj.get("points", []):
            if p.get("value") is not None:
                merged[p["date"]] = p["value"]
    merged.update({d: v for d, v in values.items() if v is not None})
    points = [{"date": d, "value": v} for d, v in sorted(merged.items())]
    vals = [p["value"] for p in points]
    dates = [p["date"] for p in points]
    # 样本过少时排名/百分位无意义（3~5 个点的「历史分位」会误导），一律留空
    enough = len(points) >= MIN_RANK_SAMPLE
    for i, p in enumerate(points):
        v = p["value"]
        if not enough:
            p["rank_all"] = p["pctile"] = p["rank_year"] = p["rank_1y"] = None
            continue
        p["rank_all"] = rank_of(vals, v)
        p["pctile"] = pctile(vals, v)
        year_vals = [q["value"] for q, d in zip(points, dates) if d.startswith(p["date"][:4])]
        p["rank_year"] = rank_of(year_vals, v) if year_vals else None
        lo = max(0, i - 243)
        p["rank_1y"] = rank_of(vals[lo:i + 1], v)
    if meta:
        inherited.update(meta)
    atomic_write_json(path, {"key": key, "name": name, "unit": unit,
                             "updated_at": now_iso(), **inherited, "points": points})
    log(f"序列 {key} 共 {len(points)} 点（本次合并 {len(values)} 个新值）")
