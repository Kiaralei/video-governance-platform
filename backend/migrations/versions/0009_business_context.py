"""add business context to content items

Revision ID: 0009_business_context
Revises: 0008_quality_flywheel
Create Date: 2026-07-02
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_business_context"
down_revision: Union[str, None] = "0008_quality_flywheel"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "content_items",
        sa.Column("business_context_json", sa.Text(), nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    op.drop_column("content_items", "business_context_json")
