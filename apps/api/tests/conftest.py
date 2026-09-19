"""Test fixtures.

Each test gets its own SQLite file, its own evidence directory and a fresh
engine, so tests never share state.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

TEMP_ROOT = Path(tempfile.mkdtemp(prefix="aegis-tests-"))
os.environ.setdefault("AEGIS_DATABASE_URL", f"sqlite:///{TEMP_ROOT}/test.db")
os.environ.setdefault("AEGIS_EVIDENCE_PATH", str(TEMP_ROOT / "evidence"))
os.environ.setdefault("AEGIS_SEED_DEMO", "false")
os.environ.setdefault("AEGIS_SECRET_KEY", "test-secret")

from aegis.db import SessionLocal, init_db  # noqa: E402
from aegis.models import Base, Organization, Program, Project, User  # noqa: E402
from aegis.security import hash_password  # noqa: E402


@pytest.fixture
def db():
    from aegis.db import engine

    Base.metadata.drop_all(bind=engine)
    init_db()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def user(db):
    account = User(
        email="tester@example.test",
        full_name="Test Engineer",
        password_hash=hash_password("test-password"),
    )
    db.add(account)
    db.flush()
    return account


@pytest.fixture
def project(db):
    org = Organization(name="Test Organization", short_name="TEST")
    db.add(org)
    db.flush()
    program = Program(organization_id=org.id, name="Test Program")
    db.add(program)
    db.flush()
    item = Project(program_id=program.id, name="Test Project", slug="test-project")
    db.add(item)
    db.flush()
    return item
