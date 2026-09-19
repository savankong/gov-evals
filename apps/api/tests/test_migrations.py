"""The schema the migrations build must be the schema the models describe.

This file exists because of a production outage. `Base.metadata.create_all`
creates missing tables and does nothing at all to tables that already exist, so
seven columns added to `datasets`, `scenarios` and `human_reviews` were never
applied to the deployed database. The tables were all there, every test passed
against a database created from scratch, and in production every endpoint that
selected one of those rows returned 500 with `UndefinedColumn`.

Tests build their database with `create_all` because it is fast. Services build
theirs with migrations. The first test here is what keeps those two from
drifting: add a column to a model without writing the revision that applies it
and it fails, naming the column.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy import create_engine, select

from aegis.migrate import BASELINE_REVISION, current_revision, upgrade_to_head
from aegis.models import Base, Dataset, Organization, Program, Project

# Revision bookkeeping is not part of the application's schema.
_IGNORED_TABLES = {"alembic_version"}


def _schema(engine) -> dict:
    """Everything about the schema that a query can fail on."""
    inspector = sa.inspect(engine)
    out: dict = {}
    for table in sorted(set(inspector.get_table_names()) - _IGNORED_TABLES):
        out[table] = {
            "columns": {
                column["name"]: (str(column["type"]), bool(column["nullable"]))
                for column in inspector.get_columns(table)
            },
            "primary_key": tuple(inspector.get_pk_constraint(table)["constrained_columns"]),
            "indexes": sorted(
                (index["name"] or "", tuple(index["column_names"]), bool(index["unique"]))
                for index in inspector.get_indexes(table)
            ),
            # Constraint names are assigned by the backend when nothing names
            # them, so they say nothing about whether the schema is right.
            "foreign_keys": sorted(
                (
                    tuple(fk["constrained_columns"]),
                    fk["referred_table"],
                    tuple(fk["referred_columns"]),
                )
                for fk in inspector.get_foreign_keys(table)
            ),
        }
    return out


def _engine(tmp_path, name: str):
    return create_engine(f"sqlite:///{tmp_path / name}", future=True)


def _describe(built: dict, expected: dict) -> str:
    lines: list[str] = []
    for table in sorted(set(expected) - set(built)):
        lines.append(f"  table {table!r} is missing from the migrations")
    for table in sorted(set(built) - set(expected)):
        lines.append(f"  table {table!r} exists only in the migrations")
    for table in sorted(set(built) & set(expected)):
        a, b = built[table], expected[table]
        for column in sorted(set(b["columns"]) - set(a["columns"])):
            lines.append(f"  {table}.{column} is in the models but no migration adds it")
        for column in sorted(set(a["columns"]) - set(b["columns"])):
            lines.append(f"  {table}.{column} is in the migrations but not in the models")
        for column in sorted(set(a["columns"]) & set(b["columns"])):
            if a["columns"][column] != b["columns"][column]:
                lines.append(
                    f"  {table}.{column} differs: migrations {a['columns'][column]}, "
                    f"models {b['columns'][column]}"
                )
        for key in ("primary_key", "indexes", "foreign_keys"):
            if a[key] != b[key]:
                lines.append(f"  {table} {key} differs: migrations {a[key]}, models {b[key]}")
    return "\n".join(lines) or "  (schemas differ in a way this report does not cover)"


def test_migrations_build_the_schema_the_models_describe(tmp_path):
    migrated = _engine(tmp_path, "migrated.db")
    upgrade_to_head(migrated)

    from_models = _engine(tmp_path, "models.db")
    Base.metadata.create_all(bind=from_models)

    built, expected = _schema(migrated), _schema(from_models)
    assert built == expected, (
        "The migrations no longer build what the models describe:\n"
        + _describe(built, expected)
        + "\n\nA model change needs a revision in aegis/migrations/versions/. Without one "
        "it reaches a new database (create_all builds those) and never reaches a deployed "
        "one, which is how /datasets started returning 500."
    )


def test_empty_database_is_built_entirely_by_migrations(tmp_path):
    engine = _engine(tmp_path, "empty.db")
    assert current_revision(engine) is None

    upgrade_to_head(engine)

    assert current_revision(engine) == "0002_expert_review"
    assert "datasets" in sa.inspect(engine).get_table_names()


def test_upgrading_twice_changes_nothing(tmp_path):
    engine = _engine(tmp_path, "twice.db")
    upgrade_to_head(engine)
    once = _schema(engine)

    upgrade_to_head(engine)

    assert _schema(engine) == once


def _make_unmanaged(engine) -> None:
    """A database as it stood in production before this package existed.

    Built the way production got there rather than by deleting columns: the
    baseline schema, plus the one table `create_all` was able to add on the
    next deploy, and no revision history. The seven columns `create_all` could
    not add are absent, which is the state `/datasets` was failing from.

    The baseline revision is used to lay this down because the baseline is
    defined as the schema that shipped before migrations existed -- that is
    what makes it the revision an unmanaged database can be stamped at.
    """
    from alembic import command

    from aegis.migrate import _config

    with engine.begin() as connection:
        command.upgrade(_config(connection), BASELINE_REVISION)

    # The deploy that introduced the expert-review models ran create_all, which
    # created this table and silently skipped every new column.
    Base.metadata.tables["expert_profiles"].create(bind=engine)

    # ...and it had no revision history, because there were no revisions.
    with engine.begin() as connection:
        connection.execute(sa.text("DROP TABLE alembic_version"))


def _insert_dataset(engine, project_id: str, name: str) -> None:
    """Insert a dataset row without going through the model.

    The model carries the column this test is about, so it cannot be used to
    write a row into a table that does not have it yet. Every other NOT NULL
    column is filled from what the reflected table says it needs, so a column
    added to `datasets` later does not turn this into a puzzle.
    """
    table = sa.Table("datasets", sa.MetaData(), autoload_with=engine)
    values: dict = {"id": "d1", "project_id": project_id, "name": name}
    for column in table.columns:
        if column.name in values or column.nullable or column.server_default is not None:
            continue
        values[column.name] = _placeholder(column.type)
    with engine.begin() as connection:
        connection.execute(table.insert().values(**values))


def _placeholder(type_):
    if isinstance(type_, sa.JSON):
        return []
    if isinstance(type_, sa.Boolean):
        return False
    if isinstance(type_, (sa.Integer, sa.Float)):
        return 0
    if isinstance(type_, sa.DateTime):
        import datetime

        return datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)
    return "x"


def test_a_database_from_before_migrations_is_adopted_and_repaired(tmp_path):
    engine = _engine(tmp_path, "unmanaged.db")
    _make_unmanaged(engine)
    assert current_revision(engine) is None
    assert "required_expertise" not in {
        column["name"] for column in sa.inspect(engine).get_columns("datasets")
    }

    upgrade_to_head(engine)

    assert current_revision(engine) == "0002_expert_review"
    assert _schema(engine)["datasets"]["columns"]["required_expertise"] == ("JSON", False)


def test_adoption_keeps_the_rows_that_are_already_there(tmp_path):
    engine = _engine(tmp_path, "rows.db")
    _make_unmanaged(engine)

    session = sa.orm.Session(engine)
    organization = Organization(name="Defence Digital", short_name="DD")
    session.add(organization)
    session.flush()
    program = Program(organization_id=organization.id, name="Contract Review")
    session.add(program)
    session.flush()
    project = Project(program_id=program.id, name="Clause Triage", slug="clause-triage")
    session.add(project)
    session.commit()
    project_id = project.id
    session.close()

    _insert_dataset(engine, project_id, "Indemnity clauses")

    upgrade_to_head(engine)

    session = sa.orm.Session(engine)
    dataset = session.execute(select(Dataset)).scalar_one()
    assert dataset.name == "Indemnity clauses"
    # The column was added to a table that already had rows in it. Every one of
    # them has to come out the other side satisfying NOT NULL.
    assert dataset.required_expertise == []
    session.close()


def test_a_database_already_holding_the_change_is_adopted_without_reapplying_it(tmp_path):
    """A development database built by `create_all` from today's models.

    Adoption stamps it at the baseline, so every revision after the baseline
    runs against a database that already contains the change.
    """
    engine = _engine(tmp_path, "current.db")
    Base.metadata.create_all(bind=engine)
    before = _schema(engine)
    assert current_revision(engine) is None

    upgrade_to_head(engine)

    assert current_revision(engine) == "0002_expert_review"
    assert _schema(engine) == before


def test_baseline_is_the_revision_an_unmanaged_database_is_stamped_at(tmp_path):
    engine = _engine(tmp_path, "stamp.db")
    _make_unmanaged(engine)

    from alembic.runtime.migration import MigrationContext

    from aegis.migrate import _config

    with engine.begin() as connection:
        from alembic import command

        command.stamp(_config(connection), BASELINE_REVISION)
        assert MigrationContext.configure(connection).get_current_revision() == BASELINE_REVISION
