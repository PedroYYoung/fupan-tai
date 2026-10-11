#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复盘台 · 自选股行情更新（quotes.json）

数据源：AKShare stock_zh_a_spot_em() 全市场快照，按 public/data/stocks.json
中的自选股清单过滤。失败时保留旧文件（不覆盖），与 build.py 同一套容错约定：
写 .tmp 校验后原子替换；任何失败只打印日志并 exit 0，网站继续显示上一份数据。

自选股维护方式：直接编辑 public/data/stocks.json：
  {"stocks": [{"code": "000001", "name": "平安银行"}, ...]}
"""
import json
import os
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)
DATA_DIR = os.path.join(REPO_ROOT, "public", "data")
STOCKS_FILE = os.path.join(DATA_DIR, "stocks.json")
QUOTES_FILE = os.path.join(DATA_DIR, "quotes.json")

sys.path.insert(0, HERE)
from modules.common import atomic_write_json, log  # noqa: E402


def load_watchlist() -> list:
    """读取自选股清单；文件缺失/损坏时返回空列表（页面显示空态而非报错）"""
    try:
        with open(STOCKS_FILE, "r", encoding="utf-8") as f:
            stocks = json.load(f).get("stocks", [])
        return [s for s in stocks if s.get("code") and s.get("name")]
    except Exception as e:
        log(f"自选股清单读取失败: {e}")
        return []


def fetch_quotes(watchlist: list) -> list:
    """按清单取最新价/涨跌幅：东财快照（主）→ 腾讯批量（备）；均失败返回 None（保留旧数据）"""
    quotes = None
    # 主源：AKShare 东财全市场快照
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        quotes = []
        for stock in watchlist:
            row = df[df["代码"] == stock["code"]]
            if row.empty:
                # 退市/停牌/代码错误：保留条目、值为 null（契约：null 表示缺失而非 0）
                quotes.append({"code": stock["code"], "name": stock["name"],
                               "price": None, "change": None})
                continue
            r = row.iloc[0]
            try:
                price = float(r["最新价"])
                change = float(r["涨跌幅"])
            except (TypeError, ValueError):
                price, change = None, None
            quotes.append({"code": stock["code"], "name": stock["name"],
                           "price": price, "change": change})
    except Exception as e:  # noqa: BLE001
        log(f"AKShare 快照接口失败（尝试腾讯备源）：{e}")

    # 备源：腾讯批量行情（本地网络对东财受限时的稳定通道）
    if quotes is None:
        try:
            import requests
            codes = []
            for w in watchlist:
                pre = "sh" if w["code"].startswith("6") else (
                    "sz" if w["code"].startswith(("0", "3")) else "bj")
                codes.append(pre + w["code"])
            s = requests.Session()
            s.trust_env = False
            r = s.get(f"https://qt.gtimg.cn/q={','.join(codes)}",
                      headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            r.encoding = "gbk"
            by_code = {}
            for line in r.text.strip().split(";"):
                if "=" not in line:
                    continue
                f = line.split("=", 1)[1].strip('"').split("~")
                if len(f) > 33 and f[2]:
                    by_code[f[2]] = (f[1], f[3], f[32])
            quotes = []
            for w in watchlist:
                t = by_code.get(w["code"])
                if t:
                    try:
                        quotes.append({"code": w["code"], "name": t[0],
                                       "price": float(t[1]) if t[1] else None,
                                       "change": float(t[2]) if t[2] else None})
                    except ValueError:
                        quotes.append({"code": w["code"], "name": t[0],
                                       "price": None, "change": None})
                else:
                    quotes.append({"code": w["code"], "name": w["name"],
                                   "price": None, "change": None})
            log("已使用腾讯备源获取自选股行情")
        except Exception as e:  # noqa: BLE001
            log(f"腾讯备源也失败：{e}")
            return None
    return quotes


def main() -> int:
    watchlist = load_watchlist()
    if not watchlist:
        log("自选股清单为空，跳过更新（保留旧 quotes.json）")
        return 0
    quotes = fetch_quotes(watchlist)
    if quotes is None:
        log("行情获取失败，保留旧 quotes.json")
        return 0
    payload = {"date": datetime.now().strftime("%Y-%m-%d"), "quotes": quotes}
    atomic_write_json(QUOTES_FILE, payload)
    ok = sum(1 for q in quotes if q["price"] is not None)
    log(f"quotes.json 更新完成：{ok}/{len(quotes)} 只有效行情，日期 {payload['date']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
