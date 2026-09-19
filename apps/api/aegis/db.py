"""Database session plumbing.

SQLite is the zero-dependency default; any SQLAlchemy URL (Postgres in
production) works without code changes.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

_settings = get_settings()

_connect_args = {"check_same_thread": False} if _settings.is_sqlite else {}

engine = create_engine(
    _settings.database_url,
    connect_args=_connect_args,
    pool_pre_ping=not _settings.is_sqlite,
    future=True,
)

if _settings.is_sqlite:

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - driver hook
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Standalone session for workers and scripts."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Create any missing tables directly from the models.

    This is the fast path for tests and throwaway databases, not the path a
    running service takes. `create_all` creates tables that are absent and
    does nothing whatsoever to tables that are present -- it will not add a
    column, widen a type or drop a constraint. A long-lived database brought
    up this way silently stops at the models of the day it was created.

    Services call `aegis.migrate.upgrade_to_head` instead. The two are held to
    the same result by tests/test_migrations.py, which fails if a model change
    lands without the revision that applies it.
    """
    from . import models  # noqa: F401  (register mappers)
    from .models import Base

    Base.metadata.create_all(bind=engine)
