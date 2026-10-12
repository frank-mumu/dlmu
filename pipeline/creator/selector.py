"""选题引擎：从 raw_items + 学校池产出候选选题（公共 + 学校定向）。Phase 1 用规则法。

后续可在规则基础上叠加 LLM 选题 / 热点权重 / metrics 回流调权。
"""
from ..storage import repo

_LEVEL_SCORE = {"985": 3.0, "211": 2.0, "双一流": 1.5}


def _level_score(level):
    score = 0.5
    if level:
        for key, val in _LEVEL_SCORE.items():
            if key in level:
                score += val
    return score


def run(session):
    """生成候选选题，返回新建的 Topic 列表。"""
    created = []

    # 学校定向选题：目标学校池中，近期有目录同步的学校
    for school in repo.pool_schools(session):
        items = repo.recent_raw_items(session, since_hours=24 * 30,
                                      kind="catalog", school_id=school.id, limit=1)
        if not items:
            continue
        item = items[0]
        major_count = (item.meta or {}).get("major_count", 0)
        score = _level_score(school.level) + min(major_count, 20) * 0.1
        title = f"{school.name}考研｜2026 硕士招生速览与报考要点"
        topic, is_new = repo.create_topic(
            session, title=title, kind="school", school_id=school.id,
            rationale=f"{school.name}（{school.province or ''}{school.level or ''}）"
                      f"目录同步 {major_count} 个专业方向",
            score=round(score, 2), ref_item_ids=[item.id])
        if is_new:
            created.append(topic)

    # 公共选题：汇总近期所有目录更新
    all_items = repo.recent_raw_items(session, since_hours=24 * 30, kind="catalog", limit=500)
    if all_items:
        n = len(all_items)
        title = f"本周研招网硕士目录更新速览（{n} 所学校）"
        topic, is_new = repo.create_topic(
            session, title=title, kind="public",
            rationale=f"近期同步 {n} 所学校硕士目录，适合做汇总类干货",
            score=1.0 + min(n, 50) * 0.05,
            ref_item_ids=[i.id for i in all_items[:50]])
        if is_new:
            created.append(topic)

    return created
