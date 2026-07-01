"""decision engine

Revision ID: 0004_decision_engine
Revises: 0003_users
Create Date: 2026-07-01

Stage 4：维度注册表 + 策略版本 + 机审决策摘要列。
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_decision_engine"
down_revision: Union[str, None] = "0003_users"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "machine_reviews", sa.Column("decision_summary_json", sa.Text(), nullable=True)
    )

    op.create_table(
        "dimension_registry",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("dimension_id", sa.String(), nullable=False),
        sa.Column("dimension_name", sa.String(), nullable=False),
        sa.Column("dimension_axis", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("llm_review_enabled", sa.Boolean(), nullable=False),
        sa.Column("auto_block_threshold", sa.Float(), nullable=False),
        sa.Column("human_review_threshold", sa.Float(), nullable=False),
        sa.Column("prompt_template_id", sa.String(), nullable=False),
        sa.Column("severity_tiers", sa.Text(), nullable=False),
        sa.Column("jurisdiction_overrides", sa.Text(), nullable=False),
        sa.Column("sor_template_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("approved_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.UniqueConstraint("dimension_id", name="uq_dimension_registry_dimension_id"),
    )
    op.create_index("idx_dimension_registry_status", "dimension_registry", ["status"])

    op.create_table(
        "policy_versions",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("version_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("activated_at", sa.String(), nullable=True),
        sa.UniqueConstraint("version_id", name="uq_policy_versions_version_id"),
    )
    op.create_index("idx_policy_versions_status", "policy_versions", ["status"])


def downgrade() -> None:
    op.drop_index("idx_policy_versions_status", table_name="policy_versions")
    op.drop_table("policy_versions")
    op.drop_index("idx_dimension_registry_status", table_name="dimension_registry")
    op.drop_table("dimension_registry")
    op.drop_column("machine_reviews", "decision_summary_json")
