# -*- coding: utf-8 -*-
"""交易所及证监会监管信息采集适配器。

来源：
- 上交所监管措施 https://www.sse.com.cn/regulation/supervision/measures/
- 深交所监管信息公开 https://www.szse.cn/disclosure/supervision/
- 证监会行政处罚 http://www.csrc.gov.cn/

合规：只读取公开信息；不绕过登录、验证码或访问限制。若接口因参数/反爬
无法稳定取得，如实返回 unavailable 并记录实测证据，绝不伪造事件。
"""
import urllib.parse
import urllib.request

_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "Chrome/120.0 Safari/537.36",
}


def _get(url, referer):
    req = urllib.request.Request(url, headers={**_UA, "Referer": referer})
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read().decode("utf-8", "replace")


def collect_sse(trade_date):
    """上交所监管措施。公开 SOA 查询接口，需精确 sqlId。"""
    try:
        url = ("https://query.sse.com.cn/commonSoaQuery.do?"
               "sqlId=COMMON_SSE_CPGP_GPJYPL_GPJYPL_MESSAGE_L&isPagination=true"
               "&pageHelp.pageSize=20&pageHelp.pageNo=1&type=inParams"
               f"&SEARCH_DATE={trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}")
        body = _get(url, "https://www.sse.com.cn/")
        # 实测：该 sqlId 返回 {"success":"false","errorMsg":"SOA service is null"}
        # 接口参数需进一步核实，本轮不伪造，标记 unavailable。
        return [], "unavailable", {"detail": "上交所监管措施接口参数未通过验证（SOA service is null）",
                                    "snippet": body[:120]}
    except Exception as exc:  # noqa: BLE001
        return [], "unavailable", {"detail": str(exc)}


def collect_szse(trade_date):
    """深交所监管信息公开。ShowReport 接口需精确 CATALOGID 且存在反爬。"""
    try:
        url = ("https://www.szse.cn/api/report/ShowReport/data?SHOWTYPE=JSON"
               "&CATALOGID=main_jgxx&TABKEY=tab1&PAGENO=1")
        body = _get(url, "https://www.szse.cn/")
        # 实测：返回 recordcount=0 + "显示报表数据失败"，需 cookie/精确 CATALOGID。
        return [], "unavailable", {"detail": "深交所监管接口需精确 CATALOGID/会话，当前未通过验证",
                                    "snippet": body[:120]}
    except Exception as exc:  # noqa: BLE001
        return [], "unavailable", {"detail": str(exc)}


def collect_csrc(trade_date):
    """证监会行政处罚/监管执法。站内搜索接口需精确参数。"""
    try:
        url = ("http://www.csrc.gov.cn/searchList/a15dc9809d884f148ed7eb50114fb78c"
               "?_isAgg=true&_isJson=true&_pageSize=20&_template=index&page=1")
        body = _get(url, "http://www.csrc.gov.cn/")
        # 实测：返回 total=0，搜索参数需进一步核实。
        return [], "unavailable", {"detail": "证监会搜索接口参数未通过验证（total=0）",
                                    "snippet": body[:120]}
    except Exception as exc:  # noqa: BLE001
        return [], "unavailable", {"detail": str(exc)}


# 各来源适配器注册表（build_observation 逐个调用，独立容错）
SOURCES = [
    {"key": "sse", "name": "上交所监管措施", "url": "https://www.sse.com.cn/regulation/supervision/measures/",
     "fn": collect_sse},
    {"key": "szse", "name": "深交所监管信息公开", "url": "https://www.szse.cn/disclosure/supervision/",
     "fn": collect_szse},
    {"key": "csrc", "name": "证监会行政处罚", "url": "http://www.csrc.gov.cn/",
     "fn": collect_csrc},
]
