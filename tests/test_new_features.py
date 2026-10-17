# -*- coding: utf-8 -*-
"""本次升级新增逻辑回归测试：
1. 科创50/北证50 YTD 口径（上一年度最后交易日为基准）
2. 两融精确回填 get_margin_total（沪+深、单位、双边校验）
3. 涨跌停 5亿/10亿 门槛切分
"""
import pandas as pd
import pytest

from modules import index_mod, margin_mod, zt_mod


# ---------------------------------------------------------------- YTD
def test_ytd_uses_prev_year_last_trade_day_as_base(monkeypatch):
    """YTD = 当日收盘 / 上一年度最后交易日收盘 - 1，基准取上一年最后交易日。"""
    dates = ["20251229", "20251230", "20251231", "20260105", "20261016"]
    closes = {"20251231": 100.0, "20261016": 105.0}
    monkeypatch.setattr(index_mod, "get_index_close", lambda c, d: closes.get(d))
    ytd = index_mod.get_index_ytd_pct("sh000688", "20261016", dates)
    assert ytd == pytest.approx(5.0)


def test_ytd_returns_none_when_base_missing(monkeypatch):
    """基准日收盘缺失时返回 None，绝不硬编码。"""
    dates = ["20251229", "20251230", "20251231", "20260105", "20261016"]
    monkeypatch.setattr(index_mod, "get_index_close", lambda c, d: None)
    assert index_mod.get_index_ytd_pct("bj899050", "20261016", dates) is None


# ---------------------------------------------------------------- 两融
def test_get_margin_total_sums_sse_and_szse(monkeypatch):
    """沪市（元已转亿）+ 深市（亿元）正确汇总，双边齐全。"""
    monkeypatch.setattr(margin_mod, "_fetch_sse_range", lambda s, e: {"20261014": 12990.05})
    monkeypatch.setattr(margin_mod, "_fetch_szse", lambda d: 12280.16)
    total, sse, szse, both = margin_mod.get_margin_total("20261014")
    assert sse == pytest.approx(12990.05)
    assert szse == pytest.approx(12280.16)
    assert total == pytest.approx(25270.21)
    assert both is True


def test_get_margin_total_single_side_not_treated_as_full(monkeypatch):
    """深市缺失时 both=False，不得把单边当完整双边总额。"""
    monkeypatch.setattr(margin_mod, "_fetch_sse_range", lambda s, e: {"20261014": 12990.05})
    monkeypatch.setattr(margin_mod, "_fetch_szse", lambda d: None)
    total, sse, szse, both = margin_mod.get_margin_total("20261014")
    assert sse == pytest.approx(12990.05)
    assert szse is None
    assert both is False


# ---------------------------------------------------------------- 涨跌停门槛
def test_limit_pools_return_full_rows_with_5e_10e(monkeypatch):
    """get_limit_pools 返回完整列表，调用方按 5亿/10亿 切分；含包含关系。"""
    import akshare as ak
    zt_df = pd.DataFrame({
        "代码": ["600000", "000001"],
        "名称": ["浦发银行", "平安银行"],
        "涨跌幅": [10.0, 10.0],
        "成交额": [15e8, 6e8],
    })
    dt_df = pd.DataFrame({
        "代码": ["600001"],
        "名称": ["某股"],
        "涨跌幅": [-10.0],
        "成交额": [20e8],
    })
    monkeypatch.setattr(ak, "stock_zt_pool_em", lambda date=None: zt_df)
    monkeypatch.setattr(ak, "stock_zt_pool_dtgc_em", lambda date=None: dt_df)

    lu, ld, lu_rows, ld_rows = zt_mod.get_limit_pools("20261016")
    assert lu == 2 and ld == 1
    assert sum(1 for r in lu_rows if r["amount"] >= 5) == 2
    assert sum(1 for r in lu_rows if r["amount"] >= 10) == 1
    assert sum(1 for r in ld_rows if r["amount"] >= 5) == 1
    assert sum(1 for r in ld_rows if r["amount"] >= 10) == 1
