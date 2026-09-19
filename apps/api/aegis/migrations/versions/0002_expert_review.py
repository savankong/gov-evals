"""Expert review: reviewer qualification, and the expertise a case requires.

This is the change that `create_all` could not apply, and the reason this
package exists. `create_all` created the one new table -- `expert_profiles` --
and silently skipped all seven new columns on tables that already existed, so a
deployed database ended up half-way through this change: the queries that
counted rows kept working, and every query that named one of the new columns
returned 500.

Each object is therefore added only if it is absent. That is not defensive
padding: a database being adopted into migrations is stamped at 0001, and the
databases that most need this revision are exactly the ones already holding
part of it.

The three NOT NULL columns are added with a server-side default so that rows
already in the table satisfy the constraint, and the default is dropped again
once they do -- the models define these defaults in Python, and leaving a
second definition in the database is how the two drift apart.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0002_expert_review"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None

FK_EXPERT_PROFILE = "fk_human_reviews_expert_profile_id"

# Added to satisfy existing rows, then dropped. See the module docstring.
_EMPTY_LIST = sa.text("'[]'")

# (table, column, type, nullable, server_default-while-adding)
_COLUMNS = (
    ("datasets", "required_expertise", sa.JSON(), False, _EMPTY_LIST),
    ("scenarios", "required_expertise", sa.JSON(), False, _EMPTY_LIST),
    ("human_reviews", "expert_profile_id", sa.String(length=36), True, None),
    ("human_reviews", "expertise", sa.String(length=128), True, None),
    ("human_reviews", "familiarity", sa.Float(), True, None),
    ("human_reviews", "qualified", sa.Boolean(), False, sa.false()),
    ("human_reviews", "qualification_note", sa.Text(), True, None),
)


def _columns(inspector: sa.Inspector, table: str) -> set[str]:
    return {column["name"] for column in inspector.get_columns(table)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "expert_profiles" not in inspector.get_table_names():
        op.create_table(
            "expert_profiles",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("user_id", sa.String(length=36), nullable=True),
            sa.Column("display_name", sa.String(length=255), nullable=False),
            sa.Column("disciplines", sa.JSON(), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=True),
            sa.Column("organization", sa.String(length=255), nullable=True),
            sa.Column("credentials", sa.Text(), nullable=True),
            sa.Column("years_experience", sa.Integer(), nullable=True),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("verified", sa.Boolean(), nullable=False),
            sa.Column("verified_by", sa.String(length=255), nullable=True),
            sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("active", sa.Boolean(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_expert_profiles_user_id"), "expert_profiles", ["user_id"], unique=False
        )
        inspector = sa.inspect(bind)

    added_defaults: list[tuple[str, str]] = []
    for table, column, type_, nullable, default in _COLUMNS:
        if column in _columns(inspector, table):
            continue
        op.add_column(
            table,
            sa.Column(column, type_, nullable=nullable, server_default=default),
        )
        if default is not None:
            added_defaults.append((table, column))

    # Rows now all carry a value, so the database no longer needs to supply one.
    for table, column in added_defaults:
        with op.batch_alter_table(table) as batch:
            batch.alter_column(column, server_default=None)

    existing_fks = {fk["name"] for fk in sa.inspect(bind).get_foreign_keys("human_reviews")}
    referenced = {
        tuple(fk["constrained_columns"])
        for fk in sa.inspect(bind).get_foreign_keys("human_reviews")
    }
    if FK_EXPERT_PROFILE not in existing_fks and ("expert_profile_id",) not in referenced:
        with op.batch_alter_table("human_reviews") as batch:
            batch.create_foreign_key(
                FK_EXPERT_PROFILE,
                "expert_profiles",
                ["expert_profile_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if FK_EXPERT_PROFILE in {fk["name"] for fk in inspector.get_foreign_keys("human_reviews")}:
        with op.batch_alter_table("human_reviews") as batch:
            batch.drop_constraint(FK_EXPERT_PROFILE, type_="foreignkey")

    for table, column, *_ in reversed(_COLUMNS):
        if column in _columns(inspector, table):
            op.drop_column(table, column)

    if "expert_profiles" in inspector.get_table_names():
        op.drop_index(op.f("ix_expert_profiles_user_id"), table_name="expert_profiles")
        op.drop_table("expert_profiles")
