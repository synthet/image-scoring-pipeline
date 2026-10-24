"""Add af_metadata JSONB column to image_exif table.

Stores parsed autofocus metadata (AFInfo2 tag 0x00B7, CropArea tag 0x0045,
focus coordinates, dimensions, mode, and in-focus lock state) from MakerNotes.

Revision ID: 0044
Revises: 0043
Create Date: 2026-10-24
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("image_exif", sa.Column("af_metadata", JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("image_exif", "af_metadata")
