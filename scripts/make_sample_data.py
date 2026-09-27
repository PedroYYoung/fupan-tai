#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成第一批示例数据（字段值均为合理真实量级，可直接打开前端查看）。

注意：这是演示/联调数据（种子随机、量级参照真实市场），首次真实建仓请运行
  python scripts/build.py --date YYYYMMDD
以 AKShare 实盘数据覆盖。节假日为近似窗口，正式数据以交易日历接口为准。
"""
import json
import os
import random
import datetime

random.seed(20260925)
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(HERE), "data")

# 年度量级基准（亿元）
AMT_BASE = {2020: 8500, 2021: 10800, 2022: 9400, 2023: 9600, 2024: 11500, 2025: 13500, 2026: 14800}
MARGIN_BASE = {2020: 11500, 2021: 16800, 2022: 15200, 2023: 15800, 2024: 16800, 2025: 18200, 2026: 19300}
IDX_BASE = {
    "sh000001": 5200, "sz399001": 6800, "sz399006": 2600, "sh000688": 520, "bj899050": 210,
    "sh000016": 1150, "sh000300": 4100, "sz399673": 950, "sh000905": 1850,
    "sh000906": 5300, "sh000852": 2100, "sh932000": 1500, "sh000985": 12500,
    "hstech_513180": 55, "micro_proxy": 130,
}
IDX_NAMES = {
    "sh000001": "上证指数", "sz399001": "深证成指", "sz399006": "创业板指",
    "sh000688": "科创50", "bj899050": "北证50", "sh000016": "上证50",
    "sh000300": "沪深300", "sz399673": "创业板50", "sh000905": "中证500",
    "sh000906": "中证800", "sh000852": "中证1000", "sh932000": "中证2000",
    "sh000985": "中证全指", "hstech_513180": "恒生科技(513180近似)",
    "micro_proxy": "微盘代理(自建)",
}

# 近似休市窗口（示例数据用；正式以交易日历接口为准）
HOLIDAYS = {
    2020: [("0101", "0101"), ("0124", "0131"), ("0406", "0406"), ("0501", "0505"),
           ("0625", "0626"), ("1001", "1008")],
    2021: [("0101", "0103"), ("0211", "0217"), ("0405", "0405"), ("0503", "0505"),
           ("0614", "0614"), ("0920", "0921"), ("1001", "1007")],
    2022: [("0103", "0103"), ("0131", "0204"), ("0404", "0405"), ("0502", "0504"),
           ("0603", "0603"), ("0912", "0912"), ("1003", "1007")],
    2023: [("0102", "0102"), ("0123", "0127"), ("0405", "0405"), ("0501", "0503"),
           ("0622", "0623"), ("0929", "0929"), ("1002", "1006")],
    2024: [("0101", "0101"), ("0212", "0216"), ("0404", "0405"), ("0501", "0503"),
           ("0610", "0610"), ("0916", "0917"), ("1001", "1007")],
    2025: [("0101", "0101"), ("0128", "0203"), ("0404", "0404"), ("0501", "0505"),
           ("0602", "0602"), ("1001", "1008")],
    2026: [("0101", "0102"), ("0216", "0220"), ("0406", "0406"), ("0501", "0505"), ("0619", "0619")],
}


def trading_days(start="20200102", end="20260925"):
    d = datetime.datetime.strptime(start, "%Y%m%d").date()
    e = datetime.datetime.strptime(end, "%Y%m%d").date()
    out = []
    while d <= e:
        if d.weekday() < 5:
            key = d.strftime("%m%d")
            if not any(s <= key <= t for s, t in HOLIDAYS.get(d.year, [])):
                out.append(d.strftime("%Y%m%d"))
        d += datetime.timedelta(days=1)
    return out


def base_at(d: str, table: dict) -> float:
    """按年份线性插值年度基准"""
    y = int(d[:4])
    years = sorted(table)
    if y <= years[0]:
        return table[years[0]]
    if y >= years[-1]:
        return table[years[-1]]
    for a, b in zip(years, years[1:]):
        if a <= y <= b:
            fa = datetime.date(a, 12, 31).timetuple().tm_yday
            t = (datetime.datetime.strptime(d, "%Y%m%d").timetuple().tm_yday) / fa
            return table[a] + (table[b] - table[a]) * t
    return table[y]


def walk(dates, table, vol=0.12, lo=None, hi=None, ar=0.75):
    """向年度基准均值回归的 AR 合成序列（量级贴近真实市场）"""
    vals, noise = [], 0.0
    for d in dates:
        noise = ar * noise + random.uniform(-vol, vol)
        v = base_at(d, table) * (1 + noise)
        v = max(lo or 0, min(hi or 1e12, v))
        vals.append(round(v, 2))
    return vals


def with_ranks(dates, vals, extra=None):
    pts = []
    n = len(vals)
    for i, (d, v) in enumerate(zip(dates, vals)):
        rank = sum(1 for x in vals if x > v) + 1
        year_vals = [x for x, dd in zip(vals, dates) if dd[:4] == d[:4]]
        ry = sum(1 for x in year_vals if x > v) + 1
        lo = max(0, i - 243)
        win = vals[lo:i + 1]
        r1 = sum(1 for x in win if x > v) + 1
        pct = round((n - rank) / max(n - 1, 1) * 100, 1)
        p = {"date": d, "value": v, "rank_year": ry, "rank_1y": r1,
             "rank_all": rank, "pctile": pct}
        if extra:
            p.update(extra(d, v))
        pts.append(p)
    return pts


def write_json(rel, obj):
    p = os.path.join(DATA, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    print("写出", rel)


TOP10_POOL = [
    ("600519", "贵州茅台"), ("300750", "宁德时代"), ("300059", "东方财富"),
    ("688981", "中芯国际"), ("600900", "长江电力"), ("002594", "比亚迪"),
    ("601899", "紫金矿业"), ("000858", "五粮液"), ("000725", "京东方A"),
    ("300308", "中际旭创"),
]
TOP50_POOL = [
    ("601318", "中国平安"), ("600036", "招商银行"), ("002475", "立讯精密"),
    ("002415", "海康威视"), ("600276", "恒瑞医药"), ("300760", "迈瑞医疗"),
    ("601012", "隆基绿能"), ("600438", "通威股份"), ("300274", "阳光电源"),
    ("300014", "亿纬锂能"), ("002460", "赣锋锂业"), ("002466", "天齐锂业"),
    ("600111", "北方稀土"), ("601919", "中远海控"), ("000568", "泸州老窖"),
    ("600809", "山西汾酒"), ("601633", "长城汽车"), ("000625", "长安汽车"),
    ("000100", "TCL科技"), ("688256", "寒武纪"), ("688041", "海光信息"),
    ("000977", "浪潮信息"), ("603019", "中科曙光"), ("601138", "工业富联"),
    ("600547", "山东黄金"), ("600150", "中国船舶"), ("600031", "三一重工"),
    ("601100", "恒立液压"), ("300124", "汇川技术"), ("601127", "赛力斯"),
    ("002230", "科大讯飞"), ("688111", "金山办公"), ("603986", "兆易创新"),
    ("600745", "闻泰科技"), ("603501", "韦尔股份"), ("002049", "紫光国微"),
    ("600584", "长电科技"), ("002371", "北方华创"), ("300661", "圣邦股份"),
    ("601728", "中国电信"), ("600941", "中国移动"), ("601857", "中国石油"),
    ("600028", "中国石化"), ("601088", "中国神华"), ("601668", "中国建筑"),
    ("601390", "中国银行"), ("601939", "建设银行"), ("600000", "浦发银行"),
    ("600030", "中信证券"), ("601688", "华泰证券"),
]
LU_STOCKS = [
    ("002104", "恒宝股份"), ("300469", "信息发展"), ("603536", "惠发食品"),
    ("000158", "常山北明"), ("600728", "佳都科技"), ("300379", "东方通"),
    ("603000", "人民网"), ("002230", "科大讯飞"),
]
LD_STOCKS = [
    ("603533", "掌阅科技"), ("002175", "东方智造"), ("300586", "美联新材"),
    ("600869", "远达环保"),
]


def main():
    dates = trading_days()
    latest = dates[-1]
    print(f"交易日 {len(dates)} 天，最新 {latest}")

    # ---- 序列 ----
    amt_vals = walk(dates, AMT_BASE, 0.10, 5500, 24000)
    margin_vals = walk(dates, MARGIN_BASE, 0.04, 10000, 23000)
    lu_vals = walk(dates, {y: 70 for y in range(2020, 2027)}, 0.35, 12, 190)
    ld_vals = walk(dates, {y: 9 for y in range(2020, 2027)}, 0.5, 0, 85)
    o10_vals = [round(a * 0.043 + random.uniform(-40, 40), 0) for a in amt_vals]

    write_json("meta/trading_days.json", {
        "list": dates, "latest": latest,
        "updated_at": "2026-09-25T19:35:12+08:00",
        "source_versions": {"akshare": "1.15.0", "baostock": "0.8.9", "tushare": "1.4.8"},
    })
    write_json("latest.json", {"latest": latest, "updated_at": "2026-09-25T19:35:12+08:00"})

    series = {
        "total_amount": ("两市成交额", "亿元", amt_vals),
        "margin": ("两融余额", "亿元", margin_vals),
        "limit_up_down": ("涨停家数", "家", lu_vals),
        "limit_down": ("跌停家数", "家", ld_vals),
        "over_10e_count": ("10亿以上家数", "家", o10_vals),
    }
    for key, (name, unit, vals) in series.items():
        write_json(f"series/{key}.json", {
            "key": key, "name": name, "unit": unit,
            "updated_at": "2026-09-25T19:35:12+08:00",
            "points": with_ranks(dates, vals),
        })
    for code, base in IDX_BASE.items():
        tbl = {y: base for y in range(2020, 2027)}
        vals = walk(dates, tbl, 0.11, base * 0.35, base * 2.4)
        write_json(f"series/index_amount_{code}.json", {
            "key": f"index_amount_{code}", "name": IDX_NAMES[code], "unit": "亿元",
            "updated_at": "2026-09-25T19:35:12+08:00",
            "points": with_ranks(dates, vals),
        })

    # ---- 头部抱团度序列（前10成交占比 %）----
    conc_vals = [round(random.uniform(3.8, 9.5), 2) for _ in dates]
    write_json("series/top10_concentration.json", {
        "key": "top10_concentration", "name": "前10成交占比", "unit": "%",
        "updated_at": "2026-09-25T19:35:12+08:00",
        "points": with_ranks(dates, conc_vals),
    })
    conc_pctile = {d: p["pctile"] for d, p in zip(dates, with_ranks(dates, conc_vals))}

    # ---- 市值分档序列（近一年，堆叠面积图用）----
    bucket_dates = dates[-250:]
    bucket_pts = []
    for d in bucket_dates:
        big = random.uniform(2.6, 4.6)
        mid = random.uniform(11.5, 14.5)
        pcts = [44.5 + random.uniform(-2, 2), 20.1 + random.uniform(-1.5, 1.5),
                15.4 + random.uniform(-1, 1), 12.5 + random.uniform(-1, 1),
                mid, big]
        s = sum(pcts)
        labels = ["<50亿", "50-100亿", "100-200亿", "200-500亿", "500-1000亿", ">1000亿"]
        counts = [2280, 1030, 790, 640, 230, 160]
        bucket_pts.append({"date": d, "buckets": [
            {"label": lb, "count": c, "pct": round(p / s * 100, 1)}
            for lb, c, p in zip(labels, counts, pcts)]})
    write_json("series/mktcap_buckets.json", {
        "key": "mktcap_buckets", "name": "市值分档结构", "unit": "%",
        "updated_at": "2026-09-25T19:35:12+08:00",
        "points": bucket_pts,
    })

    # ---- 指数聚合表（四档切换用：月/年均值一次取回，避免逐代码请求序列）----
    codes = list(IDX_BASE.keys())
    agg_codes = {}
    for code in codes:
        tbl = {y: IDX_BASE[code] for y in range(2020, 2027)}
        vals = walk(dates, tbl, 0.11, IDX_BASE[code] * 0.35, IDX_BASE[code] * 2.4)
        months, years = {}, {}
        for d, v in zip(dates, vals):
            months[d[:6]] = months.get(d[:6], [])
            months[d[:6]].append(v)
            years[d[:4]] = years.get(d[:4], [])
            years[d[:4]].append(v)
        agg_codes[code] = {
            "name": IDX_NAMES[code],
            "months": {k: round(sum(v) / len(v), 2) for k, v in months.items()},
            "years": {k: round(sum(v) / len(v), 2) for k, v in years.items()},
            "all_mean": round(sum(vals) / len(vals), 2),
            "count": len(vals),
        }
    write_json("series/index_agg.json", {
        "updated_at": "2026-09-25T19:35:12+08:00",
        "codes": agg_codes,
    })

    # ---- daily 快照：20200102 + 最近 65 个交易日 ----
    targets = ["20200102"] + dates[-65:]
    for d in targets:
        i = dates.index(d)
        amt, mg = amt_vals[i], margin_vals[i]
        lu, ld = int(lu_vals[i]), int(ld_vals[i])
        o10 = int(o10_vals[i])
        n_stocks = 5120 + random.randint(-30, 40)
        lu10 = [{"code": c, "name": nm, "amount": round(random.uniform(10, 42), 2),
                 "change": 19.98 if c.startswith("30") else 10.01,
                 "board": "创业板" if c.startswith("30") else "主板"}
                for c, nm in random.sample(LU_STOCKS, 7)]
        ld10 = [{"code": c, "name": nm, "amount": round(random.uniform(10, 25), 2),
                 "change": -19.97 if c.startswith("30") else -10.02,
                 "board": "创业板" if c.startswith("30") else "主板"}
                for c, nm in random.sample(LD_STOCKS, 3)]

        def idx_row(code, base, keys=("rank_year", "rank_1y")):
            v = round(base * random.uniform(0.85, 1.2), 2)
            return {"name": IDX_NAMES[code], "code": code, "amount": v,
                    "rank_year": random.randint(20, 900), "rank_1y": random.randint(20, 900),
                    "pctile_all": round(random.uniform(30, 85), 1),
                    "approx": code == "hstech_513180"}

        index_volume = [idx_row(c, IDX_BASE[c]) for c in
                        ["sh000001", "sz399001", "sz399006", "sh000688", "bj899050"]]
        widebase = [idx_row(c, IDX_BASE[c]) for c in
                    ["sh000016", "sh000300", "sz399673", "sh000688", "sh000905",
                     "sh000906", "sh000852", "sh932000", "sh000985", "hstech_513180"]]
        micro_amt = round(IDX_BASE["micro_proxy"] * random.uniform(0.85, 1.25), 2)
        widebase.append({"name": "微盘代理(自建)", "code": "micro_proxy",
                         "amount": micro_amt, "rank_1y": random.randint(30, 800),
                         "pctile_all": round(random.uniform(35, 90), 1), "approx": False})

        # ---- 集中度：前10/20/50 三张表 ----
        pool = random.sample(TOP50_POOL, 50)
        a10 = sorted([random.uniform(35, 120) for _ in range(10)], reverse=True)
        a20 = sorted([random.uniform(15, 45) for _ in range(10)], reverse=True)
        a50 = sorted([random.uniform(5, 25) for _ in range(30)], reverse=True)
        amounts50 = a10 + a20 + a50
        rows = [{"code": c, "name": nm, "amount": round(a, 2),
                 "pct_of_total": round(a / amt * 100, 2)}
                for (c, nm), a in zip(pool, amounts50)]
        rows.sort(key=lambda x: -x["amount"])
        top10, top20, top50 = rows[:10], rows[:20], rows[:50]
        top10_sum = round(sum(x["pct_of_total"] for x in top10), 2)

        daily = {
            "trade_date": d,
            "overview": {
                "total_amount": amt,
                "total_amount_rank_year": sum(1 for x, dd in zip(amt_vals, dates) if x > amt and dd[:4] == d[:4]) + 1,
                "total_amount_rank_all": sum(1 for x in amt_vals if x > amt) + 1,
                "total_amount_pctile_all": round((len(amt_vals) - sum(1 for x in amt_vals if x > amt) - 1) / max(len(amt_vals) - 1, 1) * 100, 1),
                "margin_balance": mg,
                "margin_rank_year": sum(1 for x, dd in zip(margin_vals, dates) if x > mg and dd[:4] == d[:4]) + 1,
                "margin_pctile_all": round((len(margin_vals) - sum(1 for x in margin_vals if x > mg) - 1) / max(len(margin_vals) - 1, 1) * 100, 1),
                "limit_up": lu, "limit_down": ld,
                "over_10e_count": o10,
                "over_10e_ratio": round(o10 / n_stocks * 100, 1),
                "stock_count": n_stocks,
            },
            "index_volume": index_volume,
            "widebase": widebase,
            "industry": {
                "top10_up": [{"name": nm, "change": round(random.uniform(1.2, 4.8), 2),
                              "amount": round(random.uniform(80, 420), 1),
                              "ratio": round(random.uniform(1.0, 3.5), 1)}
                             for nm in ["半导体", "通信设备", "软件开发", "消费电子", "光伏设备",
                                        "汽车整车", "证券", "军工电子", "算力租赁", "电池"]],
                "top10_down": [{"name": nm, "change": round(random.uniform(-3.5, -0.8), 2),
                                "amount": round(random.uniform(40, 260), 1),
                                "ratio": round(random.uniform(0.5, 2.2), 1)}
                               for nm in ["煤炭开采", "银行", "保险", "电力", "燃气",
                                          "白酒", "房地产", "中药", "公路铁路", "养殖"]],
            },
            "concentration": {
                "top_n": [10, 20, 50],
                "top10": top10,
                "top20": top20,
                "top50": top50,
                "top20_cum_pct": round(sum(x["pct_of_total"] for x in top20), 2),
                "top50_cum_pct": round(sum(x["pct_of_total"] for x in top50), 2),
                "top10_total_pctile_hist": conc_pctile.get(d),
            },
            "liquidity": {
                "over_10e_count": o10,
                "over_10e_ratio": round(o10 / n_stocks * 100, 1),
                "pctile_count": round((len(o10_vals) - sum(1 for x in o10_vals if x > o10) - 1) / max(len(o10_vals) - 1, 1) * 100, 1),
                "mktcap_buckets": [
                    {"label": "<50亿", "count": 2280, "pct": 44.5},
                    {"label": "50-100亿", "count": 1030, "pct": 20.1},
                    {"label": "100-200亿", "count": 790, "pct": 15.4},
                    {"label": "200-500亿", "count": 640, "pct": 12.5},
                    {"label": "500-1000亿", "count": 230, "pct": 4.5},
                    {"label": ">1000亿", "count": 160, "pct": 3.0},
                ],
            },
            "emotion": {
                "limit_up": lu, "limit_down": ld,
                "lu_pctile": round((len(lu_vals) - sum(1 for x in lu_vals if x > lu) - 1) / max(len(lu_vals) - 1, 1) * 100, 1),
                "ld_pctile": round((len(ld_vals) - sum(1 for x in ld_vals if x > ld) - 1) / max(len(ld_vals) - 1, 1) * 100, 1),
                "lu_ratio_of_total": round(lu / n_stocks * 100, 2),
                "ld_ratio_of_total": round(ld / n_stocks * 100, 2),
                "lu_ratio_of_over10e": round(len(lu10) / o10 * 100, 1),
                "ld_ratio_of_over10e": round(len(ld10) / o10 * 100, 1),
                "lu_over10e": lu10, "ld_over10e": ld10,
            },
            "sparklines": {
                "total_amount": [{"date": dd, "value": v} for dd, v in zip(dates[max(0, i - 19):i + 1], amt_vals[max(0, i - 19):i + 1])],
                "margin": [{"date": dd, "value": v} for dd, v in zip(dates[max(0, i - 19):i + 1], margin_vals[max(0, i - 19):i + 1])],
                "limit_up_down": [{"date": dd, "up": int(u), "down": int(dn)}
                                  for dd, u, dn in zip(dates[max(0, i - 19):i + 1],
                                                       lu_vals[max(0, i - 19):i + 1],
                                                       ld_vals[max(0, i - 19):i + 1])],
                "over_10e_count": [{"date": dd, "value": v} for dd, v in zip(dates[max(0, i - 19):i + 1], o10_vals[max(0, i - 19):i + 1])],
            },
        }
        # 涨跌停百分位用真实序列重算，覆盖随机值
        daily["emotion"]["lu_pctile"] = round((len(lu_vals) - sum(1 for x in lu_vals if x > lu) - 1) / max(len(lu_vals) - 1, 1) * 100, 1)
        write_json(f"daily/{d}.json", daily)
    print(f"daily 快照 {len(targets)} 份完成")


if __name__ == "__main__":
    main()
