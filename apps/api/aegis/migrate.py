"""Bringing a database up to the schema this code expects.

Until this module existed the schema was whatever `Base.metadata.create_all`
had managed to produce. `create_all` creates tables that are missing; it never
alters a table that is already there. Every database therefore froze at the
models of the day it was first created, and each later model change was
invisible until a request named the new column and came back 500.

Three states have to be handled, and the third is the one that matters:

  * A database under migration control -- it has `alembic_version`. Upgrade it.
  * An empty database. Upgrade it; every revision runs, starting from nothing.
  * A database with tables but no `alembic_version`. This is every database
    created before this module, including the deployed one. It is stamped at
    the baseline revision -- which is defined as the schema `create_all`
    produced before migrations existed, precisely so that this stamp needs no
    inspection to be correct -- and then upgraded. The revisions after the
    baseline are written to skip anything already present, because `create_all`
    left these databases holding part of the change already.
"""

from __future__ import annotations

import logging

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.engine import Connection, Engine

log = logging.getLogger("aegis.migrate")

BASELINE_REVISION = "0001_baseline"

# The API and the worker start at the same time and both bring the schema up.
# Without a lock they race: two processes run the same ALTER and the loser
# crashes the container. Postgres takes the lock for the duration of the
# transaction; SQLite has a single writer already.
_LOCK_KEY = 6272809831341703169  # stable, arbitrary, "aegis schema"


def _config(connection: Connection) -> Config:
    from pathlib import Path

    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parent / "migrations"))
    config.attributes["connection"] = connection
    return config


def _is_managed(connection: Connection) -> bool:
    return MigrationContext.configure(connection).get_current_revision() is not None


def _has_tables(connection: Connection) -> bool:
    return bool(inspect(connection).get_table_names())


def upgrade_to_head(engine: Engine | None = None) -> str | None:
    """Bring the database to the latest revision. Returns the revision reached."""
    if engine is None:
        from .db import engine as default_engine

        engine = default_engine

    with engine.begin() as connection:
        if connection.dialect.name == "postgresql":
            connection.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": _LOCK_KEY})

        config = _config(connection)

        if not _is_managed(connection):
            if _has_tables(connection):
                log.info(
                    "Database has tables but no migration history. Stamping it at %s -- the "
                    "schema that shipped before migrations existed -- and upgrading from there.",
                    BASELINE_REVISION,
                )
                command.stamp(config, BASELINE_REVISION)
            else:
                log.info("Empty database. Creating the schema from the full revision history.")

        before = MigrationContext.configure(connection).get_current_revision()
        command.upgrade(config, "head")
        after = MigrationContext.configure(connection).get_current_revision()

    if before == after:
        log.info("Schema is current at revision %s.", after)
    else:
        log.info("Schema upgraded from %s to %s.", before, after)
    return after


def current_revision(engine: Engine | None = None) -> str | None:
    """The revision the database is stamped at, or None if it is unmanaged."""
    if engine is None:
        from .db import engine as default_engine

        engine = default_engine
    with engine.connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()
