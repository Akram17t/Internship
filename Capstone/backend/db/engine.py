from __future__ import annotations

"""PostgreSQL engine/session foundation -- the application's sole database backend."""

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.settings import get_int_env, get_required_env, load_capstone_env

load_capstone_env()

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def get_database_url() -> str:
    return get_required_env("DATABASE_URL")


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            get_database_url(),
            pool_size=get_int_env("DATABASE_POOL_SIZE", 5),
            max_overflow=get_int_env("DATABASE_MAX_OVERFLOW", 5),
            pool_pre_ping=True,
            future=True,
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(
            bind=get_engine(), autoflush=False, expire_on_commit=False
        )
    return _SessionFactory


def get_session() -> Session:
    return get_session_factory()()
