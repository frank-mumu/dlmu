"""图文卡片渲染（Pillow 代码绘制，零 AI 出图成本）。输出 3:4 小红书卡片 PNG。

分页结构化：封面 + 若干内容页(每页 heading + points) + 尾页 CTA，
页码 i/N，前后页有逻辑，支撑 5-8 页翻页图。
"""
import os

from PIL import Image, ImageDraw, ImageFont

from ..config import settings

W, H = 1080, 1440
ACCENT = (24, 119, 242)
INK = (34, 34, 34)
MUTED = (120, 120, 120)
BG = (255, 255, 255)
FOOTER = "考研信息 · 干货分享"

_FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Supplemental/Songti.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/arphic/uming.ttc",
]


def _find_font():
    if settings.card_font and os.path.exists(settings.card_font):
        return settings.card_font
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return ""


def _font(size):
    path = _find_font()
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _wrap(draw, text, font, max_w):
    lines = []
    for para in str(text).split("\n"):
        if not para:
            lines.append("")
            continue
        cur = ""
        for ch in para:
            if draw.textlength(cur + ch, font=font) <= max_w:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
        lines.append(cur)
    return lines


def render_cover(path, title, subtitle="", footer=FOOTER, page=1, total=1):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 16], fill=ACCENT)
    f_title, f_sub, f_foot, f_pg = _font(76), _font(40), _font(36), _font(34)
    y = 190
    for ln in _wrap(d, title, f_title, W - 160)[:4]:
        d.text((80, y), ln, font=f_title, fill=INK)
        y += 102
    y += 30
    if subtitle:
        for ln in _wrap(d, subtitle, f_sub, W - 160)[:4]:
            d.text((80, y), ln, font=f_sub, fill=MUTED)
            y += 58
    d.rectangle([0, H - 96, W, H], fill=ACCENT)
    d.text((80, H - 72), footer, font=f_foot, fill=(255, 255, 255))
    d.text((W - 90, H - 72), f"{page}/{total}", font=f_pg, fill=(255, 255, 255))
    img.save(path, "PNG")


def render_content(path, heading, points, page=2, total=2, footer=FOOTER):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 16], fill=ACCENT)
    f_h, f_b, f_pg, f_foot = _font(56), _font(40), _font(32), _font(30)
    y = 130
    for ln in _wrap(d, heading, f_h, W - 160)[:2]:
        d.text((80, y), ln, font=f_h, fill=INK)
        y += 72
    y += 24
    for p in points:
        for i, ln in enumerate(_wrap(d, "· " + str(p), f_b, W - 180)):
            d.text((80 if i == 0 else 110, y), ln, font=f_b, fill=INK)
            y += 58
        y += 16
    d.text((80, H - 70), footer, font=f_foot, fill=MUTED)
    d.text((W - 90, H - 70), f"{page}/{total}", font=f_pg, fill=MUTED)
    img.save(path, "PNG")


def render_closing(path, closing, footer=FOOTER, page=2, total=2):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 16], fill=ACCENT)
    f_c, f_foot, f_pg = _font(52), _font(36), _font(34)
    y = 460
    for ln in _wrap(d, closing, f_c, W - 200)[:6]:
        d.text((100, y), ln, font=f_c, fill=INK)
        y += 80
    d.rectangle([0, H - 96, W, H], fill=ACCENT)
    d.text((80, H - 72), footer, font=f_foot, fill=(255, 255, 255))
    d.text((W - 90, H - 72), f"{page}/{total}", font=f_pg, fill=(255, 255, 255))
    img.save(path, "PNG")


def render_draft(out_dir, title, subtitle, pages, closing="", footer=FOOTER):
    """渲染一套分页卡片：封面 + 每页内容 + 尾页 CTA。

    pages: [{"heading": str, "points": [str, ...]}, ...]
    返回图片路径列表(顺序即翻页顺序)。
    """
    os.makedirs(out_dir, exist_ok=True)
    pages = pages or []
    total = 1 + len(pages) + (1 if closing else 0)
    paths = []

    cover = os.path.join(out_dir, "card_1_cover.png")
    render_cover(cover, title, subtitle, footer=footer, page=1, total=total)
    paths.append(cover)

    for idx, pg in enumerate(pages, start=2):
        p = os.path.join(out_dir, f"card_{idx}.png")
        render_content(p, pg.get("heading", "重点速览"),
                       pg.get("points", []), page=idx, total=total, footer=footer)
        paths.append(p)

    if closing:
        last = len(paths) + 1
        p = os.path.join(out_dir, f"card_{last}_end.png")
        render_closing(p, closing, footer=footer, page=last, total=total)
        paths.append(p)

    return paths
