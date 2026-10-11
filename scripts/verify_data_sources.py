# -*- coding: utf-8 -*-
"""独立行情数据源真实网络验证（不修改数据文件）。"""
import datetime
import io
import json
import sys
import traceback

import requests

LOG_BUF = io.StringIO()
OLD_STDOUT = sys.stdout
OLD_STDERR = sys.stderr
sys.stdout = LOG_BUF
sys.stderr = LOG_BUF

try:
    sys.path.insert(0, __file__.replace("verify_data_sources.py", ""))
    from modules.common import log  # noqa: E402
except Exception as e:
    print("IMPORT ERROR:", e)
    traceback.print_exc()

def _infer_target_date() -> str:
    """以腾讯上证指数返回的行情日期作为目标交易日（避免非交易日用昨天）。"""
    try:
        r = requests.get("https://qt.gtimg.cn/q=sh000001",
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        r.encoding = "gbk"
        for line in r.text.strip().split(";"):
            if 'v_sh000001="' in line:
                f = line.split('"')[1].split("~")
                if len(f) > 30 and f[30] and len(f[30]) >= 8:
                    return f[30][:8]
    except Exception as e:  # noqa: BLE001
        print(f"推断目标日期失败({e})，回退到昨天", file=sys.stderr)
    return (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y%m%d")


TARGET = _infer_target_date()
DATE_HYPHEN = f"{TARGET[:4]}-{TARGET[4:6]}-{TARGET[6:]}"
RESULTS = []


def flush_log():
    os.makedirs("scripts/_cache", exist_ok=True)
    with open("scripts/_cache/verify_data_sources.log", "w", encoding="utf-8") as f:
        f.write(LOG_BUF.getvalue())


def section(title: str):
    print(f"\n{'='*20} {title} {'='*20}")
    flush_log()


def record(source: str, endpoint: str, ok: bool, fields: dict = None, note: str = ""):
    item = {"source": source, "endpoint": endpoint, "ok": ok,
            "fields": fields or {}, "note": note, "checked_at": datetime.datetime.now().isoformat()}
    RESULTS.append(item)
    status = "OK" if ok else "FAIL"
    print(f"[{status}] {source} | {endpoint}")
    if fields:
        for k, v in fields.items():
            print(f"    {k}: {v}")
    if note:
        print(f"    note: {note}")
    flush_log()


def test_sina_realtime():
    section("Sina 实时行情")
    url = "https://hq.sinajs.cn/list=sh600519,sz000858,sz300750,sh000001,sz399001,sz399006"
    try:
        r = requests.get(url, headers={"Referer": "https://finance.sina.com.cn"}, timeout=15)
        r.encoding = "gbk"
        body = r.text
        print(f"status={r.status_code}, len={len(body)}")
        print(body[:600])
        samples = []
        for line in body.split(";"):
            if "=" not in line or "var hq_str_" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.replace("var hq_str_", "").strip()
            val = val.strip('"').split(",")
            samples.append((key, len(val), val[0] if val else ""))
        record("新浪实时行情", url, len(samples) >= 3,
               {"samples": samples, "status": r.status_code},
               "字段位置：个股 sh600519 共 ~33 字段；指数仅名称+点数+成交额等部分字段")
    except Exception as e:  # noqa: BLE001
        record("新浪实时行情", url, False, note=f"异常: {type(e).__name__} {e}")


def test_tencent_realtime():
    section("腾讯实时行情")
    codes = "sh000001,sz399001,sz399006,sh000688,bj899050,sh000016,sh000300,sh600519,sz000858,sz300750"
    url = f"https://qt.gtimg.cn/q={codes}"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        r.encoding = "gbk"
        body = r.text
        print(f"status={r.status_code}, len={len(body)}")
        print(body[:1200])
        samples = []
        for line in body.strip().split(";"):
            if "=" not in line:
                continue
            head, tail = line.split("=", 1)
            code = head.split("_")[-1]
            f = tail.strip('"').split("~")
            info = {"code": code, "name": f[1] if len(f) > 1 else None,
                    "close": f[3] if len(f) > 3 else None,
                    "change_pct": f[32] if len(f) > 32 else None,
                    "amount_yi": round(float(f[37]) / 1e4, 2) if len(f) > 37 and f[37] else None,
                    "float_mktcap_yi": f[44] if len(f) > 44 else None,
                    "mktcap_yi": f[45] if len(f) > 45 else None,
                    "quote_date": f[30][:8] if len(f) > 30 and f[30] else None,
                    "len": len(f)}
            samples.append(info)
        # 校验：所有指数的行情日期必须与目标交易日一致（实时快照不能补造历史）
        index_codes = {"sh000001", "sz399001", "sz399006", "sh000688", "bj899050", "sh000016", "sh000300"}
        date_ok = all(s.get("quote_date") == TARGET for s in samples if s["code"] in index_codes and s.get("quote_date"))
        record("腾讯实时行情", url, len(samples) == 10 and date_ok,
               {"samples": samples, "status": r.status_code},
               "f[1]名称 f[3]最新价 f[30]行情时间 f[32]涨跌幅 f[37]成交额(万元) f[44]流通市值(亿) f[45]总市值(亿)")
    except Exception as e:  # noqa: BLE001
        record("腾讯实时行情", url, False, note=f"异常: {type(e).__name__} {e}")


def test_tencent_all_index_amounts():
    section("腾讯全量宽基指数成交额")
    from modules.index_mod import INDEX_CODES, _tencent_index_amount
    rows = []
    date_mismatches = []
    for code in INDEX_CODES:
        amt = _tencent_index_amount(code, TARGET)
        rows.append({"code": code, "name": INDEX_CODES[code], "amount_yi": amt})
        if amt is None and code != "sz399673":  # 创业板50 未启用，允许失败
            date_mismatches.append(code)
    ok = len([r for r in rows if r["amount_yi"] is not None]) >= len(INDEX_CODES) - 2
    record("腾讯全量宽基指数成交额", "modules.index_mod._tencent_index_amount", ok,
           {"rows": rows},
           f"已启用腾讯通道的指数均返回有效成交额；未启用/失败: {date_mismatches}")


def test_baostock_index_amount():
    section("baostock 指数日线")
    try:
        import baostock as bs
        lg = bs.login()
        print("baostock login", lg.error_code)
        try:
            rs = bs.query_history_k_data_plus("sh.000001",
                "date,open,high,low,close,volume,amount,turn,pctChg",
                start_date=DATE_HYPHEN, end_date=DATE_HYPHEN, frequency="d")
            rows = []
            while rs.next():
                rows.append(rs.get_row_data())
            ok = len(rows) > 0
            record("baostock 上证指数日线", "sh.000001", ok,
                   {"rows": rows[:2]},
                   "amount 字段为成交额（元），需 /1e8 得亿元")
        finally:
            bs.logout()
    except Exception as e:  # noqa: BLE001
        record("baostock 上证指数日线", "sh.000001", False, note=f"异常: {type(e).__name__} {e}")


def test_sse_margin_signature():
    section("上交所两融函数签名")
    try:
        import akshare as ak
        for call_name, kwargs in [
            ("date=", {"date": DATE_HYPHEN}),
            ("无参", {}),
            ("start/end_date", {"start_date": TARGET, "end_date": TARGET}),
        ]:
            try:
                df = ak.stock_margin_sse(**kwargs)
                record("AKShare stock_margin_sse", call_name, True,
                       {"columns": list(df.columns), "rows": len(df), "head": df.head(2).to_dict(orient="records")},
                       f"签名可用，参数={kwargs}")
                break
            except TypeError as e:
                record("AKShare stock_margin_sse", call_name, False, note=f"TypeError: {e}")
                continue
            except Exception as e:  # noqa: BLE001
                record("AKShare stock_margin_sse", call_name, False,
                       note=f"请求异常（非签名）: {type(e).__name__} {e}")
                break
    except ImportError:
        record("AKShare stock_margin_sse", "akshare not installed", False)


def test_szse_margin():
    section("深交所两融")
    try:
        import akshare as ak
        for sig, kw in [("date=", {"date": DATE_HYPHEN}), ("无参", {}), ("start/end_date", {"start_date": TARGET, "end_date": TARGET})]:
            try:
                df = ak.stock_margin_szse(**kw)
                record("AKShare stock_margin_szse", sig, True,
                       {"columns": list(df.columns), "rows": len(df), "head": df.head(2).to_dict(orient="records")},
                       f"参数={kw}")
                break
            except TypeError as e:
                record("AKShare stock_margin_szse", sig, False, note=f"TypeError: {e}")
                continue
            except Exception as e:  # noqa: BLE001
                record("AKShare stock_margin_szse", sig, False, note=f"请求异常: {type(e).__name__} {e}")
                break
    except ImportError:
        record("AKShare stock_margin_szse", "akshare not installed", False)


def test_ak_index_hist():
    section("AKShare index_zh_a_hist（东财系，仅作对比）")
    try:
        import akshare as ak
        df = ak.index_zh_a_hist(symbol="000001", period="daily", start_date=TARGET, end_date=TARGET)
        record("AKShare index_zh_a_hist(000001)", "东财系", bool(len(df)),
               {"columns": list(df.columns), "rows": len(df)},
               "字段名‘成交额’，单位元")
    except Exception as e:  # noqa: BLE001
        record("AKShare index_zh_a_hist", "东财系", False, note=f"异常: {type(e).__name__} {e}")


def test_ak_spot():
    section("AKShare stock_zh_a_spot_em（东财系）")
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        record("AKShare stock_zh_a_spot_em", "东财", bool(len(df)),
               {"rows": len(df), "columns": list(df.columns)[:10]},
               "本机已被封；CI 目前失败")
    except Exception as e:  # noqa: BLE001
        record("AKShare stock_zh_a_spot_em", "东财", False, note=f"异常: {type(e).__name__} {e}")


def main():
    print(f"验证日期: {TARGET} ({DATE_HYPHEN})")
    flush_log()
    test_sina_realtime()
    test_tencent_realtime()
    test_baostock_index_amount()
    test_sse_margin_signature()
    test_szse_margin()
    test_ak_index_hist()
    test_ak_spot()
    section("验证汇总")
    ok = sum(1 for r in RESULTS if r["ok"])
    total = len(RESULTS)
    print(f"通过 {ok}/{total}")
    with open("scripts/_cache/verify_data_sources_report.json", "w", encoding="utf-8") as f:
        json.dump({"target": TARGET, "ok": ok, "total": total, "results": RESULTS}, f, ensure_ascii=False, indent=2)
    print("报告已写入 scripts/_cache/verify_data_sources_report.json")
    sys.stdout = OLD_STDOUT
    sys.stderr = OLD_STDERR
    print(LOG_BUF.getvalue())


if __name__ == "__main__":
    main()
