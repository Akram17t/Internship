from __future__ import annotations

import os

# Point the whole test suite at a dedicated PostgreSQL database, never the
# developer's own hr_agent database -- this must run before any backend
# module (which reads DATABASE_URL at first use) gets imported by a test file.
_TEST_DATABASE_URL = "postgresql+psycopg://hr_agent:hr_agent_dev_password@localhost:5432/hr_agent_test"
os.environ.setdefault("DATABASE_URL", _TEST_DATABASE_URL)

import psycopg
import pytest
from sqlalchemy import text

from backend.db.engine import get_database_url, get_engine
from backend.db.models import Base


def _guard_against_non_test_database() -> None:
    # Hard fail-fast: this suite truncates tables in every test, so accidentally
    # pointing it at a real/dev database (e.g. a stray DATABASE_URL already set
    # in the environment before conftest.py runs) must never proceed silently.
    dbname = get_database_url().rsplit("/", 1)[-1].split("?", 1)[0]
    if "test" not in dbname.lower():
        raise RuntimeError(
            f"Refusing to run tests against database {dbname!r} -- its name "
            "does not contain 'test'. This suite truncates tables every test; "
            "point DATABASE_URL at a dedicated test database."
        )


_guard_against_non_test_database()


def _ensure_test_database_exists() -> None:
    # First-run bootstrap so a fresh clone can just run pytest, without a
    # manual "create the test database" step: connect to the maintenance
    # `postgres` database on the same server and create hr_agent_test if it
    # doesn't exist yet. No-op once it already exists.
    url = get_database_url()
    if "psycopg" not in url:
        return
    plain_url = url.split("+psycopg", 1)[0] + url.split("+psycopg", 1)[1]
    conn_info = psycopg.conninfo.conninfo_to_dict(plain_url)
    target_db = conn_info.pop("dbname", "hr_agent_test")
    maintenance_url = psycopg.conninfo.make_conninfo(dbname="postgres", **conn_info)
    with psycopg.connect(maintenance_url, autocommit=True) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", (target_db,))
            if cursor.fetchone() is None:
                cursor.execute(f'CREATE DATABASE "{target_db}"')


_ensure_test_database_exists()


@pytest.fixture(scope="session", autouse=True)
def _prepare_schema():
    # Ephemeral test database: create the current table shape directly rather
    # than replaying Alembic history. Schemas must exist before create_all can
    # place tables in them.
    engine = get_engine()
    with engine.begin() as connection:
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS app"))
        connection.execute(text("CREATE SCHEMA IF NOT EXISTS analytics"))
    Base.metadata.create_all(engine, checkfirst=True)


@pytest.fixture(autouse=True)
def _clean_database():
    # Truncate every app/analytics table before each test so tests never see
    # another test's rows, without paying for a fresh CREATE DATABASE per test.
    engine = get_engine()
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.execute(text(f'TRUNCATE TABLE "{table.schema}"."{table.name}" CASCADE'))
    yield
