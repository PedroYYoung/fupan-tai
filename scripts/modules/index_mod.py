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
    "sh932000": "中证2000", "sh000985": "中证全指(沪深合计代理)", "hstech_513180": "恒生科技(513180近似)",
}

# 已验证可用腾讯行情的代码（verify_data_sources.py 实测）
# 注：腾讯实时行情实测覆盖 13/14 代码（含 bj899050 北证50、sh000688 科创50）。
# sh932000(中证2000) 在腾讯无对应符号（实测返回空壳，仅 1 个字段），故不在白名单内；
# 该代码改由「同标的 ETF 代理」通道兜底（见 _ETF_PROXY_BS）。
_TENCENT_ENABLED = {
    "sh000001", "sz399001", "sz399006", "sh000688", "bj899050",
    "sh000016", "sh000300", "sz399673", "sh000905", "sh000906",
    "sh000852", "sh000985", "hstech_513180",
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

# ------------------------------------------------------------------
# 最后兜底：同标的 ETF 代理
# ------------------------------------------------------------------
# 中证2000(932000) 在四个常规通道均无可用数据：
#   东财 —— CI 环境 push2 被封；腾讯 —— 无该符号；baostock —— 无该指数代码；
#   中证官网 —— index-perf 接口当前对所有指数返回空 data（通道已失效）。
# 故用同标的中规模最大、成交最活跃的 ETF 成交额顶上。
# 注意：ETF 成交额与指数成交额量级不可比（约 5 亿 vs 约 1500 亿），
# 仅作方向参考，调用方必须标注 approx 且不做历史排名/百分位。
_ETF_PROXY_BS = {
    "sh932000": "sh.563300",   # 华泰柏瑞中证2000ETF
}
# 中证指数公司官网：tradingValue 即成交额（亿元），权威源，
# 覆盖东财/腾讯/baostock 都取不全的中证系（含 932000 中证2000、000688 科创50）
# 注：2026-10 实测该接口对所有指数均返回空 data，通道目前实际不可用，仅保留待其恢复。
# 东财熔断：本机/CI 对 push2 系列接口存在反爬，失败会以 SSL 中断形式重试很久。
# 连续失败 3 次后本次进程内不再尝试东财，直接走 baostock / 中证官网，
# 避免「15 个指数 × 2 次重试 × 35 秒」把一次增量拖成半小时（不对坏源无限重试）。
_EM_FAILS = {"n": 0}
_EM_DISABLE_AFTER = 3


def _em_available() -> bool:
    return _EM_FAILS["n"] < _EM_DISABLE_AFTER


def _em_failed():
    _EM_FAILS["n"] += 1
    if _EM_FAILS["n"] == _EM_DISABLE_AFTER:
        log(f"东财通道连续失败 {_EM_DISABLE_AFTER} 次，本次运行剩余时间不再尝试")


def _em_ok():
    """一次成功即清零，保证熔断语义是「连续失败」而不是「累计失败」。"""
    _EM_FAILS["n"] = 0


# 「最近交易日降级」的最大可接受滞后（自然日）。超过此值说明该指数在目标日附近
# 长期没有真实数据（源端空档 / 赛季缺口），复用旧值只会把陈旧数据伪装成当日值。
MAX_STALE_DAYS = 10


def _days_between(d1: str, d2: str):
    """两个 YYYYMMDD 之间的自然日差；格式非法返回 None（宁可不复用，也不误用）。"""
    import datetime as _dt
    try:
        a = _dt.datetime.strptime(str(d1), "%Y%m%d").date()
        b = _dt.datetime.strptime(str(d2), "%Y%m%d").date()
        return (b - a).days
    except (TypeError, ValueError):
        return None


_CSINDEX_CODE_MAP = {
    "sh000016": "000016", "sh000300": "000300", "sh000688": "000688",
    "sh000905": "000905", "sh000906": "000906", "sh000852": "000852",
    "sh932000": "932000", "sh000985": "000985",
}
_CSINDEX_URL = "https://www.csindex.com.cn/csindex-home/perf/index-perf"
_CSINDEX_HEADERS = {"User-Agent": "Mozilla/5.0",
                    "Referer": "https://www.csindex.com.cn/"}

# 中证官网在部分网络下整段不可达（SSL UNEXPECTED_EOF，单指数重试可达 4 分钟）。
# 与东财一样加进程级熔断：连续失败 3 次后本次运行直接跳过，避免把增量拖成小时级。
_CS_FAILS = {"n": 0}
_CS_DISABLE_AFTER = 3


def _cs_available() -> bool:
    return _CS_FAILS["n"] < _CS_DISABLE_AFTER


def _cs_failed():
    _CS_FAILS["n"] += 1
    if _CS_FAILS["n"] == _CS_DISABLE_AFTER:
        log(f"中证官网连续失败 {_CS_DISABLE_AFTER} 次，本次运行剩余时间不再尝试")


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
    if not _cs_available():
        return {}
    last_err = None
    for attempt in range(3):
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
                _CS_FAILS["n"] = 0
                return out
            last_err = "返回空 data"
        except Exception as e:  # noqa: BLE001
            last_err = e
            time.sleep(0.6 * (attempt + 1))
    _cs_failed()
    log(f"中证官网 {code} 区间获取失败：{last_err}")
    return {}


def _get_csindex_amount(code: str, date: str):
    """中证指数官网单日成交额（亿元）；不适用或失败返回 None。"""
    return _get_csindex_history(code, date, date).get(date)


def _bs_relogin():
    """baostock 连接被服务端断开（WinError 10054 / 网络接收错误）后重连。"""
    global _BS_LOGGED
    try:
        import baostock as bs
        try:
            bs.logout()
        except Exception:  # noqa: BLE001
            pass
        _BS_LOGGED = False
        _bs_login()
    except Exception as e:  # noqa: BLE001
        log(f"baostock 重连失败：{e}")


def _bs_query_amount(bsc: str, start: str, end: str) -> dict:
    """单次 baostock 成交额查询；网络类错误抛出，交由调用方重连后重试。"""
    import baostock as bs
    _bs_login()
    rs = bs.query_history_k_data_plus(bsc, "date,amount",
                                      start_date=_bs_date(start),
                                      end_date=_bs_date(end),
                                      frequency="d", adjustflag="3")
    if rs is None or rs.error_code != "0":
        raise RuntimeError(getattr(rs, "error_msg", "无返回"))
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


def _get_bs_history(code: str, start: str, end: str) -> dict:
    """baostock 区间成交额 {date: 亿元}；不适用或失败返回 {}。

    baostock 的 socket 会在连续查询若干次后被服务端断开（WinError 10054
    「网络接收错误」），因此失败时 logout + 重新 login 再试一次，
    而不是把当天数据直接判死（实测重连后同一查询立即成功）。
    """
    bsc = _BS_CODE_MAP.get(code)
    if not bsc:
        return {}
    for attempt in range(2):
        try:
            return _bs_query_amount(bsc, start, end)
        except Exception as e:  # noqa: BLE001
            if attempt == 0:
                _bs_relogin()
                continue
            log(f"baostock {code} 区间异常：{e}")
    return {}


def _get_bs_amount(code: str, date: str):
    """baostock 单日成交额（亿元）；不适用或失败返回 None。"""
    return _get_bs_history(code, date, date).get(date)


def get_index_amount_history(code: str, start: str, end: str) -> dict:
    """区间指数成交额 {date: 亿元}；多源回退：东财 → baostock → 中证官网。"""
    pure = code[2:]
    if _em_available():
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
            _em_ok()
            return vals
      except Exception as e:  # noqa: BLE001
        _em_failed()
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
    # 通道 1：东财（连续失败则熔断，本次运行不再尝试）
    if _em_available():
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
                _em_ok()
                return round(v / 1e8, 2) if v > 1e6 else round(v, 2)  # 元→亿
      except Exception as e:  # noqa: BLE001
        _em_failed()
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


def get_etf_proxy_amount(code: str, date: str):
    """最后兜底：同标的 ETF 当日成交额（亿元）。

    仅在 _ETF_PROXY_BS 中配置过的代码才启用（当前只有 sh932000）。
    ETF 成交额与指数成交额量级不可比，调用方须标注 approx 且不参与历史排名。
    不适用或失败返回 None（绝不伪造）。
    """
    bsc = _ETF_PROXY_BS.get(code)
    if not bsc:
        return None
    try:
        import baostock as bs
        _bs_login()
        rs = bs.query_history_k_data_plus(
            bsc, "date,amount", start_date=_bs_date(date), end_date=_bs_date(date),
            frequency="d", adjustflag="3")
        if rs is None or rs.error_code != "0":
            log(f"ETF代理 {code}<-{bsc} {date} 失败：{getattr(rs, 'error_msg', '无返回')}")
            return None
        while rs.next():
            row = rs.get_row_data()
            try:
                v = float(row[1])
            except (TypeError, ValueError):
                return None
            if v > 0:
                amt = round(v / 1e8, 2)
                log(f"ETF代理 {code}<-{bsc} {date} 成交额 {amt} 亿（量级不可比，仅方向参考）")
                return amt
    except Exception as e:  # noqa: BLE001
        log(f"ETF代理 {code} {date} 异常：{e}")
    return None


def get_index_amount_resilient(code: str, date: str, last_known=None):
    """带降级的当日成交额：当日取不到时用最近交易日数据顶上，避免矩阵整格空白。

    返回 (amount, amount_date, note)：
      note=""                 当日真实抓取成功
      note="last_trading_day" 当日失败，复用序列中最近一个早于当日的真实值
      note="etf_proxy"        当日与最近交易日均无真实值，用同标的 ETF 代理（量级不可比）

    last_known: 由调用方从已落盘序列读取的 (value, date)，避免为此多打一次网络请求。
    全部分支失败返回 (None, None, "")。
    """
    amt = get_index_amount(code, date)
    if amt is not None:
        return amt, date, ""
    # 降级 1：最近一个已落盘的真实交易日数据（复用自身历史，非伪造）
    # 但「最近」必须真的最近：sh932000 的序列止于 20251231（2026 年段是已删除的合成数据），
    # 若不加闸门，20261020 会拿到 9 个月前的值并显示成当日成交额 —— 那不叫降级，叫陈旧冒充。
    if last_known:
        v, vd = last_known
        if v is not None and vd and str(vd) <= date:
            gap = _days_between(str(vd), date)
            if gap is not None and gap <= MAX_STALE_DAYS:
                log(f"指数 {code} {date} 当日无数据 → 降级复用最近交易日 {vd} 的 {v} 亿（滞后 {gap} 天）")
                return v, str(vd), "last_trading_day"
            if gap is not None:
                log(f"指数 {code} {date} 最近值 {vd} 已滞后 {gap} 天（> {MAX_STALE_DAYS}），"
                    f"不再当作当日值复用")
    # 降级 2：同标的 ETF 代理（仅方向参考）
    v = get_etf_proxy_amount(code, date)
    if v is not None:
        return v, date, "etf_proxy"
    log(f"指数 {code} {date} 当日/最近交易日/ETF代理 全部失败 → 置空")
    return None, None, ""


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


BS_SOCKET_TIMEOUT = 25.0


def _bs_login():
    """baostock 登录（幂等）。

    baostock 内部 socket 未设置超时，网络抖动时会永久挂起（实测 query_all_stock 可达 75s 以上）。
    这里给全局 socket 一个上限：requests 调用均已显式传 timeout，不受影响；
    baostock 的 login/query 则会按时抛错，交由上层回退到腾讯/东财通道。
    """
    global _BS_LOGGED
    if not _BS_LOGGED:
        import socket

        import baostock as bs

        socket.setdefaulttimeout(BS_SOCKET_TIMEOUT)
        _BS_LOGGED = bool(bs.login())


def _tencent_change_pct(code: str, date: str):
    """腾讯行情当日涨跌幅（f[32]），严格校验行情日期；失败返回 None"""
    if code not in _TENCENT_ENABLED:
        return None
    try:
        r = requests.get(f"https://qt.gtimg.cn/q={_tencent_code(code)}",
                         headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        r.encoding = "gbk"
        prefix = f'v_{_tencent_code(code)}="'
        for line in r.text.split(";"):
            line = line.strip()
            if not line.startswith(prefix):
                continue
            f = line[len(prefix):].rstrip('"').split("~")
            if len(f) < 33:
                return None
            ts = f[30].strip()
            if not ts or ts[:8] != date:
                return None
            raw = f[32].strip()
            if not raw or raw == "-":
                return None
            try:
                return round(float(raw), 2)
            except ValueError:
                return None
    except Exception as e:  # noqa: BLE001
        log(f"腾讯涨跌幅 {code} {date} 失败：{e}")
    return None


def get_index_change_pct(code: str, date: str):
    """当日涨跌幅（%）；失败返回 None。

    baostock pctChg 为主（CI 可用、可查任意历史日期）；腾讯 f[32] 为备（仅当日）。
    """
    try:
        import baostock as bs
        _bs_login()
        rs = bs.query_history_k_data_plus(
            _bs_code(code), "date,pctChg", start_date=_bs_date(date), end_date=_bs_date(date),
            frequency="d", adjustflag="3")
        if rs is not None and rs.error_code == "0":
            while rs.next():
                row = rs.get_row_data()
                try:
                    return round(float(row[1]), 2)
                except (TypeError, ValueError):
                    return None
    except Exception as e:  # noqa: BLE001
        log(f"指数涨跌幅 {code} {date} baostock 失败：{e}")
    return _tencent_change_pct(code, date)


# ------------------------------------------------------------------
# 新浪指数日线（baostock 不覆盖科创50/北证50/中证全指等时的历史收盘兜底）
# ------------------------------------------------------------------
_SINA_CACHE = {}


def _sina_daily(code: str) -> dict:
    """新浪指数日线 {YYYYMMDD: close}；失败返回 {}（进程内缓存）。"""
    if code in _SINA_CACHE:
        return _SINA_CACHE[code]
    out = {}
    try:
        import akshare as ak
        df = ak.stock_zh_index_daily(symbol=code)
        for _, r in df.iterrows():
            d = str(r.get("date")).replace("-", "").strip()
            try:
                out[d] = float(r["close"])
            except (TypeError, ValueError):
                continue
    except Exception as e:  # noqa: BLE001
        log(f"新浪指数日线 {code} 失败：{e}")
    _SINA_CACHE[code] = out
    return out


def _sina_close(code: str, date: str) -> float | None:
    return _sina_daily(code).get(date)


def get_index_close(code: str, date: str):
    """获取指数/ETF 指定交易日收盘价；baostock → 新浪，均失败返回 None。

    baostock 不覆盖科创50(sh000688)/北证50(bj899050)/中证全指(sh000985)等，
    这些代码由新浪通道兜底。
    """
    _bs_login()
    import baostock as bs
    d = _bs_date(date)
    rs = bs.query_history_k_data_plus(
        _bs_code(code), "date,close", start_date=d, end_date=d,
        frequency="d", adjustflag="3")
    if rs is not None and rs.error_code == "0":
        while rs.next():
            row = rs.get_row_data()
            try:
                return float(row[1])
            except (TypeError, ValueError):
                return None
    # 新浪兜底
    v = _sina_close(code, date)
    if v is not None:
        return v
    log(f"收盘价 {code} {date} baostock/新浪均无数据")
    return None


def get_index_ytd_pct(code: str, date: str, dates=None):
    """年初至今涨跌幅（%）：YTD = (当日收盘 / 上一年度最后交易日收盘 - 1) * 100。

    基准日为「上一年度最后一个交易日」；有交易日历时用交易日历精确取，
    否则退化为查询上一年 12 月 1 日~当年 1 月 1 日之间最后一个收盘。
    失败返回 None（绝不硬编码）。
    """
    year = int(date[:4])
    if dates:
        prev_days = [d for d in dates if d < f"{year}0101"]
        base_date = prev_days[-1] if prev_days else None
    else:
        base_date = None

    if base_date is None:
        # 无交易日历：从上一年 12 月开始找最后一个交易日收盘（用 baostock 区间查询）
        base_date = _prev_year_last_trade_day(code, year)

    if base_date is None:
        log(f"YTD {code} {date}：无法确定上一年度最后交易日基准")
        return None

    base_close = get_index_close(code, base_date)
    cur_close = get_index_close(code, date)
    if base_close is None or cur_close is None or base_close <= 0:
        log(f"YTD {code} {date}：基准 {base_date} 收盘={base_close}，当日收盘={cur_close}，无法计算")
        return None
    return round((cur_close / base_close - 1) * 100, 2)


def _prev_year_last_trade_day(code: str, year: int):
    """无交易日历时的兜底：用 baostock 区间查询找上一年最后一个交易日。"""
    import baostock as bs
    _bs_login()
    start = _bs_date(f"{year - 1}1201")
    end = _bs_date(f"{year}0101")
    rs = bs.query_history_k_data_plus(
        _bs_code(code), "date", start_date=start, end_date=end,
        frequency="d", adjustflag="3")
    if rs is None or rs.error_code != "0":
        return None
    last = None
    while rs.next():
        d = str(rs.get_row_data()[0]).replace("-", "")
        if d < f"{year}0101":
            last = d
    return last
