"""Capture and delivery: expert reasoning traces, data packages, knowledge areas.

The platform's purpose moved from "evaluate a government program's AI" to
"find what a frontier model is weak at in government work, capture expert
reasoning there, and deliver it". Three schema objects carry that:

  * `scenarios.knowledge_area` -- what body of knowledge a problem tests, so
    weakness can be found in one and delivery binned by it.
  * `reasoning_traces` -- an expert working a problem, step by step.
  * `data_packages` -- a stored, hashed delivery to a customer.

As in 0002, each object is created only if absent. A development database
built by `create_all` from today's models is adopted by stamping it at the
baseline, and then already holds everything below.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0003_capture_and_delivery"
down_revision = "0002_expert_review"
branch_labels = None
depends_on = None


def _tables(bind) -> set[str]:
    return set(sa.inspect(bind).get_table_names())


def _columns(bind, table: str) -> set[str]:
    return {column["name"] for column in sa.inspect(bind).get_columns(table)}


def _indexes(bind, table: str) -> set[str]:
    return {index["name"] for index in sa.inspect(bind).get_indexes(table)}


def upgrade() -> None:
    bind = op.get_bind()

    if "knowledge_area" not in _columns(bind, "scenarios"):
        op.add_column(
            "scenarios", sa.Column("knowledge_area", sa.String(length=255), nullable=True)
        )
    if op.f("ix_scenarios_knowledge_area") not in _indexes(bind, "scenarios"):
        op.create_index(
            op.f("ix_scenarios_knowledge_area"), "scenarios", ["knowledge_area"], unique=False
        )

    if "reasoning_traces" not in _tables(bind):
        op.create_table(
            "reasoning_traces",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("scenario_id", sa.String(length=36), nullable=True),
            sa.Column("result_id", sa.String(length=36), nullable=True),
            sa.Column("author_id", sa.String(length=36), nullable=True),
            sa.Column("author_label", sa.String(length=255), nullable=True),
            sa.Column("knowledge_area", sa.String(length=255), nullable=True),
            sa.Column("problem", sa.JSON(), nullable=False),
            sa.Column("steps", sa.JSON(), nullable=False),
            sa.Column("final_answer", sa.Text(), nullable=False),
            sa.Column("sources", sa.JSON(), nullable=False),
            sa.Column("time_spent_seconds", sa.Integer(), nullable=True),
            sa.Column("confidence", sa.Float(), nullable=True),
            sa.Column("contains_pii", sa.Boolean(), nullable=False),
            sa.Column("expert_profile_id", sa.String(length=36), nullable=True),
            sa.Column("expertise", sa.String(length=128), nullable=True),
            sa.Column("qualified", sa.Boolean(), nullable=False),
            sa.Column("qualification_note", sa.Text(), nullable=True),
            sa.Column("content_hash", sa.String(length=64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("classification", sa.String(length=64), nullable=False),
            sa.Column("owner", sa.String(length=255), nullable=True),
            sa.Column("provenance", sa.JSON(), nullable=False),
            sa.Column("retention_policy", sa.String(length=255), nullable=True),
            sa.ForeignKeyConstraint(["scenario_id"], ["scenarios.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["result_id"], ["results.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(
                ["expert_profile_id"], ["expert_profiles.id"], ondelete="SET NULL"
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        for column in ("scenario_id", "result_id", "knowledge_area", "content_hash"):
            op.create_index(
                op.f(f"ix_reasoning_traces_{column}"), "reasoning_traces", [column], unique=False
            )

    if "data_packages" not in _tables(bind):
        op.create_table(
            "data_packages",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("customer", sa.String(length=255), nullable=True),
            sa.Column("selection", sa.JSON(), nullable=False),
            sa.Column("record_count", sa.Integer(), nullable=False),
            sa.Column("manifest", sa.JSON(), nullable=False),
            sa.Column("media_type", sa.String(length=128), nullable=False),
            sa.Column("storage_uri", sa.String(length=1024), nullable=True),
            sa.Column("sha256", sa.String(length=64), nullable=False),
            sa.Column("size_bytes", sa.Integer(), nullable=False),
            sa.Column("classification", sa.String(length=64), nullable=False),
            sa.Column("created_by", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            op.f("ix_data_packages_sha256"), "data_packages", ["sha256"], unique=False
        )


def downgrade() -> None:
    bind = op.get_bind()

    if "data_packages" in _tables(bind):
        op.drop_index(op.f("ix_data_packages_sha256"), table_name="data_packages")
        op.drop_table("data_packages")

    if "reasoning_traces" in _tables(bind):
        for column in ("scenario_id", "result_id", "knowledge_area", "content_hash"):
            op.drop_index(op.f(f"ix_reasoning_traces_{column}"), table_name="reasoning_traces")
        op.drop_table("reasoning_traces")

    if op.f("ix_scenarios_knowledge_area") in _indexes(bind, "scenarios"):
        op.drop_index(op.f("ix_scenarios_knowledge_area"), table_name="scenarios")
    if "knowledge_area" in _columns(bind, "scenarios"):
        with op.batch_alter_table("scenarios") as batch:
            batch.drop_column("knowledge_area")
