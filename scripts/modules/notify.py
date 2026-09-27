# -*- coding: utf-8 -*-
"""失败通知：PushPlus / Server酱（可选，token 为空则跳过）"""
import os
import requests
from .common import log


def notify_failure(title: str, content: str):
    pushplus = os.environ.get("PUSHPLUS_TOKEN", "").strip()
    sc = os.environ.get("SC_SENDKEY", "").strip()
    try:
        if pushplus:
            requests.post("https://www.pushplus.plus/send", json={
                "token": pushplus, "title": title, "content": content, "template": "txt"
            }, timeout=10)
            log("已通过 PushPlus 推送失败通知")
        if sc:
            requests.post(f"https://sctapi.ftqq.com/{sc}.send", data={
                "title": title, "desp": content
            }, timeout=10)
            log("已通过 Server酱 推送失败通知")
    except Exception as e:  # noqa: BLE001
        log(f"通知发送失败（不影响构建）：{e}")
