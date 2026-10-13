"""页面布局词汇表：定义一套可轮换的「内容页布局」，打破「每页都是 1-2-3」的单调感。

设计原则（用户明确）：
- 同一篇（一个话题）内，整体视觉风格（主题色、字体、装饰语言）必须保持一致；
- 变化应体现在「不同话题 / 不同天」之间，以及「同一篇内每页用不同布局」；
- 仅靠配色变化不够，每页要有不同的版式结构，并加入图形元素（非纯文字）。

每种布局声明：
- name / 中文名 / 适用场景
- fields：该布局需要的 JSON 字段（创作 Agent 据此产出）
- 示例片段
渲染器 (card_renderer) 按 page["layout"] 分派到对应绘制函数。
"""
from . import style_guide

PAGE_LAYOUTS = [
    {
        "name": "list",
        "cn": "要点清单",
        "when": "干货罗列、信息密度高的页面（如「公平体现在哪」）",
        "fields": {"heading": "结论式小标题", "lead": "你字句引入",
                   "points": "[2-4 条要点，结论先行+校事实]", "callout": "可选重点/避坑"},
        "example": {"layout": "list", "heading": "公平，体现在这 3 件事上",
                    "lead": "你最担心的歧视问题，海大其实挺克制。",
                    "points": ["✅ 保护一志愿，校内调剂优先一志愿考生",
                               "✅ 复试看总分与专业素养，不唯出身",
                               "✅ 公示透明，初复试占比明确"],
                    "callout": "💡 以上为公开考情总结，精确数字以官网为准"},
    },
    {
        "name": "checks",
        "cn": "避坑清单",
        "when": "提醒类页面（如「这些坑别踩」「报考注意事项」）",
        "fields": {"heading": "结论式小标题", "lead": "你字句引入",
                   "points": "[2-4 条避坑要点]", "callout": "可选补充"},
        "example": {"layout": "checks", "heading": "这几个坑，我替你踩过了",
                    "lead": "信息差最容易翻车，先把这几条记牢。",
                    "points": ["🚫 别信「保录」「内部资料」的卖课党",
                               "🚫 别只看热门专业，友好梯队性价比更高",
                               "✅ 官网+研招网才是唯一信源，别被营销号带节奏"],
                    "callout": "💡 精确数字一律以官网/研招网为准"},
    },
    {
        "name": "steps",
        "cn": "流程步骤",
        "when": "有先后顺序的内容（如「双非跨考 4 步」「备考节奏」）",
        "fields": {"heading": "结论式小标题", "lead": "你字句引入",
                   "points": "[3-5 步，每步一句结论+做法]", "callout": "可选"},
        "example": {"layout": "steps", "heading": "双非跨考海大，照这 4 步走",
                    "lead": "别一上来就焦虑，按节奏来最稳。",
                    "points": ["定方向：先锁定考 408 的电子信息(085400)等友好专业",
                               "补基础：跨考先啃专业课参考书+近 10 年真题",
                               "冲真题：9 月后全真模拟，卡时间找手感",
                               "盯信息：10 月起盯紧官网简章与专业目录变动"],
                    "callout": "💡 每步别贪多，踏实走完就赢了一半"},
    },
    {
        "name": "compare",
        "cn": "左右对比",
        "when": "对立/对照类内容（如「误区 vs 正解」「学硕 vs 专硕」「海大 vs 他校」）",
        "fields": {"heading": "结论式小标题", "lead": "你字句引入",
                   "left_title": "左栏标题(如「常见误区」)",
                   "left": "[左栏要点]", "right_title": "右栏标题(如「正确做法」)",
                   "right": "[右栏要点]", "callout": "可选"},
        "example": {"layout": "compare", "heading": "别被误区带偏了",
                    "lead": "你听到的，未必是海大的真情况。",
                    "left_title": "❌ 常见误区", "left": ["双非肯定被刷", "热门专业才好"],
                    "right_title": "✅ 海大实际情况",
                    "right": ["保护一志愿、看总分", "友好梯队性价比更高"],
                    "callout": "💡 以官网最新简章为准"},
    },
    {
        "name": "stat",
        "cn": "数据卡",
        "when": "突出一个关键数字/标签（如「211 / 双一流」「考 408 的专业」）",
        "fields": {"heading": "结论式小标题", "lead": "你字句引入",
                   "figure": "大字号核心数字/标签(如 211 / 408 / 双一流)",
                   "label": "数字下方说明", "note": "补充句",
                   "chips": "[3 个短标签，点缀]", "callout": "可选"},
        "example": {"layout": "stat", "heading": "它到底是什么来头",
                    "lead": "你冲 211，得先知道它的牌面。",
                    "figure": "211", "label": "交通运输部直属 · 双一流",
                    "note": "行业认可度拉满，性价比被严重低估",
                    "chips": ["行业硬通货", "保护一志愿", "不卡出身"],
                    "callout": "💡 具体招生以官网为准"},
    },
    {
        "name": "grid",
        "cn": "信息网格",
        "when": "一组并列条目（如「4 个推荐专业」「院校亮点」）",
        "fields": {"heading": "结论式小标题", "lead": "你字句引入",
                   "items": "[{title:专业名(含代码), desc:一句话亮点}, ...](2-4 个)",
                   "callout": "可选"},
        "example": {"layout": "grid", "heading": "这 4 个专业，值得你冲",
                    "lead": "按「友好度+就业」给你筛了一遍。",
                    "items": [{"title": "交通运输工程 0823", "desc": "双一流学科，行业认可度高"},
                              {"title": "计算机 081200", "desc": "考 408，资料公开透明"},
                              {"title": "电子信息 085400", "desc": "专硕，招生体量大"},
                              {"title": "法学 030100", "desc": "含海商法特色方向"}],
                    "callout": "💡 选专业看兴趣+就业，别盲冲热门"},
    },
    {
        "name": "quote",
        "cn": "金句页",
        "when": "强调/收束/价值观页（如「写在中间的一句话」）",
        "fields": {"heading": "结论式小标题(可选,可空)", "quote": "一句有分量的大白话",
                   "attribution": "可选落款(如「—— 一个上岸学姐」)", "callout": "可选"},
        "example": {"layout": "quote", "heading": "",
                    "quote": "考研拼的不是出身，是信息差——而海大，把门敞得很开。",
                    "attribution": "—— 写给还在犹豫的你",
                    "callout": "💡 想看哪个专业深拆？评论区告诉我"},
    },
]

LAYOUT_NAMES = [l["name"] for l in PAGE_LAYOUTS]


def layouts_text():
    """渲染成可读文字，注入写作规范 / 简报。"""
    lines = ["【页面布局（同一篇内请轮换使用，禁止每页都是「1-2-3」清单）】"]
    lines.append("同一篇视觉风格(主题色/字体/装饰)保持一致；变化靠「每页不同布局」+「不同话题换主题色」实现。")
    lines.append("每页从下列选 1 种 layout（相邻页尽量不重复），并按其 fields 给字段：\n")
    for l in PAGE_LAYOUTS:
        lines.append(f"▸ {l['name']}（{l['cn']}）—— 适用：{l['when']}")
        fields = "、".join(l["fields"].keys())
        lines.append(f"   字段：{fields}")
    lines.append("")
    lines.append("示例：")
    for l in PAGE_LAYOUTS:
        ex = l["example"]
        lines.append(f"  · {l['name']}: {ex.get('heading') or ex.get('quote')}")
    return "\n".join(lines)


def layouts_json():
    return [{"name": l["name"], "cn": l["cn"], "when": l["when"],
             "fields": list(l["fields"].keys()), "example": l["example"]}
            for l in PAGE_LAYOUTS]
