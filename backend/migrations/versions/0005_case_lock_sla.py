"""case lock + sla

Revision ID: 0005_case_lock_sla
Revises: 0004_decision_engine
Create Date: 2026-07-01

Stage 5：人审任务加案件锁 + SLA 字段。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_case_lock_sla"
down_revision: Union[str, None] = "0004_decision_engine"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("human_review_tasks", sa.Column("locked_at", sa.String(), nullable=True))
    op.add_column("human_review_tasks", sa.Column("lock_expires_at", sa.String(), nullable=True))
    op.add_column("human_review_tasks", sa.Column("sla_deadline", sa.String(), nullable=True))
    op.add_column(
        "human_review_tasks",
        sa.Column("sla_warned", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("human_review_tasks", "sla_warned")
    op.drop_column("human_review_tasks", "sla_deadline")
    op.drop_column("human_review_tasks", "lock_expires_at")
    op.drop_column("human_review_tasks", "locked_at")
