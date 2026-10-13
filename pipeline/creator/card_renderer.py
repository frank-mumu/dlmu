"""图文卡片渲染（Pillow 代码绘制，零 AI 出图成本）。输出 3:4 小红书卡片 PNG。

设计原则：
- 同一篇（一个话题）内视觉风格一致：统一主题色 + 统一字体/装饰语言；主题色按 topic 确定性分配，
  不同话题 / 不同天自然不同（变化发生在「话题间」，而非单篇内）。
- 每页用不同「布局」打破单调：list / checks / steps / compare / stat / grid / quote（见 layouts.py）。
- 加入手绘图形元素（图标、连接线、迷你图表、装饰），不再是纯文字。

页面 page 结构（按 layout 不同字段不同，见 layouts.PAGE_LAYOUTS）：
  {"heading"?, "lead"?, "layout"?, "points"?, "left/right"?, "figure/label/note/chips"?,
   "items"?, "quote/attribution"?, "callout"?}
"""
import math
import os
import re

from PIL import Image, ImageDraw, ImageFont

from ..config import settings

W, H = 1080, 1440
ACCENT = (24, 119, 242)          # 默认主蓝（封面/尾页/未指定时的兜底）
LEAD_BG = (245, 247, 250)
INK = (34, 34, 34)
BODY = (64, 64, 64)
MUTED = (120, 120, 120)
BG = (255, 255, 255)
WHITE = (255, 255, 255)
FOOTER = "考研信息 · 干货分享"

# 内容页逐 topic 轮换的协调主题色（同一篇内固定；不同话题/天不同）
PALETTE = [
    (24, 119, 242),   # 蓝
    (0, 150, 136),    # 青绿
    (67, 97, 238),    # 靛蓝
    (245, 124, 0),    # 橙
    (214, 48, 117),   # 玫红
    (67, 160, 71),    # 绿
]


def accent_for(topic_id):
    """按 topic 确定性分配主题色：同一篇内固定，跨话题/天自然变化。"""
    return PALETTE[(int(topic_id) * 7) % len(PALETTE)]


def _lighten(color, white_frac=0.86):
    return tuple(int(c * (1 - white_frac) + 255 * white_frac) for c in color)


def _tint(color, white_frac=0.62):
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


_ASCII_RUN = re.compile(r"[A-Za-z0-9][A-Za-z0-9+./:#%\-]*")


def _tokenize(para):
    """切 token：ASCII 连续串(如 620+812、085400、408)整体不拆，其余按单字。"""
    tokens, i, n = [], 0, len(para)
    while i < n:
        m = _ASCII_RUN.match(para, i)
        if m:
            tokens.append(m.group(0))
            i = m.end()
        else:
            tokens.append(para[i])
            i += 1
    return tokens


def _wrap(draw, text, font, max_w):
    lines = []
    for para in str(text).split("\n"):
        if not para:
            lines.append("")
            continue
        cur = ""
        for tok in _tokenize(para):
            if draw.textlength(cur + tok, font=font) <= max_w:
                cur += tok
                continue
            if cur:
                lines.append(cur)
            if draw.textlength(tok, font=font) > max_w:   # 单 token 超宽 → 逐字兜底
                sub = ""
                for ch in tok:
                    if draw.textlength(sub + ch, font=font) <= max_w:
                        sub += ch
                    else:
                        lines.append(sub)
                        sub = ch
                cur = sub
            else:
                cur = tok
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
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    draw.text((cx - tw / 2 - bbox[0], cy - th / 2 - bbox[1]), text, font=font, fill=fill)


# Pillow 无彩色 emoji 字体，正文里的 emoji 不显示；这些标记交给「手绘图形」表达，
# 显示前把行首的标记符号去掉，避免留空/豆腐块。
_MARK_CHARS = set("🚫❌✗✖×✅✔💡📌⚠👉🔥✨🎯💪🚢⚙📱⚖💻🔍🚦🧭👍❗❓·•-—:： \uFE0F\u200d")


def _strip_marks(s):
    t = str(s)
    while t and t[0] in _MARK_CHARS:
        t = t[1:]
    return t.lstrip() or str(s)


def _is_negative(text):
    s = str(text).lstrip()
    if s[:1] in ("🚫", "❌", "✗", "✖", "×"):
        return True
    return _strip_marks(s)[:1] in ("别", "不", "勿", "禁")


# ───────────────────────── 手绘图形（图标 / 装饰） ─────────────────────────
def _check(draw, cx, cy, r, color, w=10):
    draw.line([(cx - r * 0.62, cy - r * 0.02), (cx - r * 0.12, cy + r * 0.55)],
              fill=color, width=w)
    draw.line([(cx - r * 0.12, cy + r * 0.55), (cx + r * 0.68, cy - r * 0.6)],
              fill=color, width=w)


def _cross(draw, cx, cy, r, color, w=10):
    draw.line([(cx - r * 0.6, cy - r * 0.6), (cx + r * 0.6, cy + r * 0.6)], fill=color, width=w)
    draw.line([(cx - r * 0.6, cy + r * 0.6), (cx + r * 0.6, cy - r * 0.6)], fill=color, width=w)


def _arrow(draw, x, y, w, h, color, wline=8):
    draw.line([(x, y + h / 2), (x + w * 0.66, y + h / 2)], fill=color, width=wline)
    draw.polygon([(x + w * 0.52, y), (x + w, y + h / 2), (x + w * 0.52, y + h)], fill=color)


def _star(draw, cx, cy, r, color):
    pts = []
    for i in range(5):
        a = -math.pi / 2 + i * 2 * math.pi / 5
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        a2 = a + math.pi / 5
        pts.append((cx + r * 0.45 * math.cos(a2), cy + r * 0.45 * math.sin(a2)))
    draw.polygon(pts, fill=color)


def _target(draw, cx, cy, r, color, wline=6):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=wline)
    draw.ellipse([cx - r * 0.55, cy - r * 0.55, cx + r * 0.55, cy + r * 0.55],
                 outline=color, width=wline)
    draw.ellipse([cx - 6, cy - 6, cx + 6, cy + 6], fill=color)


def _book(draw, cx, cy, r, color, wline=6):
    x, y, w, h = cx - r, cy - r, 2 * r, 2 * r
    draw.rounded_rectangle([x, y, x + w, y + h], radius=8, outline=color, width=wline)
    draw.line([(cx, y + 10), (cx, y + h - 10)], fill=color, width=wline)


def _shield(draw, cx, cy, r, color, wline=6):
    pts = [(cx, cy - r), (cx + r, cy - r * 0.4), (cx + r * 0.7, cy + r * 0.6),
           (cx, cy + r), (cx - r * 0.7, cy + r * 0.6), (cx - r, cy - r * 0.4)]
    draw.polygon(pts, outline=color, width=wline)


def _bulb(draw, cx, cy, r, color, wline=6):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=wline)
    draw.rectangle([cx - r * 0.4, cy + r * 0.65, cx + r * 0.4, cy + r * 1.15], outline=color, width=wline)


_ICONS = {"check": _check, "target": _target, "star": _star, "book": _book,
          "shield": _shield, "bulb": _bulb}


def _icon(draw, name, cx, cy, r, color):
    fn = _ICONS.get(name)
    if fn:
        fn(draw, cx, cy, r, color)


# ───────────────────────── 公共版块 ─────────────────────────
def _footer_band(draw, footer, page, total, accent=ACCENT):
    draw.rectangle([0, H - 92, W, H], fill=accent)
    f = _font(36)
    draw.text((80, H - 64), footer, font=f, fill=WHITE)
    pt = f"{page}/{total}"
    draw.text((W - 80 - draw.textlength(pt, font=f), H - 64), pt, font=f, fill=WHITE)


def _header_band(draw, heading, accent):
    f_h = _font(54)
    draw.rounded_rectangle([60, 92, W - 60, 224], radius=26, fill=accent)
    draw.text((100, 92 + (132 - 54) / 2), _fit(draw, heading, f_h, W - 240),
              font=f_h, fill=WHITE)


def _lead(draw, lead, accent, y):
    if not lead:
        return y
    f_lead = _font(40)
    ll = _wrap(draw, lead, f_lead, W - 240)[:3]
    lead_h = len(ll) * 56 + 44
    draw.rounded_rectangle([60, y, W - 60, y + lead_h], radius=18, fill=LEAD_BG)
    draw.rounded_rectangle([60, y, 76, y + lead_h], radius=8, fill=accent)
    ty = y + 22
    for ln in ll:
        draw.text((102, ty), ln, font=f_lead, fill=BODY)
        ty += 56
    return y + lead_h + 26


def _callout(draw, callout, accent, top):
    f_co = _font(38)
    co_lines = _wrap(draw, callout, f_co, W - 260)[:3]
    callout_h = len(co_lines) * 54 + 66
    cy0 = top - callout_h
    draw.rounded_rectangle([60, cy0, W - 60, top], radius=22, fill=accent)
    draw.text((96, cy0 + 16), "重点提示", font=_font(34), fill=WHITE)
    ty = cy0 + 60
    for ln in co_lines:
        draw.text((96, ty), ln, font=f_co, fill=WHITE)
        ty += 54
    return callout_h


# ───────────────────────── 各布局绘制（body 区域：y..bottom） ─────────────────────────
def _draw_text_block(d, text, font, tx, card_top, card_h):
    """在卡片内垂直居中多行文字（结论先行，最多 4 行）。"""
    lines = _wrap(d, _strip_marks(text), font, W - 360)[:4]
    lh = 58
    ty = card_top + (card_h - len(lines) * lh) / 2
    for j, ln in enumerate(lines):
        d.text((tx, ty + j * lh), ln, font=font, fill=INK)


def _body_list(d, page, accent, a_light, a_tint, y, bottom):
    pts = page.get("points", []) or []
    n = max(1, len(pts))
    gap = 24
    card_h = (bottom - y - gap * (n - 1)) / n
    f_b, fn = _font(42), _font(40)
    for i, p in enumerate(pts, start=1):
        d.rounded_rectangle([60, y, W - 60, y + card_h], radius=22, fill=a_light)
        cy = y + card_h / 2
        d.ellipse([92, cy - 26, 144, cy + 26], fill=accent)
        _draw_centered(d, 118, cy, str(i), fn, WHITE)
        _draw_text_block(d, p, f_b, 172, y, card_h)
        y += card_h + gap


def _body_checks(d, page, accent, a_light, a_tint, y, bottom):
    pts = page.get("points", []) or []
    n = max(1, len(pts))
    gap = 24
    card_h = (bottom - y - gap * (n - 1)) / n
    f_b = _font(42)
    for p in pts:
        d.rounded_rectangle([60, y, W - 60, y + card_h], radius=22, fill=WHITE,
                            outline=a_tint, width=3)
        cy = y + card_h / 2
        neg = _is_negative(p)
        d.rounded_rectangle([92, cy - 28, 148, cy + 28], radius=14,
                            fill=_lighten(accent) if neg else accent)
        if neg:
            _cross(d, 120, cy, 20, accent, w=8)
        else:
            _check(d, 120, cy, 22, WHITE, w=8)
        _draw_text_block(d, p, f_b, 178, y, card_h)
        y += card_h + gap


def _body_steps(d, page, accent, a_light, a_tint, y, bottom):
    pts = page.get("points", []) or []
    n = max(1, len(pts))
    gap = 26
    node_r = 34
    line_x = 118
    row_h = (bottom - y - gap * (n - 1)) / n
    f_b = _font(42)
    if n > 1:
        d.line([(line_x, y + row_h / 2), (line_x, y + (n - 1) * (row_h + gap) + row_h / 2)],
               fill=a_light, width=10)
    for i, p in enumerate(pts, start=1):
        cy = y + row_h / 2
        d.ellipse([line_x - node_r, cy - node_r, line_x + node_r, cy + node_r], fill=accent)
        _draw_centered(d, line_x, cy, str(i), _font(40), WHITE)
        _draw_text_block(d, p, f_b, 184, y, row_h)
        y += row_h + gap


def _draw_compare_item(d, text, font, x, cy, w, accent, kind, badge_fill):
    r = 22
    if kind == "cross":
        d.rounded_rectangle([x, cy - r, x + 2 * r, cy + r], radius=11, fill=_lighten(accent))
        _cross(d, x + r, cy, r * 0.7, accent, w=7)
    else:
        d.rounded_rectangle([x, cy - r, x + 2 * r, cy + r], radius=11, fill=accent)
        _check(d, x + r, cy, r * 0.7, badge_fill, w=7)
    lines = _wrap(d, _strip_marks(text), font, w - 2 * r - 16)[:3]
    ty = cy - len(lines) * 23
    for ln in lines:
        d.text((x + 2 * r + 16, ty), ln, font=font, fill=INK)
        ty += 46


def _body_compare(d, page, accent, a_light, a_tint, y, bottom):
    left_title = page.get("left_title", "误区")
    right_title = page.get("right_title", "正解")
    left = page.get("left", []) or []
    right = page.get("right", []) or []
    mid = W / 2
    col_w = (W - 120 - 40) / 2
    d.rounded_rectangle([60, y, mid - 20, bottom], radius=22, fill=a_light)
    d.rounded_rectangle([mid + 20, y, W - 60, bottom], radius=22, fill=WHITE,
                        outline=a_tint, width=3)
    f_t = _font(40)
    d.text((80, y + 18), left_title, font=f_t, fill=accent)
    d.text((mid + 40, y + 18), right_title, font=f_t, fill=accent)
    d.line([(mid, y + 14), (mid, bottom - 14)], fill=a_tint, width=4)
    inner_top = y + 84
    inner_h = bottom - 20 - inner_top
    half = max(1, max(len(left), len(right)))
    rh = min(inner_h / half, 170)
    start = inner_top + max(0, (inner_h - rh * half) / 2)
    for i in range(half):
        cy = start + i * rh + 22
        if i < len(left):
            _draw_compare_item(d, left[i], _font(36), 80, cy, col_w - 40, accent, "cross", a_light)
        if i < len(right):
            _draw_compare_item(d, right[i], _font(36), mid + 40, cy, col_w - 40, accent, "check", WHITE)
    d.ellipse([mid - 34, (y + bottom) / 2 - 34, mid + 34, (y + bottom) / 2 + 34], fill=accent)
    _draw_centered(d, mid, (y + bottom) / 2, "VS", _font(34), WHITE)


def _body_stat(d, page, accent, a_light, a_tint, y, bottom):
    figure = str(page.get("figure", ""))
    label = page.get("label", "")
    note = page.get("note", "")
    chips = page.get("chips", []) or []
    f_n = _font(38)
    note_lines = _wrap(d, note, f_n, W - 200)[:2] if note else []
    tail = (30 + len(note_lines) * 52) if note_lines else 0
    tail += (24 + 64) if chips else 0
    panel_h = (bottom - y) - tail
    if panel_h < (bottom - y) * 0.5:
        panel_h = (bottom - y) * 0.5
    d.rounded_rectangle([60, y, W - 60, y + panel_h], radius=26, fill=accent)
    f_fig = _font(190)
    figure = _fit(d, figure, f_fig, W - 160)
    _draw_centered(d, W / 2, y + panel_h * 0.44, figure, f_fig, WHITE)
    if label:
        fl = _wrap(d, label, _font(40), W - 240)[:2]
        ly = y + panel_h - 30 - len(fl) * 46
        for ln in fl:
            d.text((_cx(d, ln, _font(40)), ly), ln, font=_font(40), fill=WHITE)
            ly += 46
    yy = y + panel_h + 30
    for ln in note_lines:
        d.text((100, yy), ln, font=f_n, fill=BODY)
        yy += 52
    if chips:
        yy += 24
        cx = 100
        f_chip = _font(34)
        icon_names = ["star", "target", "shield", "book", "bulb"]
        for i, c in enumerate(chips[:5]):
            tw = d.textlength(c, font=f_chip)
            cw = tw + 80
            if cx + cw > W - 80:
                break
            d.rounded_rectangle([cx, yy, cx + cw, yy + 64], radius=32, fill=a_light)
            _icon(d, icon_names[i % len(icon_names)], cx + 34, yy + 32, 18, accent)
            d.text((cx + 64, yy + (64 - 34) / 2), c, font=f_chip, fill=accent)
            cx += cw + 18


def _body_grid(d, page, accent, a_light, a_tint, y, bottom):
    items = page.get("items", []) or []
    n = max(1, len(items))
    cols = 2
    rows = (n + cols - 1) // cols
    gap = 24
    card_w = (W - 120 - gap) / cols
    card_h = (bottom - y - gap * (rows - 1)) / rows
    f_t, f_d = _font(40), _font(34)
    icon_names = ["book", "star", "target", "shield", "bulb", "check"]
    for i, it in enumerate(items):
        r, c = divmod(i, cols)
        x = 60 + c * (card_w + gap)
        cy0 = y + r * (card_h + gap)
        d.rounded_rectangle([x, cy0, x + card_w, cy0 + card_h], radius=22, fill=a_light)
        d.rounded_rectangle([x, cy0, x + 14, cy0 + card_h], radius=8, fill=accent)
        title = it.get("title", "") if isinstance(it, dict) else str(it)
        desc = it.get("desc", "") if isinstance(it, dict) else ""
        _icon(d, icon_names[i % len(icon_names)], x + card_w - 46, cy0 + 46, 22, accent)
        d.text((x + 34, cy0 + 26), _fit(d, title, f_t, card_w - 110), font=f_t, fill=INK)
        ty = cy0 + 26 + 56
        for ln in _wrap(d, desc, f_d, card_w - 70)[:3]:
            d.text((x + 34, ty), ln, font=f_d, fill=BODY)
            ty += 44


def _body_quote(d, page, accent, a_light, a_tint, y, bottom):
    quote = page.get("quote", "")
    attribution = page.get("attribution", "")
    d.arc([80, y, 300, y + 220], 90, 210, fill=accent, width=22)
    d.arc([150, y, 370, y + 220], 90, 210, fill=accent, width=22)
    f_q = _font(52)
    lines = _wrap(d, quote, f_q, W - 220)[:6]
    lh = 76
    ty = y + 250 + (bottom - 250 - y - 160 - len(lines) * lh) / 2
    if ty < y + 250:
        ty = y + 250
    for ln in lines:
        d.text((110, ty), ln, font=f_q, fill=INK)
        ty += lh
    if attribution:
        d.text((110, bottom - 150), attribution, font=_font(36), fill=accent)


_BODY_DISPATCH = {
    "list": _body_list,
    "checks": _body_checks,
    "steps": _body_steps,
    "compare": _body_compare,
    "stat": _body_stat,
    "grid": _body_grid,
    "quote": _body_quote,
}


def render_content(path, page, page_no=2, total=2, footer=FOOTER, accent=ACCENT):
    layout = page.get("layout", "list")
    heading = page.get("heading", "")
    lead = page.get("lead", "")
    callout = page.get("callout", "")
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    a_light = _lighten(accent)
    a_tint = _tint(accent)
    d.rectangle([0, 0, W, 24], fill=accent)

    if layout != "quote" or heading:
        _header_band(d, heading or "重点速览", accent)
    y = 252
    y = _lead(d, lead, accent, y)

    co_h = _callout(d, callout, accent, 1288) if callout else 0
    bottom = 1288 - (co_h + 26 if callout else 0)

    fn = _BODY_DISPATCH.get(layout, _body_list)
    fn(d, page, accent, a_light, a_tint, y, bottom)

    d.rectangle([0, H - 96, W, H - 92], fill=accent)
    _footer_band(d, footer, page_no, total, accent)
    img.save(path, "PNG")


def render_cover(path, title, subtitle="", footer=FOOTER, page=1, total=1,
                 tags=None, kicker="2026 考研 · 硕士招生速览", highlights=None, accent=ACCENT):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 24], fill=accent)

    d.rounded_rectangle([60, 108, W - 60, 800], radius=32, fill=accent)
    f_kick, f_title = _font(36), _font(80)
    if kicker:
        d.text((_cx(d, kicker, f_kick), 168), kicker, font=f_kick, fill=WHITE)
    lines = _wrap(d, title, f_title, W - 220)[:4]
    line_h = 104
    y = 240 + (630 - len(lines) * line_h) / 2
    for ln in lines:
        d.text((_cx(d, ln, f_title), y), ln, font=f_title, fill=WHITE)
        y += line_h

    if subtitle:
        f_sub = _font(40)
        sw = d.textlength(subtitle, font=f_sub)
        cx = (W - sw) / 2
        d.rounded_rectangle([cx - 44, 838, cx + sw + 44, 932], radius=47, fill=_lighten(accent))
        d.text((cx, 838 + (94 - 40) / 2), subtitle, font=f_sub, fill=accent)

    items = (highlights or tags or [])[:3]
    if items:
        f_lab, f_it = _font(34), _font(38)
        d.text((80, 972), "本期看点", font=f_lab, fill=accent)
        y = 1030
        for it in items:
            wrapped = _wrap(d, str(it), f_it, W - 210)[:2]
            d.rounded_rectangle([80, y + 12, 98, y + 30], radius=4, fill=accent)
            for k, ln in enumerate(wrapped):
                d.text((118, y + k * 50), ln, font=f_it, fill=INK)
            y += 50 * len(wrapped) + 20

    _footer_band(d, footer, page, total, accent)
    img.save(path, "PNG")


def render_closing(path, closing, footer=FOOTER, page=2, total=2, tags=None, accent=ACCENT):
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 24], fill=accent)

    d.rounded_rectangle([60, 176, W - 60, 1006], radius=32, fill=_lighten(accent))
    f_kick = _font(38)
    d.text((_cx(d, "写在最后", f_kick), 250), "写在最后", font=f_kick, fill=accent)
    sq, gp = 22, 28
    sx = (W - (3 * sq + 2 * gp)) / 2
    for i in range(3):
        d.rounded_rectangle([sx + i * (sq + gp), 330, sx + i * (sq + gp) + sq, 330 + sq],
                            radius=6, fill=accent)
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
            d.rounded_rectangle([x, y2, x + cw, y2 + 58], radius=29, fill=_lighten(accent))
            d.text((x + 22, y2 + (58 - 32) / 2), t, font=f_chip, fill=accent)
            x += cw + 18

    _footer_band(d, footer, page, total, accent)
    img.save(path, "PNG")


def render_draft(out_dir, title, subtitle, pages, closing="", footer=FOOTER,
                 tags=None, kicker="2026 考研 · 硕士招生速览", highlights=None, accent=ACCENT):
    """渲染一套分页卡片：封面 + 每页内容(按各自 layout 绘制) + 尾页 CTA。

    同一篇统一用传入的 accent（由调用方按 topic 决定），保证视觉一致。
    pages: [{"heading"?, "lead"?, "layout"?, ...各布局字段}, ...]
    返回图片路径列表(顺序即翻页顺序)。
    """
    os.makedirs(out_dir, exist_ok=True)
    pages = pages or []
    total = 1 + len(pages) + (1 if closing else 0)
    paths = []

    cover = os.path.join(out_dir, "card_1_cover.png")
    render_cover(cover, title, subtitle, footer=footer, page=1, total=total,
                 tags=tags, kicker=kicker, highlights=highlights, accent=accent)
    paths.append(cover)

    for idx, pg in enumerate(pages, start=2):
        p = os.path.join(out_dir, f"card_{idx}.png")
        render_content(p, pg, page_no=idx, total=total, footer=footer, accent=accent)
        paths.append(p)

    if closing:
        last = len(paths) + 1
        p = os.path.join(out_dir, f"card_{last}_end.png")
        render_closing(p, closing, footer=footer, page=last, total=total, tags=tags, accent=accent)
        paths.append(p)

    return paths
