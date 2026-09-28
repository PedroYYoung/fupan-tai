#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 PWA 图标：192/512，#B7410E 纯色背景 + 白色「复盘台」三字（无图片素材依赖）"""
import os
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "public", "icons")
os.makedirs(OUT, exist_ok=True)

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",   # 微软雅黑 Bold
    r"C:\Windows\Fonts\msyh.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/System/Library/Fonts/PingFang.ttc",
]


def make(size: int):
    img = Image.new("RGB", (size, size), "#B7410E")
    draw = ImageDraw.Draw(img)
    font = None
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                font = ImageFont.truetype(p, int(size * 0.30))
                break
            except OSError:
                continue
    if font is None:
        font = ImageFont.load_default()
    text = "复盘台"
    bbox = draw.textbbox((0, 0), text, font=font)
    w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((size - w) / 2 - bbox[0], (size - h) / 2 - bbox[1]), text,
              fill="#FFFFFF", font=font)
    img.save(os.path.join(OUT, f"icon-{size}.png"), "PNG")
    print(f"icon-{size}.png 完成")


if __name__ == "__main__":
    make(192)
    make(512)
