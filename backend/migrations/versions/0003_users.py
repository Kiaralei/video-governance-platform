"""users

Revision ID: 0003_users
Revises: 0002_dead_letter_tasks
Create Date: 2026-07-01

新增用户表，支撑 JWT 认证与 RBAC。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_users"
down_revision: Union[str, None] = "0002_dead_letter_tasks"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("password_hash", sa.String(), nullable=False),
        sa.Column("roles_json", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        # 内联唯一约束：SQLite 不支持 ALTER 加约束，必须建表时声明。
        sa.UniqueConstraint("username", name="uq_users_username"),
    )


def downgrade() -> None:
    op.drop_table("users")
