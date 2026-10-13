"""仓库层：组件通过这里读写契约表，隐藏 ORM 细节。"""
from datetime import datetime, timedelta

from .models import Draft, Major, RawItem, School, Source, Theme, Topic


# ---------- 主题 ----------
def seed_themes(session, themes):
    """一次性写入/更新主题（按 key 去重）。themes: [{key,name,description,audience,scope,search_templates}]。"""
    for t in themes:
        existing = session.query(Theme).filter_by(key=t["key"]).one_or_none()
        if existing is None:
            existing = Theme(
                key=t["key"], name=t["name"], description=t.get("description"),
                audience=t.get("audience", "通用"), scope=t.get("scope", "both"),
                search_templates=t.get("search_templates", []), active=t.get("active", True))
            session.add(existing)
        else:
            existing.name = t.get("name", existing.name)
            existing.description = t.get("description", existing.description)
            existing.audience = t.get("audience", existing.audience)
            existing.scope = t.get("scope", existing.scope)
            existing.search_templates = t.get("search_templates", existing.search_templates or [])
            existing.active = t.get("active", True)
    session.flush()


def active_themes(session):
    return session.query(Theme).filter_by(active=True).order_by(Theme.id).all()


def get_theme(session, key):
    return session.query(Theme).filter_by(key=key).one_or_none()


def set_theme_active(session, key, active):
    t = get_theme(session, key)
    if t:
        t.active = active
        session.flush()
    return t


# ---------- 数据源 ----------
def get_or_create_source(session, name, type_, url=None, config=None):
    src = session.query(Source).filter_by(name=name).one_or_none()
    if src is None:
        src = Source(name=name, type=type_, url=url, config=config or {})
        session.add(src)
        session.flush()
    return src


# ---------- 学校 / 专业 ----------
def upsert_school(session, name, code=None, province=None, level=None, in_pool=None, site_url=None):
    school = session.query(School).filter_by(name=name).one_or_none()
    if school is None:
        school = School(name=name)
        session.add(school)
    if code and not school.code:
        school.code = code
    if province and not school.province:
        school.province = province
    if level and not school.level:
        school.level = level
    if site_url and not school.site_url:
        school.site_url = site_url
    if in_pool is not None:
        school.in_pool = in_pool
    session.flush()
    return school


def add_major(session, school, code, name, degree_type, direction=None, exam_subjects=None):
    exists = session.query(Major).filter_by(
        school_id=school.id, code=code, name=name,
        degree_type=degree_type, direction=direction).first()
    if exists:
        return None
    major = Major(school_id=school.id, code=code, name=name,
                  degree_type=degree_type, direction=direction, exam_subjects=exam_subjects)
    session.add(major)
    session.flush()
    return major


def school_by_name(session, name):
    return session.query(School).filter_by(name=name).one_or_none()


def pool_schools(session):
    return session.query(School).filter_by(in_pool=True).order_by(School.id).all()


# ---------- 原始内容 ----------
def add_raw_item(session, title, kind="catalog", content=None, url=None,
                 source_id=None, school_id=None, published_at=None, meta=None,
                 theme_key=None, scope=None):
    """按 url_hash 去重；返回 (item, created)。theme_key/scope 用于按主题检索。"""
    import hashlib
    key = url or f"{source_id}:{title}"
    url_hash = hashlib.sha1(key.encode("utf-8")).hexdigest()
    item = session.query(RawItem).filter_by(url_hash=url_hash).one_or_none()
    if item is not None:
        # 已有则补充主题标签（若原本为空）
        if theme_key and not item.theme_key:
            item.theme_key = theme_key
            item.scope = scope or item.scope
            session.flush()
        return item, False
    item = RawItem(title=title, kind=kind, content=content, url=url, url_hash=url_hash,
                   source_id=source_id, school_id=school_id,
                   published_at=published_at, meta=meta or {},
                   theme_key=theme_key, scope=scope)
    session.add(item)
    session.flush()
    return item, True


def recent_raw_items(session, since_hours=24*30, kind=None, school_id=None,
                     theme_key=None, scope=None, limit=200):
    q = session.query(RawItem).filter(
        RawItem.fetched_at >= datetime.utcnow() - timedelta(hours=since_hours))
    if kind:
        q = q.filter(RawItem.kind == kind)
    if school_id is not None:
        q = q.filter(RawItem.school_id == school_id)
    if theme_key:
        q = q.filter(RawItem.theme_key == theme_key)
    if scope:
        q = q.filter(RawItem.scope == scope)
    return q.order_by(RawItem.fetched_at.desc()).limit(limit).all()


def all_raw_items(session, kind=None, school_id=None, theme_key=None,
                  scope=None, limit=200):
    """不受时间窗限制的原始数据源查询（复核时按主题/学校取全部已采集素材）。"""
    q = session.query(RawItem)
    if kind:
        q = q.filter(RawItem.kind == kind)
    if school_id is not None:
        q = q.filter(RawItem.school_id == school_id)
    if theme_key:
        q = q.filter(RawItem.theme_key == theme_key)
    if scope:
        q = q.filter(RawItem.scope == scope)
    return q.order_by(RawItem.fetched_at.desc()).limit(limit).all()


# ---------- 选题 ----------
def create_topic(session, title, kind, school_id=None, rationale=None,
                 score=0.0, ref_item_ids=None, theme_id=None, period=None):
    """按 (theme_id, period, school_id) 去重：同一主题+日期+学校只产一个 topic。"""
    q = session.query(Topic).filter(Topic.status.in_(["pending", "selected"]))
    if theme_id is not None:
        q = q.filter(Topic.theme_id == theme_id, Topic.period == period)
        if school_id is not None:
            q = q.filter(Topic.school_id == school_id)
        else:
            q = q.filter(Topic.school_id.is_(None))
    else:
        q = q.filter(Topic.title == title)
    exists = q.first()
    if exists is not None:
        return exists, False
    topic = Topic(title=title, kind=kind, school_id=school_id, rationale=rationale,
                  score=score, status="pending", ref_item_ids=ref_item_ids or [],
                  theme_id=theme_id, period=period)
    session.add(topic)
    session.flush()
    return topic, True


def pending_topics(session, limit=20, theme_id=None):
    q = session.query(Topic).filter_by(status="pending")
    if theme_id is not None:
        q = q.filter(Topic.theme_id == theme_id)
    return q.order_by(Topic.score.desc()).limit(limit).all()


def select_topic(session, topic_id):
    topic = session.get(Topic, topic_id)
    if topic:
        topic.status = "selected"
        session.flush()
    return topic


# ---------- 草稿 ----------
def create_draft(session, topic_id, title, body, tags=None, assets=None,
                 platform="xiaohongshu", form="image_text", generator="template", pages=None):
    draft = Draft(topic_id=topic_id, platform=platform, form=form, title=title,
                  body=body, tags=tags or [], assets=assets or [], generator=generator,
                  pages=pages or [], status="pending_review")
    session.add(draft)
    session.flush()
    return draft


def list_drafts(session, status=None, limit=50):
    q = session.query(Draft)
    if status:
        q = q.filter(Draft.status == status)
    return q.order_by(Draft.created_at.desc()).limit(limit).all()


def latest_draft(session, topic_id):
    return (session.query(Draft).filter_by(topic_id=topic_id)
            .order_by(Draft.created_at.desc()).first())
