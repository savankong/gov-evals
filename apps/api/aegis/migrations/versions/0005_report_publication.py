"""Report publication: which benchmark reports are on the public pages.

The public benchmark pages need no login, so a report reaches them only when
someone publishes it. Both columns are nullable and unset for every existing
report, which keeps everything already generated private.

Columns are added only if absent, for the reason 0002 gives.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0005_report_publication"
down_revision = "0004_benchmark_criteria"
branch_labels = None
depends_on = None

_COLUMNS = (
    ("reports", "published_at", sa.DateTime(timezone=True)),
    ("reports", "published_by", sa.String(255)),
)


def _columns(inspector: sa.Inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table, column, type_ in _COLUMNS:
        if column not in _columns(inspector, table):
            op.add_column(table, sa.Column(column, type_, nullable=True))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table, column, _ in reversed(_COLUMNS):
        if column in _columns(inspector, table):
            op.drop_column(table, column)
