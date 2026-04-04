"""Add images.updated_at; unique (image_id, path) on file_paths for upserts.

Revision ID: 0005
Revises: 0004
Create Date: 2026-04-04

Fixes Postgres errors:
- get_image_details: column i.updated_at does not exist
- register_image_path: ON CONFLICT (image_id, path) requires a matching unique index
"""

from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "images",
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE images SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP) "
            "WHERE updated_at IS NULL"
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM file_paths AS fp1
            USING file_paths AS fp2
            WHERE fp1.id > fp2.id
              AND fp1.image_id IS NOT DISTINCT FROM fp2.image_id
              AND fp1.path IS NOT DISTINCT FROM fp2.path
            """
        )
    )
    op.create_index(
        "uq_file_paths_image_id_path",
        "file_paths",
        ["image_id", "path"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_file_paths_image_id_path", table_name="file_paths")
    op.drop_column("images", "updated_at")
