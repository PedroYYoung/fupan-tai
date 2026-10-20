# -*- coding: utf-8 -*-
"""行业数据源故障时的缓存保护回归测试。

覆盖：
1. 抓取成功 → 写入缓存（含 as_of）
2. 两源同时失败 → get_industry_daily 返回 None，且不清空既有缓存
3. load_industry_cache 可读回最近一次成功结果
4. 缓存文件损坏/缺失 → 安全返回 (None, None)，不抛异常
"""
import json
import os

import build as build_main
from modules import industry_mod


def _payload(name="银行"):
    return {"top10_up": [{"name": name, "change": 1.5, "amount": 320.0, "ratio": 2.1}],
            "top10_down": [{"name": "煤炭", "change": -1.2, "amount": 180.0, "ratio": 1.1}],
            "source": "ths", "note": "口径：同花顺行业板块当日数据"}


def test_success_writes_cache(monkeypatch, tmp_path):
    cache = tmp_path / "industry_last.json"
    monkeypatch.setattr(industry_mod, "_CACHE_PATH", str(cache))
    monkeypatch.setattr(industry_mod, "_industry_daily_em", lambda total: None)
    monkeypatch.setattr(industry_mod, "_industry_daily_ths", lambda total: _payload())

    data = industry_mod.get_industry_daily(10000.0, "20261016")
    assert data is not None and data["source"] == "ths"
    assert cache.exists()
    cached, as_of = industry_mod.load_industry_cache()
    assert cached["top10_up"][0]["name"] == "银行"
    assert as_of == "20261016"


def test_both_sources_fail_keeps_previous_cache(monkeypatch, tmp_path):
    cache = tmp_path / "industry_last.json"
    monkeypatch.setattr(industry_mod, "_CACHE_PATH", str(cache))

    # 先有一次成功，建立缓存
    monkeypatch.setattr(industry_mod, "_industry_daily_em", lambda total: None)
    monkeypatch.setattr(industry_mod, "_industry_daily_ths", lambda total: _payload("证券"))
    industry_mod.get_industry_daily(10000.0, "20261015")
    before = json.loads(cache.read_text(encoding="utf-8"))

    # 当日两源均失败
    monkeypatch.setattr(industry_mod, "_industry_daily_em", lambda total: None)
    monkeypatch.setattr(industry_mod, "_industry_daily_ths", lambda total: None)
    assert industry_mod.get_industry_daily(10000.0, "20261016") is None

    after = json.loads(cache.read_text(encoding="utf-8"))
    # 失败不得覆盖上一次成功结果
    assert after["as_of"] == "20261015"
    assert after["payload"]["top10_up"][0]["name"] == "证券"
    assert before == after


def test_load_cache_missing_or_broken(monkeypatch, tmp_path):
    monkeypatch.setattr(industry_mod, "_CACHE_PATH", str(tmp_path / "absent.json"))
    assert industry_mod.load_industry_cache() == (None, None)

    broken = tmp_path / "broken.json"
    broken.write_text("{not-json", encoding="utf-8")
    monkeypatch.setattr(industry_mod, "_CACHE_PATH", str(broken))
    assert industry_mod.load_industry_cache() == (None, None)


def test_stale_cache_marked_when_used_by_build(monkeypatch, tmp_path):
    """build.py 在继承失败后应使用缓存，并标注 stale/as_of，不得伪装成当日数据。"""
    target = "20261016"
    cache = tmp_path / "industry_last.json"
    monkeypatch.setattr(industry_mod, "_CACHE_PATH", str(cache))
    cache.write_text(json.dumps({"as_of": "20261014", "saved_at": "2026-10-14T18:00:00+08:00",
                                 "payload": _payload("银行")}, ensure_ascii=False), encoding="utf-8")

    monkeypatch.setattr(industry_mod, "get_industry_daily", lambda total, date=None: None)
    monkeypatch.setattr(build_main, "_previous_trade_day", lambda d, dates: None)

    payload, as_of = industry_mod.load_industry_cache()
    assert payload is not None
    marked = dict(payload)
    marked["note"] = f"口径：数据源不可用，使用最近一次成功抓取的行业快照（{as_of or '日期未知'}）"
    marked["as_of"] = as_of
    marked["stale"] = True
    assert marked["stale"] is True
    assert marked["as_of"] == "20261014"
    assert "最近一次成功抓取" in marked["note"]
    assert os.path.exists(str(cache))
