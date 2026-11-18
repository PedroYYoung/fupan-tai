# -*- coding: utf-8 -*-
"""涨跌停自愈路径：真实 0 跌停日必须即时声明，防止滑出豁免窗口后 CI 误判。

根因（2026-11-18 build 失败）：build.py 主构建路径会在真实 0 跌停时声明到
backfill.filled_dates，但 backfill.py 的 heal_recent_limit_pools 自愈回补历史日
时写入 0 却未声明。20261110/20261111 由自愈回补产生，滑出「最近 N 交易日」窗口后
被 test_no_zero_substitution_for_missing_days 判为「失败写 0」，导致 pytest 失败。
"""
import json
import os

from modules import backfill, common


def _ld_path():
    # 运行时读取 DATA_DIR：conftest 的 fixture 已把它重定向到临时目录
    return os.path.join(common.DATA_DIR, "series", "limit_down.json")


def _write_ld(obj):
    with open(_ld_path(), "w", encoding="utf-8") as f:
        json.dump(obj, f)


def _read_ld():
    with open(_ld_path(), encoding="utf-8") as f:
        return json.load(f)


def test_heal_declares_real_zero_down_and_keeps_count_consistent():
    """自愈回补的真实 0 跌停日被声明，且 filled_days 与 filled_dates 同步、排序、幂等"""
    _write_ld({
        "key": "limit_down",
        "backfill": {"filled_days": 1, "nonzero_days": 0,
                     "filled_dates": ["20261105"]},
        "points": [],
    })

    backfill._declare_zero_down_from_heal(["20261110", "20261111", "20261105"])

    obj = _read_ld()
    bf = obj["backfill"]
    assert bf["filled_dates"] == ["20261105", "20261110", "20261111"]
    assert bf["filled_days"] == 3
    # 幂等：再次声明不产生重复、不改变计数
    backfill._declare_zero_down_from_heal(["20261110"])
    assert _read_ld()["backfill"]["filled_days"] == 3


def test_heal_declaration_ignores_empty_input():
    """空输入不得改动数据文件，避免无意义重写"""
    _write_ld({"key": "limit_down",
               "backfill": {"filled_days": 0, "nonzero_days": 0, "filled_dates": []},
               "points": []})
    before = _read_ld()
    backfill._declare_zero_down_from_heal([])
    assert _read_ld() == before
