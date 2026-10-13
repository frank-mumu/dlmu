"""图文卡片渲染（Pillow 代码绘制，零 AI 出图成本）。输出 3:4 小红书卡片 PNG。

设计原则：每页内容丰富、有信息量，版式抓眼球，且**每页视觉有变化**。
- 内容页在「圆点气泡卡 / 描边编辑卡」两种版式间交替，并逐页轮换主题色，避免千篇一律。
- 封面：大色块标题 + 副标题胶囊 + “本期看点” + 页脚色带。
- 尾页：大面板 + 装饰 + 尾语 + 标签 + 页脚色带。
分页：封面 + 3-6 内容页 + 尾页，页码 i/N，合计 5-8 页。

内容页 page 结构：{"heading", "lead"?, "points":[...], "callout"?}
"""
import os

from PIL import Image, ImageDraw, ImageFont

from ..config import settings

W, H = 1080, 1440
ACCENT = (24, 119, 242)
LEAD_BG = (245, 247, 250)
INK = (34, 34, 34)
BODY = (64, 64, 64)
MUTED = (120, 120, 120)
BG = (255, 255, 255)
WHITE = (255, 255, 255)
FOOTER = "考研信息 · 干货分享"

# 内容页逐页轮换的协调主题色（封面/尾页固定用主蓝，形成品牌框）
PALETTE = [
    (24, 119, 242),   # 蓝
    (0, 150, 136),    # 青绿
    (67, 97, 238),    # 靛蓝
    (245, 124, 0),    # 橙
    (214, 48, 117),   # 玫红
    (67, 160, 71),    # 绿
]


def _lighten(color, white_frac=0.86):
    """把颜色往白色混合，得到浅色底。"""
    return tuple(int(c * (1 - white_frac) + 255 * white_frac) for c in color)


def _tint(color, white_frac=0.62):
    """比 _lighten 更深的浅色，用作描边/分隔。"""
    return tuple(int(c * (1 - white_frac) + 255 * white_frac) for c in color)


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


def _cx(draw, text, font):
    return (W - draw.textlength(text, font=font)) / 2


def _fit(draw, text, font, max_w):
    if draw.textlength(text, font=font) <= max_w:
        return text
    t = text
    while t and draw.textlength(t + "…", font=font) > max_w:
        t = t[:-1]
    return t + "…"


def _draw_centered(draw, cx, cy, text, font, fill):
    """把文字以 (cx, cy) 为几何中心真正居中（兼容任意字体度量）。"""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text((cx - tw / 2 - bbox[0], cy - th / 2 - bbox[1]), text, font=font, fill=fill)


def _footer_band(draw, footer, page, total, accent=ACCENT):
    draw.rectangle([0, H - 92, W, H], fill=accent)
    f = _font(36)
    draw.text((80, H - 64), footer, font=f, fill=WHITE)
    pt = f"{page}/{total}"
    draw.text((W - 80 - draw.textlength(pt, font=f), H - 64), pt, font=f, fill=WHITE)


def render_cover(path, title, subtitle="", footer=FOOTER, page=1, total=1,
                 tags=None, kicker="2026 考研 · 硕士招生速览", highlights=None):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 24], fill=ACCENT)

    # 大标题色块
    d.rounded_rectangle([60, 108, W - 60, 800], radius=32, fill=ACCENT)
    f_kick, f_title = _font(36), _font(80)
    if kicker:
        d.text((_cx(d, kicker, f_kick), 168), kicker, font=f_kick, fill=WHITE)
    lines = _wrap(d, title, f_title, W - 220)[:4]
    line_h = 104
    y = 240 + (630 - len(lines) * line_h) / 2
    for ln in lines:
        d.text((_cx(d, ln, f_title), y), ln, font=f_title, fill=WHITE)
        y += line_h

    # 副标题胶囊
    if subtitle:
        f_sub = _font(40)
        sw = d.textlength(subtitle, font=f_sub)
        cx = (W - sw) / 2
        d.rounded_rectangle([cx - 44, 838, cx + sw + 44, 932], radius=47, fill=_lighten(ACCENT))
        d.text((cx, 838 + (94 - 40) / 2), subtitle, font=f_sub, fill=ACCENT)

    # 本期看点
    items = (highlights or tags or [])[:3]
    if items:
        f_lab, f_it = _font(34), _font(38)
        d.text((80, 972), "本期看点", font=f_lab, fill=ACCENT)
        y = 1030
        for it in items:
            wrapped = _wrap(d, str(it), f_it, W - 210)[:2]
            d.rounded_rectangle([80, y + 12, 98, y + 30], radius=4, fill=ACCENT)
            for k, ln in enumerate(wrapped):
                d.text((118, y + k * 50), ln, font=f_it, fill=INK)
            y += 50 * len(wrapped) + 20

    _footer_band(d, footer, page, total)
    img.save(path, "PNG")


def _draw_title_band(d, heading, accent, style):
    f_h = _font(54)
    if style == 1:
        # 描边编辑风：白底 + 强调色描边 + 左侧强调色块 + 强调色标题字
        d.rounded_rectangle([60, 92, W - 60, 224], radius=26, fill=WHITE,
                            outline=accent, width=4)
        d.rounded_rectangle([60, 92, 98, 224], radius=10, fill=accent)
        d.text((120, 92 + (132 - 54) / 2), _fit(d, heading, f_h, W - 280),
               font=f_h, fill=accent)
    else:
        # 填充风：强调色色带 + 白字
        d.rounded_rectangle([60, 92, W - 60, 224], radius=26, fill=accent)
        d.text((100, 92 + (132 - 54) / 2), _fit(d, heading, f_h, W - 240),
               font=f_h, fill=WHITE)


def _draw_lead(d, lead, accent, y):
    if not lead:
        return y
    f_lead = _font(40)
    ll = _wrap(d, lead, f_lead, W - 240)[:3]
    lead_h = len(ll) * 56 + 44
    d.rounded_rectangle([60, y, W - 60, y + lead_h], radius=18, fill=LEAD_BG)
    d.rounded_rectangle([60, y, 76, y + lead_h], radius=8, fill=accent)
    ty = y + 22
    for ln in ll:
        d.text((102, ty), ln, font=f_lead, fill=BODY)
        ty += 56
    return y + lead_h + 26


def _draw_callout(d, callout, accent, top):
    f_co = _font(38)
    co_lines = _wrap(d, callout, f_co, W - 260)[:3]
    callout_h = len(co_lines) * 54 + 66
    cy0 = top - callout_h
    d.rounded_rectangle([60, cy0, W - 60, top], radius=22, fill=accent)
    d.text((96, cy0 + 16), "重点提示", font=_font(34), fill=WHITE)
    ty = cy0 + 60
    for ln in co_lines:
        d.text((96, ty), ln, font=f_co, fill=WHITE)
        ty += 54
    return callout_h


def _draw_points(d, points, accent, a_light, a_tint, y, bottom, style):
    n = max(1, len(points))
    gap = 24
    card_h = (bottom - y - gap * (n - 1)) / n
    f_b, fn = _font(42), _font(40)
    for i, p in enumerate(points, start=1):
        if style == 1:
            # 描边编辑卡：白底 + 浅描边 + 左侧强调色边 + 圆角方块编号
            d.rounded_rectangle([60, y, W - 60, y + card_h], radius=22,
                                fill=WHITE, outline=a_tint, width=3)
            d.rounded_rectangle([60, y, 88, y + card_h], radius=12, fill=accent)
            cy = y + card_h / 2
            d.rounded_rectangle([102, cy - 25, 150, cy + 25], radius=12, fill=accent)
            _draw_centered(d, 126, cy, str(i), fn, WHITE)
            tx = 176
        else:
            # 气泡卡：浅色卡 + 圆形编号徽章
            d.rounded_rectangle([60, y, W - 60, y + card_h], radius=22, fill=a_light)
            cy = y + card_h / 2
            d.ellipse([92, cy - 26, 144, cy + 26], fill=accent)
            _draw_centered(d, 118, cy, str(i), fn, WHITE)
            tx = 172
        lines = _wrap(d, str(p), f_b, W - 360)[:4]
        lh = 58
        ty = y + (card_h - len(lines) * lh) / 2
        for j, ln in enumerate(lines):
            d.text((tx, ty + j * lh), ln, font=f_b, fill=INK)
        y += card_h + gap


def render_content(path, heading, points, page=2, total=2, footer=FOOTER,
                   lead="", callout="", accent=ACCENT, style=0):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    a_light = _lighten(accent)
    a_tint = _tint(accent)
    d.rectangle([0, 0, W, 24], fill=accent)

    _draw_title_band(d, heading, accent, style)
    y = 252
    y = _draw_lead(d, lead, accent, y)

    co_h = _draw_callout(d, callout, accent, 1288) if callout else 0
    bottom = 1288 - (co_h + 26 if callout else 0)

    _draw_points(d, points, accent, a_light, a_tint, y, bottom, style)

    f_foot, f_pg = _font(30), _font(32)
    d.text((80, H - 60), footer, font=f_foot, fill=MUTED)
    pt = f"{page}/{total}"
    d.text((W - 80 - d.textlength(pt, font=f_pg), H - 60), pt, font=f_pg, fill=MUTED)
    # 页脚上方一条强调色细线，强化本页主题色
    d.rectangle([0, H - 96, W, H - 92], fill=accent)
    img.save(path, "PNG")


def render_closing(path, closing, footer=FOOTER, page=2, total=2, tags=None):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 24], fill=ACCENT)

    d.rounded_rectangle([60, 176, W - 60, 1006], radius=32, fill=_lighten(ACCENT))
    f_kick = _font(38)
    kicker = "写在最后"
    d.text((_cx(d, kicker, f_kick), 250), kicker, font=f_kick, fill=ACCENT)
    sq, gp = 22, 28
    sx = (W - (3 * sq + 2 * gp)) / 2
    for i in range(3):
        d.rounded_rectangle([sx + i * (sq + gp), 330, sx + i * (sq + gp) + sq, 330 + sq],
                            radius=6, fill=ACCENT)
    f_c = _font(54)
    lines = _wrap(d, closing, f_c, W - 260)[:6]
    line_h = 78
    y = 420 + (540 - len(lines) * line_h) / 2
    for ln in lines:
        d.text((_cx(d, ln, f_c), y), ln, font=f_c, fill=INK)
        y += line_h

    if tags:
        x, y2 = 70, 1056
        f_chip = _font(32)
        for t in tags[:8]:
            tw = d.textlength(t, font=f_chip)
            cw = tw + 44
            if x + cw > W - 70:
                x, y2 = 70, y2 + 70
            d.rounded_rectangle([x, y2, x + cw, y2 + 58], radius=29, fill=_lighten(ACCENT))
            d.text((x + 22, y2 + (58 - 32) / 2), t, font=f_chip, fill=ACCENT)
            x += cw + 18

    _footer_band(d, footer, page, total)
    img.save(path, "PNG")


def render_draft(out_dir, title, subtitle, pages, closing="", footer=FOOTER,
                 tags=None, kicker="2026 考研 · 硕士招生速览", highlights=None):
    """渲染一套分页卡片：封面 + 每页内容(逐页轮换主题色与版式) + 尾页 CTA。

    pages: [{"heading", "lead"?, "points":[...], "callout"?}, ...]
    返回图片路径列表(顺序即翻页顺序)。
    """
    os.makedirs(out_dir, exist_ok=True)
    pages = pages or []
    total = 1 + len(pages) + (1 if closing else 0)
    paths = []

    cover = os.path.join(out_dir, "card_1_cover.png")
    render_cover(cover, title, subtitle, footer=footer, page=1, total=total,
                 tags=tags, kicker=kicker, highlights=highlights)
    paths.append(cover)

    for idx, pg in enumerate(pages, start=2):
        p = os.path.join(out_dir, f"card_{idx}.png")
        accent = PALETTE[(idx - 2) % len(PALETTE)]
        style = (idx - 2) % 2
        render_content(p, pg.get("heading", "重点速览"), pg.get("points", []),
                       page=idx, total=total, footer=footer,
                       lead=pg.get("lead", ""), callout=pg.get("callout", ""),
                       accent=accent, style=style)
        paths.append(p)

    if closing:
        last = len(paths) + 1
        p = os.path.join(out_dir, f"card_{last}_end.png")
        render_closing(p, closing, footer=footer, page=last, total=total, tags=tags)
        paths.append(p)

    return paths
