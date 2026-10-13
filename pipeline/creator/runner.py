"""创作 Agent 运行器：选题 → 文案 → 卡片 → 草稿入库（status=pending_review）。"""
import os

from ..config import settings
from ..storage import Major, Theme, Topic, repo, session_scope
from . import copywriter, selector
from .card_renderer import render_draft, accent_for
import re


def _fsafe(s):
    """文件名安全化：保留中文/字母/数字，剔除文件系统危险字符。"""
    return re.sub(r'[\\/:*?"<>|\r\n\t]', "", str(s)).strip().strip(".") or "topic"


def _label(s, n=24):
    """话题标签：只留中文/字母/数字（去掉 emoji/标点/空格），截断到 n 字。"""
    t = re.sub(r"[^\u4e00-\u9fff0-9A-Za-z]", "", str(s))
    return t[:n] or "topic"


def theme_number(session, theme):
    """主题编号 01..N：按 active 主题 id 顺序（= 定义顺序）稳定编号。"""
    if theme is None:
        return "00"
    for i, th in enumerate(repo.active_themes(session), start=1):
        if th.id == theme.id:
            return f"{i:02d}"
    return "00"


def topic_card_dir(session, topic):
    """主题根目录：编号_主题名（如 01_院校专业解读），跨期累积。"""
    theme = topic.theme
    name = (theme.name if theme else (topic.title or "topic"))
    no = theme_number(session, theme)
    return os.path.join(settings.output_dir, "cards", f"{no}_{_fsafe(name)}")


def topic_run_dir(session, topic, title=""):
    """某一期的卡片目录：主题根目录 / YYYYMMDD_本期话题。"""
    stamp = topic_stamp(topic)
    label = _label(title or (topic.title or "topic"))
    return os.path.join(topic_card_dir(session, topic), f"{stamp}_{label}")


def topic_stamp(topic):
    """日期戳 YYYYMMDD：优先用 topic.period，否则今天。"""
    period = getattr(topic, "period", None) or ""
    m = re.search(r"(\d{4})[-/]?(\d{1,2})[-/]?(\d{1,2})", str(period))
    if m:
        return f"{m.group(1)}{int(m.group(2)):02d}{int(m.group(3)):02d}"
    try:
        from datetime import datetime
        return datetime.utcnow().strftime("%Y%m%d")
    except Exception:
        return "00000000"


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
    # 规范化 Agent 提供的分页：去掉 callout 里重复的「提示/重点：」前缀
    for pg in pages:
        if pg.get("callout"):
            pg["callout"] = _clean_callout(pg["callout"].strip())
    closing = content.get("closing") or _default_closing(topic, school)
    body = content.get("body") or pages_to_body(title, pages, closing)
    footer = f"{school.name} · 考研干货" if school else "考研信息 · 干货分享"
    kicker = f"{school.name} · 2026 硕士招生速览" if school else "2026 考研 · 硕士招生速览"
    out_dir = topic_run_dir(session, topic, title)
    # 同一篇统一主题色（按 topic 确定性分配），保证单篇视觉一致
    accent = accent_for(topic.id)
    assets = render_draft(out_dir, title, subtitle, pages, closing=closing, footer=footer,
                          tags=content.get("tags"), kicker=kicker,
                          highlights=content.get("highlights"), accent=accent)
    draft = repo.create_draft(
        session, topic_id=topic.id, title=title, body=body,
        tags=content.get("tags", []), assets=assets, platform="xiaohongshu",
        form="image_text", generator=content.get("generator", "workbuddy"),
        pages=pages)
    repo.select_topic(session, topic.id)
    # 创作后自动复核：依据原始数据源（专业目录 + 全网素材）校验内容，报告写入同一目录
    from . import verifier
    review = verifier.verify_and_write(
        session, topic,
        {"title": title, "subtitle": subtitle, "pages": pages,
         "closing": closing, "tags": content.get("tags")},
        out_dir)
    # 发布物料：一键复制的发布文档(含语音口播稿，供人工确认)。
    # 配音不在此自动生成——确认口播稿后由 `cli narrate` 按需单独生成(消耗 MiniMax 额度)。
    try:
        from . import narrator, publisher
        narration = narrator.build_narration(
            {"title": title, "pages": pages, "closing": closing})
        publisher.render_publish_doc(
            {"title": title, "body": body, "tags": content.get("tags")},
            out_dir, assets=assets, narration=narration)
    except Exception as exc:  # 文档生成失败不影响主流程
        print(f"[finalize_draft] 发布物料生成失败(已跳过): {exc}")
    draft.reviewed_at = datetime_now()
    return draft


def datetime_now():
    from datetime import datetime
    return datetime.utcnow()


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


def topics_brief(session, limit=30, period=None, theme_id=None):
    """产出候选选题的结构化简报(JSON 友好)，供创作 Agent(或人)据此写文案。

    每个选题附带：
    - 所属主题、受众、按主题标签检索到的近期原始素材(全网抓取结果)；
    - school_anchor：永远锚定大连海事大学的可核实具体事实（专业代码/考试科目），
      公共主题也带，便于把宏观政策落到本校考生身上；
    - writing_guide：围绕学校具体信息、不得编造的取材规范；
    - verified_facts / unverified_note：标明哪些可写、哪些严禁编造。
    """
    from . import prompts, style_guide
    selector.run(session, period=period)
    topics = repo.pending_topics(session, limit=limit, theme_id=theme_id)
    anchor = prompts.anchor_school(session)
    brief = []
    for t in topics:
        school = t.school
        theme = t.theme
        # 锚定学校的具体专业事实（学校定向用自身，公共主题用大连海事大学做例子锚点）
        anchor_school = school or anchor
        majors = (session.query(Major).filter_by(school_id=anchor_school.id).limit(20).all()
                  if anchor_school else [])
        # 原始数据源：① 本主题标签下的全网素材；② 锚定学校的全网素材
        raw = []
        if theme:
            raw += repo.all_raw_items(session, theme_key=theme.key, scope="general", limit=5)
        if anchor_school:
            raw += repo.all_raw_items(session, scope=anchor_school.name, limit=5)
        # 去重
        seen, raw_dedup = set(), []
        for it in raw:
            k = it.title
            if k in seen:
                continue
            seen.add(k)
            raw_dedup.append(it)
        brief.append({
            "topic_id": t.id,
            "kind": t.kind,
            "period": t.period,
            "topic_title": t.title,
            "theme": ({"key": theme.key, "name": theme.name,
                       "audience": theme.audience, "description": theme.description}
                      if theme else None),
            "rationale": t.rationale,
            "school": ({"name": school.name, "province": school.province,
                        "level": school.level} if school else None),
            "school_anchor": ({"name": anchor_school.name,
                               "province": anchor_school.province,
                               "level": anchor_school.level}
                              if anchor_school else None),
            "majors": [{"code": m.code, "name": m.name, "degree_type": m.degree_type,
                        "direction": m.direction, "exam_subjects": m.exam_subjects}
                       for m in majors],
            "ref_items": [{"title": it.title, "content": (it.content or "")[:1500],
                           "url": it.url, "scope": it.scope}
                          for it in raw_dedup],
            "writing_guide": prompts.writing_guide(theme.name if theme else "", t.kind),
            "style_guide": style_guide.style_guide_json(),
            "verified_facts": prompts.verified_facts_block(session, anchor_school),
            "unverified_note": prompts.unverified_note(),
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
