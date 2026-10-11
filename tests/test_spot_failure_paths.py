# -*- coding: utf-8 -*-
"""行情通道失败路径回归测试。

覆盖 2026-09-29 起 CI 每日失败的根因：
1. build.py 异常处理调用 notify_failure 时出现 NameError（应为 notify.notify_failure）
2. 东财/efinance 行情接口不可用时的降级与明确失败（SpotFetchError，而非裸异常/无限重试）
3. 腾讯兜底通道的字段解析与单位换算（f[37]万元→元、f[44]/f[45]亿元→元）

测试全部使用 mock/fixture，不产生任何真实网络请求；
fixture 行情仅用于验证解析逻辑，绝不写入产品数据文件。
"""
import json
import sys
import types

import pandas as pd
import pytest

import build as build_main
from modules import notify, spot_mod


# ---------------------------------------------------------------- 工具

def _raise(exc):
    def _fn(*args, **kwargs):
        raise exc
    return _fn


def _json_decode_error():
    return json.JSONDecodeError("Expecting value", "line", 0)


def _make_fake_ef():
    fake_ef = types.ModuleType("efinance")
    fake_ef.stock = types.SimpleNamespace(
        get_realtime_quotes=_raise(_json_decode_error()))
    return fake_ef


# ---------------------------------------------------------------- 腾讯通道 fixture

def _gtimg_line(name, code, price, chg, amount_wan, cap_yi):
    """构造一条 v_shXXXXXX="..." 腾讯行情响应（49 个 ~ 分隔字段）"""
    f = [""] * 49
    f[1], f[2] = name, code
    f[3], f[32] = str(price), str(chg)
    f[37], f[44], f[45] = str(amount_wan), str(cap_yi), str(cap_yi)
    return f'v_sh{code}="{"~".join(f)}";'


class _FakeResp:
    def __init__(self, text):
        self.text = text
        self.encoding = "gbk"


def _make_fake_tencent(monkeypatch, n_codes=1100):
    """mock baostock（成分清单）+ requests.Session（批量行情），返回 n_codes 只 fixture"""
    codes = [f"sh.60{i:04d}" for i in range(n_codes)]  # baostock 格式：sh.600000

    class _RS:
        error_code = "0"

        def __init__(self, rows):
            self._rows = list(rows)

        def next(self):
            return bool(self._rows)

        def get_row_data(self):
            return self._rows.pop(0)

    fake_bs = types.ModuleType("baostock")
    fake_bs.login = lambda: None
    fake_bs.logout = lambda: None
    fake_bs.query_all_stock = lambda day=None: _RS([[c, "1", "N"] for c in codes])
    monkeypatch.setitem(sys.modules, "baostock", fake_bs)

    class _Sess:
        trust_env = True

        def get(self, url, headers=None, timeout=None):
            q = url.split("q=", 1)[1].split(",")
            text = "".join(
                _gtimg_line(f"N{c[2:]}", c[2:], 10.0, 1.23, 50000.0, 100.0)
                for c in q)
            return _FakeResp(text)

    fake_requests = types.ModuleType("requests")
    fake_requests.Session = _Sess
    monkeypatch.setitem(sys.modules, "requests", fake_requests)
    return codes


# ---------------------------------------------------------------- 通道降级

def test_all_sources_fail_raises_spot_fetch_error_not_name_error(monkeypatch):
    """三通道全失败：必须是携带各通道原因的 SpotFetchError，绝不能是 NameError"""
    monkeypatch.setattr(spot_mod.ak, "stock_zh_a_spot_em",
                        _raise(ConnectionError("RemoteDisconnected")))
    monkeypatch.setitem(sys.modules, "efinance", _make_fake_ef())
    monkeypatch.setattr(spot_mod, "_tencent_spot",
                        _raise(RuntimeError("baostock 挂了")))

    with pytest.raises(spot_mod.SpotFetchError) as ei:
        spot_mod.get_spot("20261009")

    msg = str(ei.value)
    assert "东财" in msg and "efinance" in msg and "腾讯" in msg
    assert "RemoteDisconnected" in msg


def test_get_spot_falls_back_to_tencent(monkeypatch):
    """东财 + efinance 同时失效（CI 实际场景）→ 自动降级腾讯通道并成功"""
    monkeypatch.setattr(spot_mod.ak, "stock_zh_a_spot_em",
                        _raise(ConnectionError("RemoteDisconnected")))
    monkeypatch.setitem(sys.modules, "efinance", _make_fake_ef())
    _make_fake_tencent(monkeypatch)

    df = spot_mod.get_spot("20261009")
    assert len(df) == 1100
    assert set(["code", "name", "close", "change_pct", "amount", "mktcap"]).issubset(df.columns)


def test_normalize_rejects_partial_or_empty_market():
    """源返回残缺数据（缺列/个股数异常）必须视为通道失败，而不是放行"""
    ok = {"代码": ["600000"], "名称": ["浦发银行"], "最新价": [10.0], "涨跌幅": [1.0],
          "成交额": [1e8], "总市值": [1e10]}
    with pytest.raises(ValueError):
        spot_mod._normalize(pd.DataFrame(ok), "测试源")  # 仅 1 只 < _MIN_STOCKS

    no_col = pd.DataFrame({"代码": ["600000"], "名称": ["x"]})
    with pytest.raises(ValueError):
        spot_mod._normalize(no_col, "测试源")  # 缺必需列


def test_tencent_spot_field_positions_and_units(monkeypatch):
    """腾讯字段位置与单位换算回归：f[37]万元→元、f[45]亿元→元、f[32]涨跌幅"""
    _make_fake_tencent(monkeypatch, n_codes=1100)
    df = spot_mod._tencent_spot("20261009")
    row = df[df["code"] == "600000"].iloc[0]
    assert row["amount"] == pytest.approx(50000.0 * 1e4)      # 万元 → 元
    assert row["mktcap"] == pytest.approx(100.0 * 1e8)        # 亿元 → 元
    assert row["float_mktcap"] == pytest.approx(100.0 * 1e8)
    assert row["change_pct"] == pytest.approx(1.23)
    assert row["close"] == pytest.approx(10.0)


# ---------------------------------------------------------------- build.py 异常处理

def test_build_failure_path_notifies_without_name_error(monkeypatch):
    """单日构建失败：record_error + notify.notify_failure 都被调用，不再 NameError"""
    calls = []
    boom = _raise(spot_mod.SpotFetchError("全市场快照三通道均失败"))
    monkeypatch.setattr(build_main.spot_mod, "get_spot", lambda *a, **k: boom())
    monkeypatch.setattr(build_main.calendar_mod, "get_trade_dates",
                        lambda: ["20261009", "20261010"])
    monkeypatch.setattr(build_main, "record_error",
                        lambda msg: calls.append(("record_error", msg)))
    monkeypatch.setattr(build_main.notify, "notify_failure",
                        lambda t, c: calls.append(("notify", t, c)))
    monkeypatch.setattr(sys, "argv", ["build.py", "--date", "20261010"])

    build_main.main()  # 不得抛出任何异常（含 NameError）

    kinds = [c[0] for c in calls]
    assert "record_error" in kinds, "应记录 last_error"
    assert "notify" in kinds, "应推送失败通知"
    assert any("复盘台数据更新失败" in c[1] for c in calls if c[0] == "notify")


def test_build_fatal_path_notifies_without_name_error(monkeypatch):
    """main() 自身抛异常（FATAL）：run() 兜底同样不得 NameError，且返回 0"""
    calls = []
    monkeypatch.setattr(build_main.calendar_mod, "get_trade_dates",
                        _raise(RuntimeError("交易日历接口挂了")))
    monkeypatch.setattr(build_main, "record_error",
                        lambda msg: calls.append(("record_error", msg)))
    monkeypatch.setattr(build_main.notify, "notify_failure",
                        lambda t, c: calls.append(("notify", t, c)))
    monkeypatch.setattr(sys, "argv", ["build.py", "--incremental"])

    assert build_main.run() == 0  # 不得抛出任何异常（含 NameError）
    assert any(c[0] == "notify" and "FATAL" in c[1] for c in calls)


# ---------------------------------------------------------------- notify 自身健壮性

def test_notify_failure_never_raises_even_if_network_down(monkeypatch):
    """通知通道网络失败不得影响构建主流程"""
    monkeypatch.setenv("PUSHPLUS_TOKEN", "fake-token")
    monkeypatch.setenv("SC_SENDKEY", "fake-key")
    fake_requests = types.SimpleNamespace(post=_raise(ConnectionError("network down")))
    monkeypatch.setattr(notify, "requests", fake_requests)
    notify.notify_failure("标题", "内容")  # 只记日志，不抛异常
