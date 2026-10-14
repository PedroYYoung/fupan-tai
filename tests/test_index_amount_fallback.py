# -*- coding: utf-8 -*-
"""指数成交额降级机制回归测试。

链路：index_mod.get_index_amount_resilient → build.fetch_index_rows → daily.widebase
目标：单个指数当日取不到值时，不得让矩阵整格空白（amount=null）；
      依次降级为「最近交易日真实值」→「同标的 ETF 代理」，全失败才置空。
"""
import pytest

from modules import index_mod


def _no_today(monkeypatch):
    monkeypatch.setattr(index_mod, "get_index_amount", lambda c, d: None)


def test_resilient_uses_today_when_available(monkeypatch):
    """当日抓取成功 → 原样返回，note 为空（不降级）。"""
    monkeypatch.setattr(index_mod, "get_index_amount", lambda c, d: 3684.51)
    assert index_mod.get_index_amount_resilient("sh000300", "20261014") == (
        3684.51, "20261014", "")


def test_resilient_falls_back_to_last_known(monkeypatch):
    """当日失败 → 复用最近一个已收盘交易日的真实值，并标注来源日期。"""
    _no_today(monkeypatch)
    amt, adate, note = index_mod.get_index_amount_resilient(
        "sh932000", "20261014", last_known=(1508.17, "20260925"))
    assert amt == pytest.approx(1508.17)
    assert adate == "20260925"
    assert note == "last_trading_day"


def test_resilient_rejects_future_last_known(monkeypatch):
    """last_known 日期晚于目标交易日时拒绝使用，避免写入「未来数据」。"""
    _no_today(monkeypatch)
    monkeypatch.setattr(index_mod, "get_etf_proxy_amount", lambda c, d: None)
    assert index_mod.get_index_amount_resilient(
        "sh932000", "20261014", last_known=(1508.17, "20261020")) == (None, None, "")


def test_resilient_etf_proxy_is_last_resort(monkeypatch):
    """最近交易日也没有时才用 ETF 代理，且必须标注 etf_proxy。"""
    _no_today(monkeypatch)
    monkeypatch.setattr(index_mod, "get_etf_proxy_amount", lambda c, d: 5.41)
    assert index_mod.get_index_amount_resilient("sh932000", "20261014") == (
        5.41, "20261014", "etf_proxy")


def test_resilient_all_fail_returns_empty(monkeypatch):
    _no_today(monkeypatch)
    monkeypatch.setattr(index_mod, "get_etf_proxy_amount", lambda c, d: None)
    assert index_mod.get_index_amount_resilient("sh932000", "20261014") == (None, None, "")


def test_etf_proxy_only_for_configured_codes():
    """未配置代理的代码不走 ETF 通道，避免用 ETF 值顶替真实指数成交额。"""
    assert "sh932000" in index_mod._ETF_PROXY_BS
    assert index_mod.get_etf_proxy_amount("sh000300", "20261014") is None
    assert index_mod.get_etf_proxy_amount("sh000985", "20261014") is None


def test_sh932000_not_in_tencent_whitelist():
    """sh932000 在腾讯无对应符号（实测返回空壳），改由 ETF 代理兜底。"""
    assert "sh932000" not in index_mod._TENCENT_ENABLED
    assert "sh932000" in index_mod._ETF_PROXY_BS
