"""enforce one machine review per content item

并发处理路径（线程 worker / Celery chain / 演示注入后台线程）曾因
check-then-insert 竞态对同一 content 写入多条机审记录。先清掉历史
重复（保留每个 content 最新一条），再加唯一约束从数据库层兜底。

Revision ID: 0010_machine_review_unique
Revises: 0009_business_context
Create Date: 2026-07-02
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0010_machine_review_unique"
down_revision: Union[str, None] = "0009_business_context"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DELETE FROM machine_reviews
        WHERE EXISTS (
            SELECT 1 FROM machine_reviews newer
            WHERE newer.content_id = machine_reviews.content_id
              AND (newer.created_at > machine_reviews.created_at
                   OR (newer.created_at = machine_reviews.created_at
                       AND newer.id > machine_reviews.id))
        )
        """
    )
    # batch 模式兼容 SQLite（copy-and-move）；PostgreSQL 下等价于普通 ALTER。
    with op.batch_alter_table("machine_reviews") as batch:
        batch.create_unique_constraint("uq_machine_reviews_content_id", ["content_id"])


def downgrade() -> None:
    with op.batch_alter_table("machine_reviews") as batch:
        batch.drop_constraint("uq_machine_reviews_content_id", type_="unique")
