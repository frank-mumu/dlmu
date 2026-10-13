"""数据契约：共享数据库表结构（见 ARCHITECTURE.md）。

所有组件只通过这些表交换数据，互不 import 彼此业务代码。
"""
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def utcnow():
    return datetime.utcnow()


class Source(Base):
    __tablename__ = "sources"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), unique=True, nullable=False)
    type = Column(String(32), nullable=False)          # yz_catalog / school_site / rss
    url = Column(Text, nullable=True)
    enabled = Column(Boolean, default=True)
    config = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utcnow)


class School(Base):
    __tablename__ = "schools"
    id = Column(Integer, primary_key=True)
    name = Column(String(128), unique=True, nullable=False)
    code = Column(String(32), nullable=True)
    province = Column(String(64), nullable=True)
    level = Column(String(64), nullable=True)          # 985/211/双一流
    in_pool = Column(Boolean, default=False)           # 是否目标学校池
    site_url = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)


class Major(Base):
    __tablename__ = "majors"
    id = Column(Integer, primary_key=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=False)
    code = Column(String(32))
    name = Column(String(256))
    degree_type = Column(String(32))                   # 学硕 / 专硕
    direction = Column(String(256), nullable=True)
    exam_subjects = Column(Text, nullable=True)
    __table_args__ = (UniqueConstraint(
        "school_id", "code", "name", "degree_type", "direction", name="uq_major"),)
    school = relationship("School")


class RawItem(Base):
    __tablename__ = "raw_items"
    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=True)
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=True)
    kind = Column(String(32), default="catalog")       # catalog / notice / news
    title = Column(String(512))
    content = Column(Text, nullable=True)
    url = Column(Text, nullable=True)
    url_hash = Column(String(64), unique=True, nullable=True)   # 去重键
    published_at = Column(DateTime, nullable=True)
    fetched_at = Column(DateTime, default=utcnow)
    meta = Column(JSON, default=dict)


class Topic(Base):
    __tablename__ = "topics"
    id = Column(Integer, primary_key=True)
    title = Column(String(512))
    kind = Column(String(16))                          # public / school
    school_id = Column(Integer, ForeignKey("schools.id"), nullable=True)
    rationale = Column(Text, nullable=True)
    score = Column(Float, default=0.0)
    status = Column(String(16), default="pending")     # pending / selected / rejected
    ref_item_ids = Column(JSON, default=list)
    created_at = Column(DateTime, default=utcnow)
    school = relationship("School")


class Draft(Base):
    __tablename__ = "drafts"
    id = Column(Integer, primary_key=True)
    topic_id = Column(Integer, ForeignKey("topics.id"), nullable=True)
    platform = Column(String(32), default="xiaohongshu")
    form = Column(String(16), default="image_text")    # image_text / video
    title = Column(String(512))
    body = Column(Text)
    tags = Column(JSON, default=list)
    assets = Column(JSON, default=list)                # 卡片图片路径
    pages = Column(JSON, default=list)                 # 分页结构 [{heading, points[]}]
    generator = Column(String(16), default="template") # llm / template
    status = Column(String(16), default="pending_review")  # pending_review/approved/rejected/published
    created_at = Column(DateTime, default=utcnow)
    reviewed_at = Column(DateTime, nullable=True)
    topic = relationship("Topic")


class PublishJob(Base):
    __tablename__ = "publish_jobs"
    id = Column(Integer, primary_key=True)
    draft_id = Column(Integer, ForeignKey("drafts.id"), nullable=False)
    platform = Column(String(32))
    status = Column(String(16), default="queued")      # queued/publishing/published/failed
    scheduled_at = Column(DateTime, nullable=True)
    published_at = Column(DateTime, nullable=True)
    result = Column(JSON, default=dict)
    created_at = Column(DateTime, default=utcnow)


class Metric(Base):
    __tablename__ = "metrics"
    id = Column(Integer, primary_key=True)
    platform = Column(String(32))
    content_ref = Column(String(256))
    draft_id = Column(Integer, ForeignKey("drafts.id"), nullable=True)
    views = Column(Integer, default=0)
    likes = Column(Integer, default=0)
    comments = Column(Integer, default=0)
    collects = Column(Integer, default=0)
    captured_at = Column(DateTime, default=utcnow)
