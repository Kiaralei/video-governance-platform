"""quality + flywheel

Revision ID: 0008_quality_flywheel
Revises: 0007_appeals
Create Date: 2026-07-01

Stage 8：黄金题字段 + 数据回流样本表。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_quality_flywheel"
down_revision: Union[str, None] = "0007_appeals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "human_review_tasks",
        sa.Column("is_golden", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "human_review_tasks",
        sa.Column("golden_expected_decision", sa.String(), nullable=True),
    )

    op.create_table(
        "flywheel_samples",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("content_id", sa.String(), nullable=False),
        sa.Column("dimension_id", sa.String(), nullable=False),
        sa.Column("machine_decision", sa.String(), nullable=False),
        sa.Column("human_decision", sa.String(), nullable=False),
        sa.Column("final_decision", sa.String(), nullable=False),
        sa.Column("error_type", sa.String(), nullable=False),
        sa.Column("policy_version", sa.String(), nullable=False),
        sa.Column("rule_version", sa.String(), nullable=False),
        sa.Column("quality_gate_passed", sa.Boolean(), nullable=False),
        sa.Column("is_correction", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index("idx_flywheel_source", "flywheel_samples", ["source_type"])
    op.create_index("idx_flywheel_content", "flywheel_samples", ["content_id"])


def downgrade() -> None:
    op.drop_index("idx_flywheel_content", table_name="flywheel_samples")
    op.drop_index("idx_flywheel_source", table_name="flywheel_samples")
    op.drop_table("flywheel_samples")
    op.drop_column("human_review_tasks", "golden_expected_decision")
    op.drop_column("human_review_tasks", "is_golden")
