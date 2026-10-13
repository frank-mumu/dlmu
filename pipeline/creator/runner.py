"""创作 Agent 运行器：选题 → 文案 → 卡片 → 草稿入库（status=pending_review）。"""
import os

from ..config import settings
from ..storage import Major, Topic, repo, session_scope
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


def finalize_draft(session, topic, content):
    """把一段文案落成草稿并渲染卡片。content: {title, body, tags, generator}。"""
    school = topic.school
    majors = (session.query(Major).filter_by(school_id=school.id).limit(12).all()
              if school else [])
    points = _points_from(content, majors)
    out_dir = os.path.join(settings.output_dir, "cards", f"topic{topic.id}")
    assets = render_draft(out_dir, content["title"], _subtitle(topic, school), points)
    draft = repo.create_draft(
        session, topic_id=topic.id, title=content["title"], body=content["body"],
        tags=content["tags"], assets=assets, platform="xiaohongshu",
        form="image_text", generator=content.get("generator", "workbuddy"))
    repo.select_topic(session, topic.id)
    return draft


def run(limit=3, period=None):
    """LLM API 模式：选题 → 调 copywriter(外部 LLM) → 草稿。保留备用。"""
    with session_scope() as session:
        new_topics = selector.run(session, period=period)
        topics = repo.pending_topics(session, limit=limit)
        draft_ids = []
        for t in topics:
            school = t.school
            majors = (session.query(Major).filter_by(school_id=school.id).limit(12).all()
                      if school else [])
            raw_items = (repo.recent_raw_items(session, school_id=school.id, limit=3)
                         if school else [])
            content = copywriter.write(t, school=school, majors=majors, raw_items=raw_items)
            draft = finalize_draft(session, t, content)
            draft_ids.append(draft.id)
        return {"new_topics": len(new_topics), "draft_ids": draft_ids}


def topics_brief(session, limit=5, period=None):
    """产出候选选题的结构化简报(JSON 友好)，供创作 Agent(或人)据此写文案。"""
    selector.run(session, period=period)
    topics = repo.pending_topics(session, limit=limit)
    brief = []
    for t in topics:
        school = t.school
        majors = (session.query(Major).filter_by(school_id=school.id).limit(20).all()
                  if school else [])
        items = (repo.recent_raw_items(session, school_id=school.id, limit=3)
                 if school else [])
        brief.append({
            "topic_id": t.id, "kind": t.kind, "topic_title": t.title,
            "rationale": t.rationale,
            "school": ({"name": school.name, "province": school.province,
                        "level": school.level} if school else None),
            "majors": [{"code": m.code, "name": m.name, "degree_type": m.degree_type,
                        "direction": m.direction, "exam_subjects": m.exam_subjects}
                       for m in majors],
            "ref_items": [{"title": it.title, "content": it.content} for it in items],
        })
    return brief


def run_agent(drafts):
    """Agent 模式：接收 Agent 写好的文案(list[{topic_id,title,body,tags}])，落草稿+渲染卡片。"""
    with session_scope() as session:
        created = []
        for item in drafts:
            topic = session.get(Topic, item.get("topic_id"))
            if topic is None:
                created.append({"topic_id": item.get("topic_id"), "error": "topic 不存在"})
                continue
            content = {"title": item["title"], "body": item["body"],
                       "tags": item.get("tags", []), "generator": "workbuddy"}
            draft = finalize_draft(session, topic, content)
            created.append({"draft_id": draft.id, "title": draft.title,
                            "cards": draft.assets})
        return created
