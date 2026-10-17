#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""两融余额历史回填（合并写入，保留原有正确记录，仅修正/补齐错误或缺失日期）。

用法：
  python scripts/backfill_margin.py --start 20260929 --end 20261014

规则：
- 逐交易日取上交所 + 深交所官网真实数据，汇总为两融余额（亿元）
- 按日期 upsert 合并进 data/series/margin.json，重算排名/百分位
- 沪市单位为元（/1e8）、深市单位为亿元（不再除），绝不把单边当双边
- 某一交易所缺失时如实报告，不插值、不复制前值
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules import calendar_mod, compute, margin_mod  # noqa: E402
from modules.common import log  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="两融余额历史回填")
    ap.add_argument("--start", required=True, help="起始交易日 YYYYMMDD")
    ap.add_argument("--end", required=True, help="结束交易日 YYYYMMDD")
    args = ap.parse_args()

    dates = calendar_mod.get_trade_dates()
    window = [d for d in dates if args.start <= d <= args.end]
    if not window:
        log(f"区间 {args.start}~{args.end} 内无交易日")
        return

    log(f"===== 两融回填：{window[0]} ~ {window[-1]}（{len(window)} 个交易日）=====")
    vals = {}
    report = []
    missing = []
    for d in window:
        total, sse, szse, both = margin_mod.get_margin_total(d)
        if total is None:
            missing.append(d)
            report.append((d, None, None, None, "缺失"))
            log(f"{d}: 沪深均无数据，跳过")
            continue
        if not both:
            missing.append(d)
            report.append((d, sse, szse, total, "单边缺失"))
            log(f"{d}: 仅单边（沪={sse} 深={szse}），不写入完整双边总额")
            continue
        vals[d] = total
        report.append((d, sse, szse, total, "OK"))
        log(f"{d}: 沪 {sse} + 深 {szse} = {total} 亿")

    if vals:
        compute.write_series_merge("margin", "两融余额", "亿元", vals)

    # 输出回填明细表
    print("\n===== 回填明细 =====")
    print(f"{'日期':<10}{'沪市(亿)':<12}{'深市(亿)':<12}{'合计(亿)':<12}{'状态':<10}")
    for d, sse, szse, total, st in report:
        print(f"{d:<10}{str(sse):<12}{str(szse):<12}{str(total):<12}{st:<10}")
    print(f"\n回填 {len(vals)} 天，缺失/异常 {len(missing)} 天")


if __name__ == "__main__":
    main()
