"""appeals

Revision ID: 0007_appeals
Revises: 0006_review_queue
Create Date: 2026-07-01

Stage 7：申诉案件表。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_appeals"
down_revision: Union[str, None] = "0006_review_queue"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "appeal_cases",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("content_id", sa.String(), sa.ForeignKey("content_items.id"), nullable=False),
        sa.Column("appellant_id", sa.String(), nullable=False),
        sa.Column("appeal_reason", sa.Text(), nullable=False),
        sa.Column("original_decision", sa.String(), nullable=False),
        sa.Column("original_reviewer_id", sa.String(), nullable=True),
        sa.Column("original_task_id", sa.String(), nullable=True),
        sa.Column("pre_disposition_snapshot", sa.Text(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("assigned_reviewer_id", sa.String(), nullable=True),
        sa.Column("resolved_decision", sa.String(), nullable=True),
        sa.Column("resolution_reason", sa.Text(), nullable=True),
        sa.Column("sla_deadline", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("resolved_at", sa.String(), nullable=True),
    )
    op.create_index("idx_appeal_cases_status", "appeal_cases", ["status"])


def downgrade() -> None:
    op.drop_index("idx_appeal_cases_status", table_name="appeal_cases")
    op.drop_table("appeal_cases")
