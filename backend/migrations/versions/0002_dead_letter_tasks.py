"""dead_letter_tasks

Revision ID: 0002_dead_letter_tasks
Revises: 0001_initial
Create Date: 2026-07-01

新增死信任务表，配合 Celery 流水线：任务重试耗尽 / 线程路径终态失败时落库。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002_dead_letter_tasks"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "dead_letter_tasks",
        sa.Column("id", _PK, primary_key=True, autoincrement=True),
        sa.Column("task_name", sa.String(), nullable=False),
        sa.Column("celery_task_id", sa.String(), nullable=True),
        sa.Column("job_id", sa.String(), nullable=True),
        sa.Column("content_id", sa.String(), nullable=True),
        sa.Column("exception_type", sa.String(), nullable=False),
        sa.Column("exception_message", sa.Text(), nullable=False),
        sa.Column("traceback", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index("idx_dead_letter_tasks_status", "dead_letter_tasks", ["status"])


def downgrade() -> None:
    op.drop_table("dead_letter_tasks")
