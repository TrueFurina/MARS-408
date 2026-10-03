#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""品牌图标 / PWA / 分享卡资产生成器（零裁切，可复现）。

从一张**正方形**主视觉原图生成完整的外层品牌资产：

    public/brand/mangxiaocheng-64.png            64x64     favicon（PNG）
    public/brand/mangxiaocheng-180.png          180x180    Apple touch icon
    public/brand/mangxiaocheng-192.png          192x192    PWA manifest (any)
    public/brand/mangxiaocheng.png              256x256    应用内 logo / 高分辨率 favicon
    public/brand/mangxiaocheng-512.png          512x512    PWA manifest (any)
    public/brand/mangxiaocheng-512-maskable.png 512x512    PWA manifest (maskable, 80% 安全区)
    public/brand/mangxiaocheng.ico              16/32/48/64 多尺寸 ICO
    public/brand/share-og.png                   1200x630   OG / Twitter 分享卡

设计约束（与 design-system v11 一致）：
  * **零裁切**：源为正方形，方形图标 = 整图等比缩放，逐像素等于 "整图 resize"。
  * 分享卡为 1200x630 画布：整幅作品 contain 到左侧（高度 540），右侧品牌字；
    底色 / 辉光取自品牌 token（#0E1217 画布 + #7c6af2 紫）。

用法：
    python scripts/gen_brand_assets.py                     # 用默认源图
    python scripts/gen_brand_assets.py --src "D:\\art.jpg"  # 指定源图
    python scripts/gen_brand_assets.py --out public/brand  # 指定输出目录

依赖：Pillow。CJK 字体取 Windows 自带 msyh/msyhbd（缺失时回退 simhei）。
"""
from __future__ import annotations

import argparse
import os
import sys

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
except ImportError:  # pragma: no cover
    sys.exit("需要 Pillow：pip install Pillow")

# ── 默认值 ────────────────────────────────────────────────────────────────
DEFAULT_SRC = r"E:\3chuang\豆豆AI图片\成长治愈篇 (4).jpg"
DEFAULT_OUT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "public", "brand"
)

CANVAS_DARK = (14, 18, 23)      # #0E1217 深色画布（同 --color-canvas）
CANVAS_DARK2 = (21, 26, 32)     # #151A20 渐变末端（同 --color-surface）
ACCENT = (124, 106, 242)        # #7c6af2 紫罗兰（同 --color-accent）
ACCENT_TEXT = (169, 159, 247)   # #a99ff7 深底强调文字（同 --color-accent-text）
WHITE = (255, 255, 255)

FONT_BOLD_CANDS = [r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\simhei.ttf"]
FONT_REG_CANDS = [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"]

BRAND_TITLE = "芒得很职"
BRAND_SUB = ["多智能体赋能", "职业素养对抗实训平台"]


def _font(cands, size):
    for p in cands:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def contain_square(src: Image.Image, size: int) -> Image.Image:
    """整幅等比缩放到 size×size（平方源 → 零裁切）。"""
    return src.resize((size, size), Image.LANCZOS)


def radial_glow(base: Image.Image, center, radius: int, color, alpha: int) -> Image.Image:
    """在 base(RGB) 上叠加一团柔和径向辉光，返回新图。"""
    w, h = base.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = center
    d.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
              fill=(color[0], color[1], color[2], alpha))
    layer = layer.filter(ImageFilter.GaussianBlur(radius * 0.55))
    return Image.alpha_composite(base.convert("RGBA"), layer).convert("RGB")


def generate(src_path: str, out_dir: str) -> list[str]:
    os.makedirs(out_dir, exist_ok=True)
    src = Image.open(src_path).convert("RGB")
    if src.size[0] != src.size[1]:
        sys.exit(f"源图必须是正方形（当前 {src.size}）；否则方形图标会变形/裁切。")
    written: list[str] = []

    def save(img: Image.Image, name: str, **kw) -> None:
        p = os.path.join(out_dir, name)
        img.save(p, **kw)
        written.append(name)
        print(f"  {name:34s} {img.size}")

    # 1. 方形 PNG（整幅 contain）
    for name, size in [
        ("mangxiaocheng-64.png", 64),
        ("mangxiaocheng-180.png", 180),
        ("mangxiaocheng-192.png", 192),
        ("mangxiaocheng.png", 256),
        ("mangxiaocheng-512.png", 512),
    ]:
        save(contain_square(src, size), name, format="PNG", optimize=True)

    # 2. maskable：整幅缩至 80% 居中，四周补画布底色（安全区）
    M, ratio = 512, 0.80
    mask_canvas = Image.new("RGB", (M, M), CANVAS_DARK)
    inner = int(M * ratio)
    mask_canvas.paste(contain_square(src, inner), ((M - inner) // 2,) * 2)
    save(mask_canvas, "mangxiaocheng-512-maskable.png", format="PNG", optimize=True)

    # 3. 多尺寸 ICO
    ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64)]
    ico = contain_square(src, 256)
    save(ico, "mangxiaocheng.ico", format="ICO", sizes=ico_sizes)

    # 4. OG 分享卡 1200x630
    W, H = 1200, 630
    base = Image.new("RGB", (W, H))
    px = base.load()
    for y in range(H):
        t = y / (H - 1)
        row = tuple(int(CANVAS_DARK[i] + (CANVAS_DARK2[i] - CANVAS_DARK[i]) * t) for i in range(3))
        for x in range(W):
            px[x, y] = row
    card = radial_glow(base, (150, 60), 420, ACCENT, 46)
    card = radial_glow(card, (1080, 600), 380, ACCENT, 34)

    art_h = 540
    art = src.resize((art_h, art_h), Image.LANCZOS)
    card.paste(art, (56, (H - art_h) // 2))

    d = ImageDraw.Draw(card)
    f_title = _font(FONT_BOLD_CANDS, 78)
    f_sub = _font(FONT_REG_CANDS, 33)
    tx = 56 + art_h + 52
    d.text((tx, 226), BRAND_TITLE, font=f_title, fill=WHITE)
    d.rounded_rectangle([tx, 336, tx + 68, 342], radius=3, fill=ACCENT)
    for i, line in enumerate(BRAND_SUB):
        d.text((tx, 372 + i * 44), line, font=f_sub, fill=ACCENT_TEXT)
    save(card, "share-og.png", format="PNG", optimize=True)

    return written


def main() -> None:
    ap = argparse.ArgumentParser(description="生成品牌图标 / PWA / OG 分享卡资产")
    ap.add_argument("--src", default=DEFAULT_SRC, help="正方形主视觉原图路径")
    ap.add_argument("--out", default=DEFAULT_OUT, help="输出目录（默认 public/brand）")
    a = ap.parse_args()
    print(f"src : {a.src}")
    print(f"out : {a.out}")
    names = generate(a.src, a.out)
    print(f"\nDONE — {len(names)} files")


if __name__ == "__main__":
    main()
