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


def microcap_proxy_amount(spot_df):
    """微盘代理：全A按总市值升序取后10%等权合成，返回其平均成交额（亿元）"""
    df = spot_df.dropna(subset=["mktcap", "amount"]).copy()
    df = df.sort_values("mktcap")
    k = max(int(len(df) * 0.1), 1)
    micro = df.head(k)
    return round(micro["amount"].mean() / 1e8, 2), k


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


def over_10e(spot_df):
    """10亿以上 = 成交额 >= 10 亿元"""
    df = spot_df.dropna(subset=["amount"])
    cnt = int((df["amount"] >= 10 * 1e8).sum())
    n = len(df)
    return cnt, round(cnt / n * 100, 1) if n else 0, n


def update_series(key: str, name: str, unit: str, date: str, value):
    """读取 data/series/{key}.json，upsert 当日点，重算 rank_year/rank_1y/rank_all/pctile"""
    import json, os
    from .common import DATA_DIR, atomic_write_json, now_iso
    path = os.path.join(DATA_DIR, "series", f"{key}.json")
    points = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            points = json.load(f).get("points", [])
    points = [p for p in points if p["date"] != date]
    points.append({"date": date, "value": value})
    points.sort(key=lambda p: p["date"])
    values = [p["value"] for p in points]
    dates = [p["date"] for p in points]
    year = date[:4]
    for i, p in enumerate(points):
        v = p["value"]
        p["rank_all"] = rank_of(values, v)
        p["pctile"] = pctile(values, v)
        year_vals = [q["value"] for q, d in zip(points, dates) if d.startswith(year)]
        p["rank_year"] = rank_of(year_vals, v) if year_vals else None
        lo = max(0, i - 243)
        p["rank_1y"] = rank_of(values[lo:i + 1], v)
    atomic_write_json(path, {"key": key, "name": name, "unit": unit,
                             "updated_at": now_iso(), "points": points})
    log(f"序列 {key} 共 {len(points)} 点")
