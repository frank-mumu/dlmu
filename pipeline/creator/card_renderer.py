"""图文卡片渲染（Pillow 代码绘制，零 AI 出图成本）。输出 3:4 小红书卡片 PNG。"""
import os

from PIL import Image, ImageDraw, ImageFont

from ..config import settings

W, H = 1080, 1440
ACCENT = (24, 119, 242)
INK = (34, 34, 34)
MUTED = (120, 120, 120)
BG = (255, 255, 255)

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
    for para in text.split("\n"):
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


def render_cover(path, title, subtitle=""):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 16], fill=ACCENT)
    f_title, f_sub, f_foot = _font(72), _font(40), _font(38)
    y = 220
    for ln in _wrap(d, title, f_title, W - 160)[:4]:
        d.text((80, y), ln, font=f_title, fill=INK)
        y += 96
    y += 40
    for ln in _wrap(d, subtitle, f_sub, W - 160)[:3]:
        d.text((80, y), ln, font=f_sub, fill=MUTED)
        y += 60
    d.rectangle([0, H - 90, W, H], fill=ACCENT)
    d.text((80, H - 70), "考研信息 · 干货分享", font=f_foot, fill=(255, 255, 255))
    img.save(path, "PNG")


def render_points(path, heading, points, page=1, total=1):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 16], fill=ACCENT)
    f_h, f_b, f_pg = _font(60), _font(42), _font(34)
    d.text((80, 120), heading[:16], font=f_h, fill=INK)
    y = 260
    for p in points:
        for i, ln in enumerate(_wrap(d, "· " + p, f_b, W - 160)):
            d.text((80 if i == 0 else 108, y), ln, font=f_b, fill=INK)
            y += 62
        y += 18
    d.text((80, H - 90), f"{page}/{total}", font=f_pg, fill=MUTED)
    img.save(path, "PNG")


def render_draft(out_dir, title, subtitle, points):
    """渲染一套卡片，返回图片路径列表。"""
    os.makedirs(out_dir, exist_ok=True)
    paths = []
    cover = os.path.join(out_dir, "card_1_cover.png")
    render_cover(cover, title, subtitle)
    paths.append(cover)
    per = 6
    pages = [points[i:i + per] for i in range(0, len(points), per)] or [[]]
    total = len(pages) + 1
    for idx, pg in enumerate(pages, start=2):
        p = os.path.join(out_dir, f"card_{idx}.png")
        render_points(p, subtitle or "重点速览", pg, page=idx, total=total)
        paths.append(p)
    return paths
