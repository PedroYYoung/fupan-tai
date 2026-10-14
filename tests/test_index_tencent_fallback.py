# -*- coding: utf-8 -*-
"""指数成交额备用通道回归测试：腾讯字段位置、单位换算、日期校验、异常值拒绝。"""
import pytest

from modules import index_mod


def _quote(code, name, price, ts, amount_wan, mktcap_yi=100.0):
    """构造一条腾讯行情响应。"""
    f = [""] * 49
    f[1], f[2] = name, code[2:] if not code.startswith("sh513") else code[2:]
    f[3] = str(price)
    f[30] = ts
    f[32] = "0.55"
    f[37] = str(amount_wan)
    f[44] = f[45] = str(mktcap_yi)
    return f'v_{code}="{"~".join(f)}";'


def _fake_get(url, headers=None, timeout=None):
    class R:
        encoding = "gbk"
        text = ""
    code = url.split("q=")[1]
    mapping = {
        "sh000001": ("上证指数", "20261009091500", "12345678"),  # 8885.61 亿
        "sz399001": ("深证成指", "20261009091530", "23456789"),
        "sh513180": ("华夏恒生科技", "20261009091600", "500000"),
    }
    name, ts, amount = mapping.get(code, ("未知", "20261009091500", "0"))
    R.text = _quote(code, name, 100.0, ts, amount)
    return R


def test_parse_tencent_quote_field_positions_and_units():
    body = _quote("sh000001", "上证指数", 3813.79, "20261009161500", "88856120")
    amount, qd, reason = index_mod._parse_tencent_quote(body, "sh000001", "20261009")
    assert amount == pytest.approx(8885.61)
    assert qd == "20261009"
    assert reason == ""


def test_parse_tencent_quote_date_mismatch_returns_none():
    body = _quote("sh000001", "上证指数", 3813.79, "20261008161500", "88856120")
    amount, qd, reason = index_mod._parse_tencent_quote(body, "sh000001", "20261009")
    assert amount is None
    assert qd == "20261008"
    assert "不匹配" in reason


def test_parse_tencent_quote_rejects_empty_amount():
    body = _quote("sh000001", "上证指数", 3813.79, "20261009161500", "0")
    amount, qd, reason = index_mod._parse_tencent_quote(body, "sh000001", "20261009")
    assert amount is None
    assert "成交额为空" in reason


def test_parse_tencent_quote_rejects_abnormal_amount():
    body = _quote("sh000001", "上证指数", 3813.79, "20261009161500", "9999999999999")
    amount, qd, reason = index_mod._parse_tencent_quote(body, "sh000001", "20261009")
    assert amount is None
    assert "异常" in reason


def test_tencent_index_amount_not_enabled_returns_none():
    """未在 _TENCENT_ENABLED 中的代码不应走腾讯通道。
    注意：sz399673 已在 a82be23 加入白名单，故改用明确不在白名单内的 sh000999 作哨兵，
    既验证白名单过滤逻辑，又避免测试依赖真实网络。"""
    assert "sh000999" not in index_mod._TENCENT_ENABLED
    amount = index_mod._tencent_index_amount("sh000999", "20261009")
    assert amount is None


def test_tencent_fallback_success(monkeypatch):
    """东财失败 → 腾讯备用通道返回正确亿元值。"""
    import akshare as ak
    monkeypatch.setattr(ak, "index_zh_a_hist", lambda **kw: _raise(ValueError("东财挂了"))())
    monkeypatch.setattr(index_mod.requests, "get", _fake_get)

    amount = index_mod.get_index_amount("sh000001", "20261009")
    assert amount == pytest.approx(1234.57)


def test_tencent_hstech_etf_mapping(monkeypatch):
    """恒生科技 ETF 代码映射为 sh513180。"""
    import akshare as ak
    monkeypatch.setattr(ak, "fund_etf_hist_em", lambda **kw: _raise(ValueError("东财挂了"))())
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return _fake_get(url)

    monkeypatch.setattr(index_mod.requests, "get", fake_get)
    amount = index_mod.get_index_amount("hstech_513180", "20261009")
    assert amount == pytest.approx(50.0)
    assert any("sh513180" in c for c in calls)


def _raise(exc):
    def _fn(*args, **kwargs):
        raise exc
    return _fn
