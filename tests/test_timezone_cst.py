# -*- coding: utf-8 -*-
"""北京时间与交易日逻辑（专项三）

覆盖：开盘前 / 收盘后 / 跨午夜 / 周末 / 节假日 / UTC 与北京时间不同日的时刻，
以及「实时快照写入闸门」只认最近已收盘交易日。
"""
import datetime

import pytest

import build
from modules.common import CST, now_iso

# 2026-10-19（周一）、2026-10-20（周二）为交易日；10-17/18 为周末
DATES = ["20261015", "20261016", "20261019", "20261020", "20261021"]


def bj(y, m, d, H, M):
    return datetime.datetime(y, m, d, H, M, tzinfo=CST)


def test_before_close_points_to_previous_day():
    """14:59（未收盘）→ 仍是上一交易日，绝不用今天标注未完成的行情"""
    assert build.last_closed_trade_date(DATES, bj(2026, 10, 20, 14, 59)) == "20261019"


def test_at_close_boundary():
    """15:00 整仍在缓冲区内（收盘集合竞价落库），15:05 起视为已收盘"""
    assert build.last_closed_trade_date(DATES, bj(2026, 10, 20, 15, 0)) == "20261019"
    assert build.last_closed_trade_date(DATES, bj(2026, 10, 20, 15, 5)) == "20261020"


def test_after_close_points_to_today():
    assert build.last_closed_trade_date(DATES, bj(2026, 10, 20, 19, 30)) == "20261020"


def test_pre_open_points_to_previous_day():
    """开盘前 09:00 → 上一交易日，不得生成「今日」行情"""
    assert build.last_closed_trade_date(DATES, bj(2026, 10, 20, 9, 0)) == "20261019"


def test_weekend_points_to_friday():
    assert build.last_closed_trade_date(DATES, bj(2026, 10, 17, 12, 0)) == "20261016"
    assert build.last_closed_trade_date(DATES, bj(2026, 10, 18, 23, 0)) == "20261016"


def test_holiday_is_skipped_by_calendar():
    """非交易日（不在交易日历里）不会成为 result，即使时间已过收盘"""
    dates = [d for d in DATES if d != "20261020"]
    assert build.last_closed_trade_date(dates, bj(2026, 10, 20, 20, 0)) == "20261019"


def test_utc_date_differs_from_beijing_date():
    """UTC 10-20 16:30 == 北京 10-21 00:30：业务日期必须仍是 10-20（不被 UTC 拖到前一天）"""
    utc = datetime.datetime(2026, 10, 20, 16, 30, tzinfo=datetime.timezone.utc)
    assert build.last_closed_trade_date(DATES, utc.astimezone(CST)) == "20261020"
    # 同一时刻用 UTC 直接取日期会得到 20261020，但用 UTC 取 08:30 之前的时刻会错成前一天
    utc2 = datetime.datetime(2026, 10, 20, 23, 30, tzinfo=datetime.timezone.utc)  # 北京 10-21 07:30
    assert build.last_closed_trade_date(DATES, utc2.astimezone(CST)) == "20261020"


def test_now_iso_carries_beijing_offset():
    assert now_iso().endswith("+08:00")


@pytest.mark.parametrize("date,expect", [
    ("20261020", True),   # 最近已收盘交易日 → 允许实时快照
    ("20261019", False),  # 历史日 → 禁止用当前 spot 伪造
    ("20261021", False),  # 未来日 → 禁止
])
def test_realtime_gate_only_latest_closed_day(monkeypatch, date, expect):
    monkeypatch.setattr(build, "last_closed_trade_date", lambda dates, now=None: "20261020")
    assert build.is_realtime_session_target(date, DATES) is expect
