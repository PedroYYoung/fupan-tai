# -*- coding: utf-8 -*-
"""指数成交额降级机制回归测试。

链路：index_mod.get_index_amount_resilient → build.fetch_index_rows → daily.widebase
目标：单个指数当日取不到值时，不得让矩阵整格空白（amount=null）；
      依次降级为「最近交易日真实值」→「同标的 ETF 代理」，全失败才置空。

新增边界（20261020 实测暴露）：降级复用必须有时效闸门。sh932000 的序列止于
20251231（2026 年段为已删除的合成数据），若「最近值」可以无限往前取，就会把
9 个月前的 5040.02 亿显示成当日成交额 —— 这不是降级，是陈旧数据冒充当日值。
因此超过 MAX_STALE_DAYS 的最近值必须拒绝，宁可整格空白。
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
    """当日失败且最近值足够近（1 天）→ 复用之，并标注来源日期。"""
    _no_today(monkeypatch)
    amt, adate, note = index_mod.get_index_amount_resilient(
        "sh932000", "20261014", last_known=(1508.17, "20261013"))
    assert amt == pytest.approx(1508.17)
    assert adate == "20261013"
    assert note == "last_trading_day"


def test_resilient_rejects_stale_last_known(monkeypatch):
    """最近值滞后超过 MAX_STALE_DAYS → 拒绝复用，改走 ETF 代理或置空。

    真实案例：20261014 的 sh932000 只能拿到 20260925 的值（滞后 19 天）。
    """
    _no_today(monkeypatch)
    monkeypatch.setattr(index_mod, "get_etf_proxy_amount", lambda c, d: None)
    assert index_mod.get_index_amount_resilient(
        "sh932000", "20261014", last_known=(1508.17, "20260925")) == (None, None, "")


def test_resilient_stale_falls_through_to_etf_proxy(monkeypatch):
    """陈旧最近值被拒绝后，仍然允许 ETF 代理兜底（并标注 etf_proxy）。"""
    _no_today(monkeypatch)
    monkeypatch.setattr(index_mod, "get_etf_proxy_amount", lambda c, d: 5.41)
    assert index_mod.get_index_amount_resilient(
        "sh932000", "20261014", last_known=(1508.17, "20251231")) == (
        5.41, "20261014", "etf_proxy")


def test_stale_threshold_is_defined():
    """闸门阈值必须有明确常量，便于审计与调参（当前 10 自然日）。"""
    assert isinstance(index_mod.MAX_STALE_DAYS, int)
    assert 1 <= index_mod.MAX_STALE_DAYS <= 30
    assert index_mod._days_between("20251231", "20261020") == 293
    assert index_mod._days_between("bad", "20261020") is None


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
