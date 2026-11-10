# -*- coding: utf-8 -*-
"""恢复被增量构建抹掉的序列口径元信息（幂等）。

事故：`compute.write_series_merge` 早期实现只写 key/name/unit/updated_at/points，
每次增量都会把 coverage_start / note / demo_removed 这类**口径声明**抹掉——
于是「只有 4 个真实点」的微盘代理序列，在前端看起来像一条全长历史曲线。

代码已修（meta 继承 + 样本 <30 排名置空），本脚本负责把已被抹掉的历史声明补回来。
数值全部来自本轮整治的实际审计结果（repair_demo_residue.py 的删除记录）：
  micro_proxy  1636 → 3   （删 1633 个 make_sample_data 合成点，20200102~20260924）
  bj899050     1637 → 4   （删 1633）
  sh000688     1638 → 1460（删 178，20260105~20260924）
  sh932000     2852 → 2674（删 178，20260105~20260924）

运行：python scripts/repair_series_meta.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.common import DATA_DIR, atomic_write_json, log  # noqa: E402

SERIES = os.path.join(DATA_DIR, "series")

SPEC = {
    "index_amount_micro_proxy": {
        "source": "real_collected",
        "note": "自建微盘代理＝全A按总市值升序后10%的等权平均成交额（亿元/只），"
                "仅自 20261014 起有真实采集；此前无可靠历史源，已移除全部示例数据，"
                "不做平滑、不做回填。样本 <30 时排名/百分位留空。",
        "demo_removed": {"range": ["20200102", "20260924"], "count": 1633,
                         "reason": "make_sample_data.py 合成的示例数据"},
    },
    "index_amount_bj899050": {
        "source": "real_collected",
        "note": "北证50指数成交额：该指数 2022-11-21 才发布，2020~2022 无真实数据；"
                "早期历史为示例数据，已全部移除，仅保留真实采集点。",
        "demo_removed": {"range": ["20200102", "20260924"], "count": 1633,
                         "reason": "make_sample_data.py 合成的示例数据"},
    },
    "index_amount_sh000688": {
        "source": "real_collected",
        "note": "科创50指数成交额：2020-2025 为真实回补值；2026 年内（0105~0924）早期"
                "被示例数据覆盖，已移除并保留缺口（不做伪造）。",
        "demo_removed": {"range": ["20260105", "20260924"], "count": 178,
                         "reason": "make_sample_data.py 合成的示例数据"},
    },
    "index_amount_sh932000": {
        "source": "real_collected",
        "note": "中证2000指数成交额：2015-2025 为真实回补值；2026 年内（0105~0924）早期"
                "被示例数据覆盖，已移除并保留缺口（不做伪造）。",
        "demo_removed": {"range": ["20260105", "20260924"], "count": 178,
                         "reason": "make_sample_data.py 合成的示例数据"},
    },
}


def main():
    fixed = []
    for key, spec in SPEC.items():
        p = os.path.join(SERIES, f"{key}.json")
        if not os.path.exists(p):
            log(f"{key}: 文件不存在，跳过")
            continue
        with open(p, encoding="utf-8") as f:
            obj = json.load(f)
        pts = obj.get("points") or []
        if not pts:
            log(f"{key}: 无数据点，跳过")
            continue
        changed = False
        for k, v in spec.items():
            if k not in obj:
                obj[k] = v
                changed = True
        for k, v in (("coverage_start", min(x["date"] for x in pts)),
                     ("coverage_end", max(x["date"] for x in pts)),
                     ("sample_n", len(pts))):
            if obj.get(k) != v:
                obj[k] = v
                changed = True
        if changed:
            atomic_write_json(p, obj)
            fixed.append(key)
    log(f"序列口径元信息恢复：{len(fixed)} 个 {fixed}")


if __name__ == "__main__":
    main()
