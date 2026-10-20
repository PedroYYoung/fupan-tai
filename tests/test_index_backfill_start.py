# -*- coding: utf-8 -*-
"""指数回补起点配置测试。

目的：确保 backfill_real.py 的 --stage index 使用按指数配置的历史起点，
不会用统一 2015-01-01 覆盖已经回补的 1997~2014 历史。
"""
from backfill_real import INDEX_START, INDEX_START_BY_CODE, index_start_for


def test_default_start_is_2015():
    assert INDEX_START == "2015-01-01"


def test_per_index_starts_exact():
    expected = {
        "sh000001": "1997-01-01",
        "sz399001": "1997-01-01",
        "sz399006": "2010-06-01",
        "sh000016": "2004-01-01",
        "sh000300": "2005-01-01",
        "sz399673": "2014-06-18",
        "sh000905": "2005-01-01",
        "sh000906": "2007-01-01",
    }
    assert INDEX_START_BY_CODE == expected


def test_known_codes_use_configured_start():
    assert index_start_for("sh000001") == "1997-01-01"
    assert index_start_for("sz399001") == "1997-01-01"
    assert index_start_for("sh000300") == "2005-01-01"
    assert index_start_for("sz399673") == "2014-06-18"


def test_unconfigured_codes_fall_back_to_2015():
    # sh000852 因 2011 年数据缺口不纳入；未验证/派生代码一律回退默认
    for code in ("sh000852", "sh000688", "bj899050", "sh932000",
                 "hstech_513180", "micro_proxy", "unknown"):
        assert index_start_for(code) == "2015-01-01"
