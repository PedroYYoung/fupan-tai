# -*- coding: utf-8 -*-
"""指数日线成交额：AKShare index_zh_a_hist（主）/ 腾讯批量行情（备）/ baostock（交叉验证）。
恒生科技以 ETF 513180 成交额近似（UI 标注「近似值」）。
"""
import re
import time

import akshare as ak
import requests

from .common import retry, log

_BS_LOGGED = False

# 行固定：5 指数 + 11 宽基（code: 指数代码）
INDEX_CODES = {
    "sh000001": "上证指数", "sz399001": "深证成指", "sz399006": "创业板指",
    "sh000688": "科创50", "bj899050": "北证50",
    "sh000016": "上证50", "sh000300": "沪深300", "sz399673": "创业板50",
    "sh000905": "中证500", "sh000906": "中证800", "sh000852": "中证1000",
    "sh932000": "中证2000", "sh000985": "中证全指", "hstech_513180": "恒生科技(513180近似)",
}

# 已验证可用腾讯行情的代码（verify_data_sources.py 实测）
# 注：腾讯实时行情实测可覆盖 13/14 代码（含 bj899050 北证50、sh000688 科创50）；
# 仅 sh932000(中证2000) 在腾讯无对应符号，改由中证指数官网 tradingValue 通道补齐。
_TENCENT_ENABLED = {
    "sh000001", "sz399001", "sz399006", "sh000688", "bj899050",
    "sh000016", "sh000300", "sz399673", "sh000905", "sh000906",
    "sh000852", "sh932000", "sh000985", "hstech_513180",
}

# 腾讯行情代码映射：去掉 sh/sz/bj 前缀；ETF 特殊处理
_TENCENT_CODE_MAP = {
    "hstech_513180": "sh513180",
}


def _tencent_code(code: str) -> str:
    return _TENCENT_CODE_MAP.get(code, code)


def _parse_tencent_quote(body: str, code: str, target_date: str):
    """解析腾讯行情单条响应；校验日期与目标交易日匹配。

    字段约定（qt.gtimg.cn）：
    f[1]=名称, f[2]=代码, f[3]=最新价, f[30]=行情时间(YYYYMMDDHHMMSS),
    f[32]=涨跌幅, f[37]=成交额(万元), f[44]=流通市值(亿), f[45]=总市值(亿)

    返回 (amount_yi: float|None, quote_date: str|None, reason: str)
    """
    prefix = f'v_{_tencent_code(code)}="'
    for line in body.split(";"):
        line = line.strip()
        if not line.startswith(prefix):
            continue
        tail = line[len(prefix):].rstrip('"')
        f = tail.split("~")
        if len(f) < 46:
            return None, None, f"字段不足({len(f)}<46)"
        ts = f[30].strip()
        if not ts or len(ts) < 8:
            return None, None, "无行情时间戳"
        quote_date = ts[:8]
        if quote_date != target_date:
            return None, quote_date, f"行情日期不匹配: 期望 {target_date}, 实际 {quote_date}"
        raw = f[37].strip()
        if not raw or raw in ("-", "0", "0.00"):
            return None, quote_date, "成交额为空或零"
        try:
            amount_yi = round(float(raw) / 1e4, 2)  # 万元 -> 亿元
        except ValueError:
            return None, quote_date, f"成交额非数字: {raw}"
        if amount_yi <= 0 or amount_yi > 5e5:  # 上证单日不可能 > 50 万亿
            return None, quote_date, f"成交额异常: {amount_yi} 亿"
        return amount_yi, quote_date, ""
    return None, None, "未找到对应代码行情"


def _tencent_index_amount(code: str, date: str):
    """腾讯备用通道：仅对已验证代码启用，严格校验日期。"""
    if code not in _TENCENT_ENABLED:
        return None
    url = f"https://qt.gtimg.cn/q={_tencent_code(code)}"
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        r.encoding = "gbk"
        amount, quote_date, reason = _parse_tencent_quote(r.text, code, date)
        if amount is None:
            log(f"腾讯指数 {code} {date} 不可用：{reason}")
            return None
        log(f"腾讯指数 {code} {date} 成交额 {amount} 亿")
        return amount
    except Exception as e:  # noqa: BLE001
        log(f"腾讯指数 {code} {date} 请求失败：{e}")
        return None


# ------------------------------------------------------------------
# 独立备用源（东财在 CI 被封时的通道）：中证指数官网 / baostock
# ------------------------------------------------------------------
# baostock 支持「指数日成交额」的代码子集（amount 字段，单位：元）
_BS_CODE_MAP = {
    "sh000001": "sh.000001", "sz399001": "sz.399001", "sz399006": "sz.399006",
    "sh000688": "sh.000688", "sh000016": "sh.000016", "sh000300": "sh.000300",
    "sz399673": "sz.399673", "sh000905": "sh.000905", "sh000906": "sh.000906",
    "sh000852": "sh.000852", "hstech_513180": "sh.513180",
}
# 中证指数公司官网：tradingValue 即成交额（亿元），权威源，
# 覆盖东财/腾讯/baostock 都取不全的中证系（含 932000 中证2000、000688 科创50）
_CSINDEX_CODE_MAP = {
    "sh000016": "000016", "sh000300": "000300", "sh000688": "000688",
    "sh000905": "000905", "sh000906": "000906", "sh000852": "000852",
    "sh932000": "932000", "sh000985": "000985",
}
_CSINDEX_URL = "https://www.csindex.com.cn/csindex-home/perf/index-perf"
_CSINDEX_HEADERS = {"User-Agent": "Mozilla/5.0",
                    "Referer": "https://www.csindex.com.cn/"}


# 中证官网偶发 SSL 中断（UNEXPECTED_EOF），用带退避重试的 Session 提升 CI 稳定性
_CSINDEX_SESSION = requests.Session()
_CSINDEX_SESSION.headers.update(_CSINDEX_HEADERS)
_CSINDEX_SESSION.mount(
    "https://",
    requests.adapters.HTTPAdapter(
        max_retries=requests.packages.urllib3.util.retry.Retry(
            total=5, backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"]))))


def _get_csindex_history(code: str, start: str, end: str) -> dict:
    """中证指数官网区间成交额 {date: 亿元}；不适用或失败返回 {}。"""
    cs = _CSINDEX_CODE_MAP.get(code)
    if not cs:
        return {}
    last_err = None
    for attempt in range(6):
        try:
            r = _CSINDEX_SESSION.get(_CSINDEX_URL,
                                     params={"indexCode": cs,
                                             "startDate": _bs_date(start),
                                             "endDate": _bs_date(end)},
                                     timeout=12)
            out = {}
            for row in (r.json().get("data") or []):
                d = str(row.get("tradeDate") or "")
                v = row.get("tradingValue")
                if len(d) == 8 and v is not None and float(v) > 0:
                    out[d] = round(float(v), 2)
            if out:
                return out
            last_err = "返回空 data"
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(0.6 * (attempt + 1))
    log(f"中证官网 {code} 区间获取失败（已重试 6 次）：{last_err}")
    return {}


def _get_csindex_amount(code: str, date: str):
    """中证指数官网单日成交额（亿元）；不适用或失败返回 None。"""
    return _get_csindex_history(code, date, date).get(date)


def _get_bs_history(code: str, start: str, end: str) -> dict:
    """baostock 区间成交额 {date: 亿元}；不适用或失败返回 {}。"""
    bsc = _BS_CODE_MAP.get(code)
    if not bsc:
        return {}
    try:
        import baostock as bs
        _bs_login()
        rs = bs.query_history_k_data_plus(bsc, "date,amount",
                                          start_date=_bs_date(start),
                                          end_date=_bs_date(end),
                                          frequency="d", adjustflag="3")
        if rs is None or rs.error_code != "0":
            log(f"baostock {code} 区间失败：{getattr(rs, 'error_msg', '无返回')}")
            return {}
        out = {}
        while rs.next():
            row = rs.get_row_data()
            try:
                v = float(row[1])
            except (TypeError, ValueError):
                continue
            if v > 0:
                out[str(row[0]).replace("-", "")] = round(v / 1e8, 2)
        return out
    except Exception as e:  # noqa: BLE001
        log(f"baostock {code} 区间异常：{e}")
        return {}


def _get_bs_amount(code: str, date: str):
    """baostock 单日成交额（亿元）；不适用或失败返回 None。"""
    return _get_bs_history(code, date, date).get(date)


def get_index_amount_history(code: str, start: str, end: str) -> dict:
    """区间指数成交额 {date: 亿元}；多源回退：东财 → baostock → 中证官网。"""
    pure = code[2:]
    try:
        if code == "hstech_513180":
            df = retry(lambda: ak.fund_etf_hist_em(symbol="513180", period="daily",
                       start_date=start, end_date=end, adjust=""), what=f"ETF回补{code}")
            col = "成交额"
        else:
            df = retry(lambda: ak.index_zh_a_hist(symbol=pure, period="daily",
                       start_date=start, end_date=end), what=f"指数回补{code}")
            col = "成交额" if "成交额" in df.columns else "amount"
        vals = {str(r["日期"]).replace("-", ""): round(float(r[col]) / 1e8, 2)
                for _, r in df.iterrows()}
        if vals:
            return vals
    except Exception as e:  # noqa: BLE001
        log(f"指数回补东财 {code} 失败：{e}")
    # baostock 优先（快、覆盖广）；中证官网仅兜底（覆盖 932000/000688/000985）
    vals = _get_bs_history(code, start, end)
    if vals:
        return vals
    return _get_csindex_history(code, start, end)


def get_index_amount(code: str, date: str):
    """返回当日成交额（亿元）；全部数据源失败返回 None（绝不伪造）。

    策略（任一成功即返回）：
    1. 东财 AKShare 日线（本地/未封禁环境主源）
    2. 腾讯实时行情（CI 可用；仅当日，严格校验「行情日期 == 目标交易日」）
    3. baostock 日线（CI 安全历史源；快、覆盖 10/14 代码）
    4. 中证指数官网 tradingValue（CI 安全兜底；补 932000/000688/000985 缺口）
    5. 全部失败 → None，调用方保留旧数据
    """
    # 通道 1：东财
    try:
        if code == "hstech_513180":
            df = retry(lambda: ak.fund_etf_hist_em(symbol="513180", period="daily",
                       start_date=date, end_date=date, adjust=""), what=f"ETF{code}")
            amt_col = "成交额"
        else:
            pure = code[2:]  # 去掉 sh/sz/bj 前缀
            df = retry(lambda: ak.index_zh_a_hist(symbol=pure, period="daily",
                       start_date=date, end_date=date), what=f"指数{code}")
            amt_col = "成交额" if "成交额" in df.columns else "amount"
        if df is not None and len(df) > 0 and amt_col in df.columns:
            v = float(df.iloc[-1][amt_col])
            if v > 0:
                return round(v / 1e8, 2) if v > 1e6 else round(v, 2)  # 元→亿
    except Exception as e:  # noqa: BLE001
        log(f"指数 {code} {date} 东财获取失败：{e}")

    # 通道 2：腾讯实时（CI 可用；仅当日）
    amt = _tencent_index_amount(code, date)
    if amt is not None:
        return amt

    # 通道 3：baostock（CI 安全历史源；快、覆盖 10/14 代码）
    amt = _get_bs_amount(code, date)
    if amt is not None:
        return amt

    # 通道 4：中证指数官网（CI 安全历史源；兜底 932000/000688/000985）
    amt = _get_csindex_amount(code, date)
    if amt is not None:
        return amt

    log(f"指数 {code} {date} 全部数据源失败 → None（调用方保留旧数据）")
    return None


# ------------------------------------------------------------------
# baostock 指数收盘价（用于 YTD 等趋势观察，不新增数据源）
# ------------------------------------------------------------------
def _bs_code(code: str) -> str:
    if code == "hstech_513180":
        return "sh.513180"
    if code.startswith("sh"):
        return f"sh.{code[2:]}"
    if code.startswith("sz"):
        return f"sz.{code[2:]}"
    if code.startswith("bj"):
        return f"bj.{code[2:]}"
    return code


def _bs_date(d: str) -> str:
    """YYYYMMDD → YYYY-MM-DD（baostock 要求）"""
    return f"{d[:4]}-{d[4:6]}-{d[6:]}"


def _bs_login():
    global _BS_LOGGED
    if not _BS_LOGGED:
        import baostock as bs
        _BS_LOGGED = bool(bs.login())


def get_index_close(code: str, date: str):
    """使用 baostock 获取指数/ETF 指定交易日收盘价；失败返回 None"""
    _bs_login()
    import baostock as bs
    d = _bs_date(date)
    rs = bs.query_history_k_data_plus(
        _bs_code(code), "date,close", start_date=d, end_date=d,
        frequency="d", adjustflag="3")
    if rs is None or rs.error_code != "0":
        msg = getattr(rs, "error_msg", "返回 None") if rs else "返回 None"
        log(f"baostock 收盘价 {code} {date} 失败：{msg}")
        return None
    while rs.next():
        row = rs.get_row_data()
        try:
            return float(row[1])
        except (TypeError, ValueError):
            return None
    return None


def get_index_ytd_pct(code: str, date: str):
    """计算指数/ETF 年初至今涨跌幅（%）；失败返回 None"""
    year_start = _bs_date(f"{date[:4]}0101")
    _bs_login()
    import baostock as bs
    rs = bs.query_history_k_data_plus(
        _bs_code(code), "date,close", start_date=year_start, end_date=_bs_date(date),
        frequency="d", adjustflag="3")
    if rs is None or rs.error_code != "0":
        msg = getattr(rs, "error_msg", "返回 None") if rs else "返回 None"
        log(f"baostock YTD {code} {date} 失败：{msg}")
        return None
    rows = []
    while rs.next():
        rows.append(rs.get_row_data())
    if len(rows) < 2:
        return None
    first_close = float(rows[0][1])
    last_close = float(rows[-1][1])
    if first_close <= 0:
        return None
    return round((last_close / first_close - 1) * 100, 2)
