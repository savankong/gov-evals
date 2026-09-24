"""Benchmark criteria: rubric criteria on scenarios, expert labels on reviews.

A benchmark scores each answer against several criteria, each judged on its
own, and publishes how often the model judge agrees with qualified experts on
those same criteria. The first needs somewhere to keep the criteria; the second
needs somewhere to keep an expert's verdict on each one.

Columns are added only if absent, for the reason 0002 gives: a database being
adopted into migrations may already hold part of a change. The NOT NULL column
is added with a server default for existing rows and the default is dropped
once they satisfy it, so the model stays the only place the default is defined.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_benchmark_criteria"
down_revision = "0002_expert_review"
branch_labels = None
depends_on = None

_EMPTY_LIST = sa.text("'[]'")

# (table, column, type, nullable, server_default-while-adding)
_COLUMNS = (
    ("scenarios", "criteria", sa.JSON(), False, _EMPTY_LIST),
    ("human_reviews", "criteria_labels", sa.JSON(), True, None),
)


def _columns(inspector: sa.Inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table, column, type_, nullable, default in _COLUMNS:
        if column in _columns(inspector, table):
            continue
        op.add_column(
            table,
            sa.Column(column, type_, nullable=nullable, server_default=default),
        )
        if default is not None:
            with op.batch_alter_table(table) as batch:
                batch.alter_column(column, server_default=None)


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table, column, *_ in reversed(_COLUMNS):
        if column in _columns(inspector, table):
            op.drop_column(table, column)
