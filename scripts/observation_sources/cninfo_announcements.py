# -*- coding: utf-8 -*-
"""巨潮资讯网（cninfo.com.cn）上市公司公告采集适配器。

官方公开查询接口：http://www.cninfo.com.cn/new/hisAnnouncement/query（POST）
- 支持按公告披露日期区间（seDate）回溯历史公告。
- 返回字段含证券代码、公司名称、公告标题、发布时间、PDF 原文入口。
- 只读取公开数据，不绕过任何登录/验证码/访问限制。

数据授权与合规：仅用于本地个人复盘，不将抓取到的原文内容上传公开仓库。
"""
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

from . import events

CNINFO_QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
PDF_BASE = "https://static.cninfo.com.cn/"
CNINFO_HOME = "https://www.cninfo.com.cn/"

_UA = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "Chrome/120.0 Safari/537.36",
    "Referer": "http://www.cninfo.com.cn/new/commonUrl/pageOfSearch?url=disclosure/list/search",
    "X-Requested-With": "XMLHttpRequest",
}

_CN_TZ = timezone(timedelta(hours=8))


def _ts_to_cn(ts_ms):
    """巨潮 announcementTime（毫秒时间戳）→ 北京时间 ISO 字符串。"""
    if not ts_ms:
        return None
    try:
        dt = datetime.fromtimestamp(ts_ms / 1000, tz=_CN_TZ)
        return dt.isoformat(timespec="seconds")
    except (ValueError, OSError, OverflowError):
        return None


def _query_page(se_date, page_num, page_size=30, retries=3):
    """查询单页公告，返回 (total, rows)。带重试（巨潮接口偶发 504）。"""
    data = urllib.parse.urlencode({
        "pageNum": page_num,
        "pageSize": page_size,
        "column": "sse",        # 上交所（fulltext 模式下实际返回全市场）
        "tabName": "fulltext",
        "plate": "",
        "stock": "",
        "searchkey": "",
        "secid": "",
        "category": "",
        "trade": "",
        "seDate": se_date,      # 形如 2026-11-06~2026-11-06
        "sortName": "",
        "sortType": "",
        "isHLtitle": "true",
    }).encode("utf-8")

    import json
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(CNINFO_QUERY_URL, data=data, headers=_UA)
            with urllib.request.urlopen(req, timeout=25) as r:
                body = r.read().decode("utf-8", "replace")
            obj = json.loads(body)
            total = int(obj.get("totalAnnouncement") or 0)
            rows = obj.get("announcements") or []
            return total, rows
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(1.0 * (attempt + 1))
    raise last_err


def fetch_announcements(trade_date, max_pages=0, delay=0.3):
    """抓取指定交易日的全部公告，返回标准化事件列表。

    参数：
      trade_date  交易日 YYYYMMDD（公告披露日）
      max_pages   最多翻页数（0=不限制，抓全量）；用于限制请求量
      delay       每页请求间隔秒数（合理访问频率）
    """
    se_date = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}~" \
              f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"

    collected_at = datetime.now(_CN_TZ).isoformat(timespec="seconds")
    raw_events = []
    total, rows = _query_page(se_date, 1)
    page = 1
    while rows:
        for a in rows:
            sec_code = a.get("secCode") or ""
            sec_name = a.get("secName") or ""
            title = (a.get("announcementTitle") or a.get("shortTitle") or "").strip()
            if not title:
                continue
            ts = a.get("announcementTime")
            published_at = _ts_to_cn(ts)
            adj = a.get("adjunctUrl") or ""
            original_url = (PDF_BASE + adj) if adj else ""
            announce_id = a.get("announcementId") or ""

            category, group = events.classify_title(title)
            raw_events.append({
                "event_id": f"cninfo_{announce_id}",
                "event_date": trade_date,
                "published_at": published_at,
                "collected_at": collected_at,
                "company_name": sec_name,
                "stock_code": sec_code,
                "source_type": "announcement",
                "source_name": "巨潮资讯网",
                "event_category": category,
                "category_group": group,
                "title": title,
                "factual_summary": events.build_factual_summary(title, sec_name),
                "event_status": "已披露",
                "original_url": original_url,
                "related_primary_url": CNINFO_HOME,
                "verification_status": events.VERIFY_OFFICIAL,
                "duplicate_key": events.make_duplicate_key(sec_code, category, title),
                "is_routine": events.is_routine(title),
            })
        if not total or page >= (total // 30 + (1 if total % 30 else 0)):
            break
        if max_pages and page >= max_pages:
            break
        page += 1
        time.sleep(delay)
        total2, rows = _query_page(se_date, page)

    return raw_events, total


def collect(trade_date, max_pages=0):
    """适配器入口：抓取并筛选重点事件。

    返回 (events, status, meta)：
      events  非例行的重点事件列表（已去重）
      status  success_with_events / success_no_match / partial / unavailable
      meta    总公告数、重点事件数、采集时间等
    """
    try:
        raw, total = fetch_announcements(trade_date, max_pages=max_pages)
    except Exception as exc:  # noqa: BLE001
        return [], "unavailable", {"error": str(exc)}

    deduped = events.deduplicate(raw)
    # 重点事件 = 非例行公告（保留原始标题与链接，不改写事实）
    important = [e for e in deduped if not e.get("is_routine")]

    status = "success_with_events" if important else "success_no_match"
    meta = {
        "total_announcements": total,
        "collected": len(raw),
        "important_events": len(important),
        "as_of": datetime.now(_CN_TZ).isoformat(timespec="seconds"),
    }
    return important, status, meta
