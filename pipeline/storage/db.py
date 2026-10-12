"""数据库引擎与会话管理。"""
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ..config import settings
from .models import Base

engine = create_engine(settings.database_url, echo=False, future=True)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db():
    """建表（Phase 1 用 create_all；后续可平滑接入 Alembic 做迁移）。"""
    Base.metadata.create_all(engine)


@contextmanager
def session_scope():
    """组件统一用这个上下文读写 DB，自动 commit/rollback。"""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
