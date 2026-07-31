from __future__ import annotations

"""PostgreSQL engine/session foundation for the (optional) PostgreSQL backend.

This module is only imported when DATABASE_BACKEND=postgres. The default
SQLite-backed behavior in backend/cache_db.py is untouched otherwise.
"""

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from backend.settings import get_env, get_int_env, load_capstone_env

load_capstone_env()

_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def get_database_url() -> str:
    return get_env(
        "DATABASE_URL",
        "postgresql+psycopg://hr_agent:hr_agent_dev_password@localhost:5432/hr_agent",
    )


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


def check_connection() -> bool:
    # Lightweight readiness probe: connect and run SELECT 1.
    with get_engine().connect() as connection:
        connection.execute(text("SELECT 1"))
    return True
