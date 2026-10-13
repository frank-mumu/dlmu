"""周计划：一周聚焦一组相关主题，下周轮换到另一组，避免每天 12 主题全铺一遍。

- 12 个主题按内容关联性分成 4 组（每组 3 个），按自然周(ISO 周)轮换：
  第 N 周 → WEEK_PLANS[N % 4]。
- 创作任务每天凌晨跑，只从「本周组」里选题出稿；一组内 3 个主题 7 天足够轮透，
  还能对同一主题从不同角度多写几篇。
- 抓取任务不受影响（素材仍按全主题采集，供本周与未来周使用）。
"""
from datetime import date, timedelta

# 每周一组相关主题（3 个/组，共 4 组轮换）
WEEK_PLANS = [
    {
        "name": "择校选专业",
        "focus": "帮考生定学校、选专业：专业解读、报录数据、考试科目与参考书",
        "theme_keys": ["major_intro", "admission_stats", "exam_books"],
    },
    {
        "name": "读研投入产出",
        "focus": "读研值不值：导师科研、就业薪酬、奖助学费",
        "theme_keys": ["supervisor_research", "employment", "scholarship"],
    },
    {
        "name": "冲刺上岸与避坑",
        "focus": "临门一脚：复试调剂、考研政策、报考避坑",
        "theme_keys": ["retry_adjust", "policy", "pitfall"],
    },
    {
        "name": "备考方法与读研生活",
        "focus": "怎么备考、特殊人群跨考、读研的日常与城市",
        "theme_keys": ["prep_plan", "cross_exam", "campus_life"],
    },
]

# 主题 key → 中文名（与 themes.py 保持一致；仅用于展示）
_THEME_CN = {
    "major_intro": "院校专业解读",
    "admission_stats": "报录数据透视",
    "exam_books": "考试科目与参考书",
    "supervisor_research": "导师与科研方向",
    "employment": "就业与薪酬前景",
    "scholarship": "奖助学金与学费",
    "campus_life": "校园生活与城市",
    "retry_adjust": "复试与调剂策略",
    "policy": "考研政策与动态",
    "prep_plan": "备考规划与经验",
    "pitfall": "报考避坑指南",
    "cross_exam": "跨考与特殊群体",
}


def _monday(day):
    """该日期所在周的周一。"""
    d = date.fromisoformat(day) if isinstance(day, str) else day
    return d - timedelta(days=d.weekday())


def plan_for(day=None):
    """某日期所在周的周计划。day 缺省=今天。返回 dict。"""
    monday = _monday(day or date.today())
    # 用周一的 ISO 周数做稳定轮换锚点
    index = monday.isocalendar()[1] % len(WEEK_PLANS)
    plan = WEEK_PLANS[index]
    return {
        "week_start": monday.isoformat(),
        "week_end": (monday + timedelta(days=6)).isoformat(),
        "index": index,
        "name": plan["name"],
        "focus": plan["focus"],
        "theme_keys": list(plan["theme_keys"]),
        "themes_cn": [_THEME_CN.get(k, k) for k in plan["theme_keys"]],
    }


def upcoming(n=4, day=None):
    """从本周起的 n 周计划（含本周）。"""
    monday = _monday(day or date.today())
    return [plan_for(monday + timedelta(weeks=i)) for i in range(n)]


def render_markdown(n=4, day=None):
    """渲染未来 n 周计划为 Markdown（本周在前）。"""
    plans = upcoming(n, day)
    lines = ["# 考研内容周计划（本周起）", ""]
    for i, p in enumerate(plans):
        tag = "本周" if i == 0 else f"+{i} 周"
        lines.append(f"## {tag}｜{p['week_start']} ~ {p['week_end']}｜{p['name']}")
        lines.append("")
        lines.append(f"- 方向：{p['focus']}")
        lines.append(f"- 主题（{len(p['theme_keys'])} 个）：{'、'.join(p['themes_cn'])}")
        lines.append(f"- theme_keys：{', '.join(p['theme_keys'])}")
        lines.append("")
    lines.append("> 轮换规则：4 组按自然周循环；创作任务每天凌晨只从「本周组」选题出稿。")
    return "\n".join(lines)
