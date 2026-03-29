"""Add keywords_dim and image_keywords tables

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-29

Adds the normalized keyword tables that were present in db_postgres.init_db()
but missing from the Alembic migration chain.  Required for dual-write
activation (Phase 2) since keyword sync writes to these tables.
"""

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # KEYWORDS_DIM — normalized keyword dictionary
    # ------------------------------------------------------------------
    op.create_table(
        "keywords_dim",
        sa.Column("keyword_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("keyword_norm", sa.String(200), nullable=False),
        sa.Column("keyword_display", sa.String(200), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("keyword_id"),
    )
    op.create_index("uq_keywords_dim_norm", "keywords_dim", ["keyword_norm"], unique=True)

    # ------------------------------------------------------------------
    # IMAGE_KEYWORDS — many-to-many junction (image <-> keyword)
    # ------------------------------------------------------------------
    op.create_table(
        "image_keywords",
        sa.Column("image_id", sa.Integer(), nullable=False),
        sa.Column("keyword_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(20), server_default="auto", nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["keyword_id"], ["keywords_dim.keyword_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("image_id", "keyword_id"),
    )
    op.create_index("idx_imgkw_image_id", "image_keywords", ["image_id"])
    op.create_index("idx_imgkw_keyword_id", "image_keywords", ["keyword_id"])


def downgrade() -> None:
    op.drop_table("image_keywords")
    op.drop_table("keywords_dim")
