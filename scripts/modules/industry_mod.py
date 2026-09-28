# -*- coding: utf-8 -*-
"""行业板块：AKShare stock_board_industry_name_em()（东财行业，当日涨跌+成交额）

口径说明（UI 同步标注）：
- 当日数据：东财行业板块实时快照
- 历史序列：中证/申万指数体系回填；若需严格申万二级成分映射，
  需用户提供「东财行业 ↔ 申万二级」CSV 对齐表后启用 backfill_industry()
"""
import akshare as ak
from .common import retry, log


def get_industry_daily(total_amount: float):
    """返回 {top10_up, top10_down}：[{name, change, amount(亿), ratio(占两市%)}]"""
    try:
        df = retry(lambda: ak.stock_board_industry_name_em(), what="东财行业板块")
    except Exception as e:  # noqa: BLE001
        log(f"行业板块获取失败（保留旧数据）：{e}")
        return None

    df = df.rename(columns={"板块名称": "name", "涨跌幅": "change", "成交额": "amount"})
    df = df.dropna(subset=["change", "amount"])

    def rows(sub):
        out = []
        for _, r in sub.iterrows():
            amt_yi = float(r["amount"]) / 1e8
            out.append({
                "name": str(r["name"]),
                "change": round(float(r["change"]), 2),
                "amount": round(amt_yi, 1),
                "ratio": round(amt_yi / total_amount * 100, 2) if total_amount else 0,
            })
        return out

    top10_up = rows(df.nlargest(10, "change"))
    top10_down = rows(df.nsmallest(10, "change"))
    log(f"行业板块：{df['name'].nunique()} 个，上涨TOP10 首位 {top10_up[0]['name']} {top10_up[0]['change']}%")
    return {"top10_up": top10_up, "top10_down": top10_down}


def backfill_industry(mapping_csv: str, start: str, end: str):
    """（可选）申万二级行业指数历史回填。需用户提供对齐表 CSV：east_name,sw_code,sw_name"""
    import pandas as pd
    from . import compute
    mp = pd.read_csv(mapping_csv)
    log(f"行业历史回填：{len(mp)} 条对齐（{start}~{end}）")
    for _, r in mp.iterrows():
        code = str(r["sw_code"])
        try:
            df = retry(lambda: ak.index_hist_sw(symbol=code, period="day",
                                                start_date=start, end_date=end),
                       what=f"申万{code}")
            pts = [{"date": str(d).replace("-", ""), "value": round(float(v) / 1e8, 2)}
                   for d, v in zip(df["日期"], df["成交额"])]
            for p in pts:
                compute.update_series(f"industry_sw_{code}", str(r["sw_name"]), "亿元", p["date"], p["value"])
        except Exception as e:  # noqa: BLE001
            log(f"申万 {code} 回填失败：{e}")
    log("行业历史回填完成")
