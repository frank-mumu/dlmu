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


_BULLET_CHARS = "·-•"


def _is_bullet(line):
    s = line.strip()
    if not s:
        return False
    return s[0] in _BULLET_CHARS or s[0].isdigit() or s[0] in "⚠📌✅🔍💡⚖💻🚦🧭🚢⚙📱🔥📢👉👍"


_CALLOUT_PREFIX = ("⚠", "💡", "📌", "重点", "提示", "注意", "避坑", "收藏")


def _clean_callout(s):
    c = s
    for pre in ("重点提示", "温馨提示", "避坑提醒", "避坑", "注意", "提示", "重点"):
        if c.startswith(pre):
            c = c[len(pre):].lstrip("：: 　")
            break
    return c.lstrip("⚠💡📌 ").strip() or s


def body_to_pages(body, majors=None, min_pages=3, max_pages=6):
    """把一段正文启发式拆成 3-6 个内容页(每页 heading/lead/points/callout)，LLM 模式/兜底用。"""
    lines = [ln.rstrip() for ln in (body or "").split("\n")]
    pages, cur = [], {"heading": "", "lead": "", "points": [], "callout": ""}

    def flush():
        nonlocal cur
        if cur["points"] or cur["heading"] or cur["lead"]:
            pg = {"heading": cur["heading"] or "重点速览", "points": cur["points"]}
            if cur["lead"]:
                pg["lead"] = cur["lead"]
            if cur["callout"]:
                pg["callout"] = cur["callout"]
            pages.append(pg)
        cur = {"heading": "", "lead": "", "points": [], "callout": ""}

    for ln in lines:
        s = ln.strip()
        if not s:
            continue
        if any(s.startswith(x) for x in _CALLOUT_PREFIX):
            cur["callout"] = _clean_callout(s)
            continue
        if _is_bullet(s):
            if len(cur["points"]) >= 3:
                flush()
            cur["points"].append(s.lstrip("·-• ").strip())
        elif len(s) <= 24 and not cur["heading"] and not cur["lead"] and not cur["points"]:
            cur["heading"] = s
        elif len(s) <= 70 and not cur["lead"] and not cur["points"]:
            cur["lead"] = s
        else:
            if len(cur["points"]) >= 3:
                flush()
            cur["points"].append(s)
    flush()

    if len(pages) > max_pages:
        head = pages[:max_pages - 1]
        tail = [p for pg in pages[max_pages - 1:] for p in pg["points"]]
        head.append({"heading": "更多要点", "points": tail[:6]})
        pages = head
    if len(pages) < min_pages and majors:
        for m in majors:
            if len(pages) >= min_pages:
                break
            pages.append({"heading": f"{m.degree_type}·{m.name}",
                          "points": [f"专业代码 {m.code}",
                                     f"方向：{m.direction or '-'}",
                                     f"科目：{m.exam_subjects or '-'}"]})
    return pages[:max_pages]


def pages_to_body(title, pages, closing=""):
    parts = [title]
    for pg in pages:
        if pg.get("heading"):
            parts.append(pg["heading"])
        parts += ["· " + p for p in pg.get("points", [])]
    if closing:
        parts.append(closing)
    return "\n".join(parts)


def _default_closing(topic, school):
    if school:
        return f"以上就是{school.name}的考研速览～一切以官网最新招生简章为准，有问题评论区聊！"
    return "以研招网/官网最新信息为准，收藏备用，评论区聊聊你的目标院校～"


def finalize_draft(session, topic, content):
    """把文案落成草稿并渲染分页卡片。

    content: {title, subtitle?, closing?, pages?, body, tags, generator}
    pages: [{"heading", "points":[...]}]，缺省时由 body 自动拆分(3-6 内容页)。
    """
    school = topic.school
    majors = (session.query(Major).filter_by(school_id=school.id).limit(20).all()
              if school else [])
    title = content["title"]
    subtitle = content.get("subtitle") or _subtitle(topic, school)
    pages = content.get("pages") or body_to_pages(content.get("body", ""), majors)
    closing = content.get("closing") or _default_closing(topic, school)
    body = content.get("body") or pages_to_body(title, pages, closing)
    footer = f"{school.name} · 考研干货" if school else "考研信息 · 干货分享"
    kicker = f"{school.name} · 2026 硕士招生速览" if school else "2026 考研 · 硕士招生速览"
    out_dir = os.path.join(settings.output_dir, "cards", f"topic{topic.id}")
    assets = render_draft(out_dir, title, subtitle, pages, closing=closing, footer=footer,
                          tags=content.get("tags"), kicker=kicker,
                          highlights=content.get("highlights"))
    draft = repo.create_draft(
        session, topic_id=topic.id, title=title, body=body,
        tags=content.get("tags", []), assets=assets, platform="xiaohongshu",
        form="image_text", generator=content.get("generator", "workbuddy"),
        pages=pages)
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
    """Agent 模式：接收 Agent 写好的分页文案，落草稿+渲染 5-8 页卡片。

    drafts: [{topic_id, title, subtitle?, tags, body, closing?, pages?:[{heading,points[]}]}]
    """
    with session_scope() as session:
        created = []
        for item in drafts:
            topic = session.get(Topic, item.get("topic_id"))
            if topic is None:
                created.append({"topic_id": item.get("topic_id"), "error": "topic 不存在"})
                continue
            content = {"title": item["title"], "body": item.get("body", ""),
                       "tags": item.get("tags", []), "generator": "workbuddy",
                       "subtitle": item.get("subtitle"), "closing": item.get("closing"),
                       "highlights": item.get("highlights"),
                       "pages": item.get("pages")}
            draft = finalize_draft(session, topic, content)
            created.append({"draft_id": draft.id, "title": draft.title,
                            "cards": draft.assets})
        return created
