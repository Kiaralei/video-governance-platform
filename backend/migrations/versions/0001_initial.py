"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-01

初始迁移，与 app/models.py 一致。后续结构变更用
`alembic revision --autogenerate -m "..."` 生成新版本，不要改这个文件。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# audit_logs 主键需服务端自增：PG 用 BIGINT，SQLite 用 INTEGER(rowid)。
_AUDIT_PK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "content_items",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), nullable=False),
        sa.Column("jurisdiction", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("creator_id", sa.String(), nullable=False),
        sa.Column("poi", sa.String(), nullable=True),
        sa.Column("video_url", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("final_decision", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
    )

    op.create_table(
        "pipeline_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("content_id", sa.String(), sa.ForeignKey("content_items.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("started_at", sa.String(), nullable=True),
        sa.Column("finished_at", sa.String(), nullable=True),
    )
    op.create_index("idx_pipeline_jobs_status_created", "pipeline_jobs", ["status", "created_at"])

    op.create_table(
        "media_assets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("content_id", sa.String(), sa.ForeignKey("content_items.id"), nullable=False),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column("source_type", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("storage_backend", sa.String(), nullable=False),
        sa.Column("storage_uri", sa.String(), nullable=True),
        sa.Column("local_path", sa.String(), nullable=True),
        sa.Column("sha256", sa.String(), nullable=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("mime_type", sa.String(), nullable=True),
        sa.Column("extension", sa.String(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("asset_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index("idx_media_assets_content", "media_assets", ["content_id"])
    op.create_index("idx_media_assets_sha256", "media_assets", ["sha256"])

    op.create_table(
        "evidence_packages",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("content_id", sa.String(), sa.ForeignKey("content_items.id"), nullable=False),
        sa.Column("package_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
    )

    op.create_table(
        "machine_reviews",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("content_id", sa.String(), sa.ForeignKey("content_items.id"), nullable=False),
        sa.Column("recommendation", sa.String(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("verdicts_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index("idx_machine_reviews_content", "machine_reviews", ["content_id"])

    op.create_table(
        "human_review_tasks",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("content_id", sa.String(), sa.ForeignKey("content_items.id"), nullable=False),
        sa.Column(
            "evidence_package_id",
            sa.String(),
            sa.ForeignKey("evidence_packages.id"),
            nullable=False,
        ),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("assigned_to", sa.String(), nullable=True),
        sa.Column("decision", sa.String(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("decided_at", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
    )
    op.create_index(
        "idx_human_review_tasks_status_created", "human_review_tasks", ["status", "created_at"]
    )

    op.create_table(
        "audit_logs",
        sa.Column("id", _AUDIT_PK, primary_key=True, autoincrement=True),
        sa.Column("content_id", sa.String(), nullable=True),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("actor", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("detail_json", sa.Text(), nullable=False),
        sa.Column("prev_hash", sa.String(), nullable=False),
        sa.Column("entry_hash", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
    )
    op.create_index("idx_audit_logs_content_id", "audit_logs", ["content_id"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("human_review_tasks")
    op.drop_table("machine_reviews")
    op.drop_table("evidence_packages")
    op.drop_table("media_assets")
    op.drop_table("pipeline_jobs")
    op.drop_table("content_items")
