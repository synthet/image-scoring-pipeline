"""Widen image_keywords.source for long provenance labels

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-01

repair_legacy_keywords_junction and similar callers exceed VARCHAR(20).
"""

from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "image_keywords",
        "source",
        existing_type=sa.String(20),
        type_=sa.String(128),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "image_keywords",
        "source",
        existing_type=sa.String(128),
        type_=sa.String(20),
        existing_nullable=True,
    )
