"""创作 Agent 运行器：选题 → 文案 → 卡片 → 草稿入库（status=pending_review）。"""
import os

from ..config import settings
from ..storage import Major, repo, session_scope
from . import copywriter, selector
from .card_renderer import render_draft


def _subtitle(topic, school):
    if school:
        return " ".join(x for x in [school.province or "", school.level or ""] if x).strip()
    return "考研资讯"


def _points_from(content, majors):
    pts = []
    for ln in content["body"].split("\n"):
        s = ln.strip()
        if s.startswith("·"):
            pts.append(s.lstrip("· ").strip())
    if not pts and majors:
        pts = [f"{m.degree_type} {m.name}（{m.code}）" for m in majors[:8]]
    if not pts:
        pts = [ln.strip() for ln in content["body"].split("\n") if ln.strip()][:6]
    seen, out = set(), []
    for p in pts:
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return out[:8]


def run(limit=3):
    with session_scope() as session:
        new_topics = selector.run(session)
        topics = repo.pending_topics(session, limit=limit)
        draft_ids = []
        for t in topics:
            repo.select_topic(session, t.id)
            school = t.school
            majors = []
            if school:
                majors = (session.query(Major).filter_by(school_id=school.id)
                          .limit(12).all())
            raw_items = (repo.recent_raw_items(session, school_id=school.id, limit=3)
                         if school else [])
            content = copywriter.write(t, school=school, majors=majors, raw_items=raw_items)
            points = _points_from(content, majors)
            out_dir = os.path.join(settings.output_dir, "cards", f"topic{t.id}")
            assets = render_draft(out_dir, content["title"], _subtitle(t, school), points)
            draft = repo.create_draft(
                session, topic_id=t.id, title=content["title"], body=content["body"],
                tags=content["tags"], assets=assets, platform="xiaohongshu",
                form="image_text", generator=content["generator"])
            draft_ids.append(draft.id)
        return {"new_topics": len(new_topics), "draft_ids": draft_ids}
