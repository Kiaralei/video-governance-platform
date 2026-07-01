"""priority queue + anti-fatigue

Revision ID: 0006_review_queue
Revises: 0005_case_lock_sla
Create Date: 2026-07-01

Stage 6：人审任务加优先级、敏感标记、法域字段 + 队列复合索引。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_review_queue"
down_revision: Union[str, None] = "0005_case_lock_sla"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "human_review_tasks",
        sa.Column("priority", sa.Integer(), nullable=False, server_default="5"),
    )
    op.add_column(
        "human_review_tasks",
        sa.Column("is_sensitive", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "human_review_tasks",
        sa.Column("jurisdiction", sa.String(), nullable=False, server_default="global"),
    )
    op.create_index(
        "idx_human_review_tasks_queue",
        "human_review_tasks",
        ["status", "priority", "sla_deadline", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_human_review_tasks_queue", table_name="human_review_tasks")
    op.drop_column("human_review_tasks", "jurisdiction")
    op.drop_column("human_review_tasks", "is_sensitive")
    op.drop_column("human_review_tasks", "priority")
