#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""复盘台 · 公共工具：限速重试 / 原子写入 / 错误日志"""
import json
import os
import time
import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 统一数据根：public/data（Vite 直接静态托管 /data/*，构建时随 dist 发布，
# 本地 dev / Vercel / CI 三端同构，不再维护第二份拷贝）
DATA_DIR = os.path.join(REPO_ROOT, "public", "data")

_req_count = 0


def log(msg: str):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def pace():
    """每 50 次请求 sleep 2s，防 IP 封禁"""
    global _req_count
    _req_count += 1
    if _req_count % 50 == 0:
        log(f"已发起 {_req_count} 次请求，休眠 2s …")
        time.sleep(2)


def retry(fn, times=2, delay=5, what=""):
    """单接口最多重试 2 次、间隔 5s"""
    last_exc = None
    for i in range(times + 1):
        try:
            pace()
            return fn()
        except Exception as e:  # noqa: BLE001
            last_exc = e
            if i < times:
                log(f"{what} 第{i+1}次失败：{e}，{delay}s 后重试")
                time.sleep(delay)
    raise last_exc


def atomic_write_json(path: str, obj) -> None:
    """全部写入 *.tmp，校验通过后原子替换；保证无半份 json"""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        f.flush()
        os.fsync(f.fileno())
    # 校验：能完整读回
    with open(tmp, "r", encoding="utf-8") as f:
        json.load(f)
    os.replace(tmp, path)
    log(f"写出 {os.path.relpath(path, REPO_ROOT)}")


def record_error(msg: str) -> None:
    """任一日失败 → 保留旧数据，追加 last_error.log（网站仍显示上一交易日数据）"""
    os.makedirs(os.path.join(DATA_DIR, "meta"), exist_ok=True)
    p = os.path.join(DATA_DIR, "meta", "last_error.log")
    with open(p, "a", encoding="utf-8") as f:
        f.write(f"{datetime.datetime.now().isoformat(timespec='seconds')} {msg}\n")


def now_iso() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")
