"""选题引擎：按「主题 × 日期」产出候选 topic。

- 主题(Theme)一次性定义（见 themes.py），每个主题有 scope(school/general/both)。
- 对学校定向主题：目标学校池每校生成一条 topic；公共主题：生成一条通用 topic。
- 每个 topic 带 period(YYYY-MM-DD)，按 (theme_id, period, school_id) 去重，
  保证周期任务每次只产「今天」的新 topic，不重复。
- 后续可在规则基础上叠加 LLM 选题 / 热点权重 / metrics 回流调权。
"""
from datetime import date

from ..storage import repo

_LEVEL_SCORE = {"985": 3.0, "211": 2.0, "双一流": 1.5}


def _period_label(period=None):
    return period or date.today().isoformat()


def _level_score(level):
    score = 0.3
    if level:
        for key, val in _LEVEL_SCORE.items():
            if key in level:
                score += val
    return score


def _ensure_topic(session, theme, school=None, period=None):
    """为某主题(在某学校/公共范围)创建当天 period 的 topic；已存在则跳过。"""
    scope_label = school.name if school else "考研公共"
    title = f"{theme.name}｜{scope_label} · {period}"
    kind = "school" if school else "public"
    school_id = school.id if school else None
    rationale = f"主题[{theme.name}/{theme.audience}]；范围={scope_label}"
    if school:
        rationale += f"；{school.province or ''}{school.level or ''}"
    topic, is_new = repo.create_topic(
        session, title=title, kind=kind, school_id=school_id,
        rationale=rationale, score=round(_level_score(school.level if school else None), 2),
        theme_id=theme.id, period=period)
    return topic, is_new


def run(session, period=None, theme_keys=None):
    """遍历 active 主题，按 scope 生成今天 period 的候选 topic。返回新建列表。

    theme_keys: 只为这些主题生成 topic（周计划模式：本周只铺本周组的主题）。
    """
    label = _period_label(period)
    created = []
    for theme in repo.active_themes(session):
        if theme_keys is not None and theme.key not in theme_keys:
            continue
        if theme.scope in ("school", "both"):
            for school in repo.pool_schools(session):
                topic, is_new = _ensure_topic(session, theme, school=school, period=label)
                if is_new:
                    created.append(topic)
        if theme.scope in ("general", "both"):
            topic, is_new = _ensure_topic(session, theme, school=None, period=label)
            if is_new:
                created.append(topic)
    return created
