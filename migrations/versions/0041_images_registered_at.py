"""Image registration time: ``images.registered_at`` (#584, epic #345).

The localization new-image boundary (0039) compared ``images.created_at`` with
``localization_enablement.enabled_at``. Indexing stores the camera capture time in
``created_at`` (the gallery sorts by it), so a photo captured before the boundary never
counted as new, however recently it was imported. ``registered_at`` is set once, when the
row is inserted, and is what the boundary now uses.

Existing rows are backfilled from ``created_at`` so their new/legacy classification is
unchanged. The default is set only after the backfill: adding the column with
``DEFAULT CURRENT_TIMESTAMP`` would stamp every existing row with the upgrade time and make
the whole library "new".

Revision ID: 0041
Revises: 0040
Create Date: 2026-10-09
"""

from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE images ADD COLUMN IF NOT EXISTS registered_at TIMESTAMP")
    op.execute("UPDATE images SET registered_at = created_at WHERE registered_at IS NULL")
    op.execute("ALTER TABLE images ALTER COLUMN registered_at SET DEFAULT CURRENT_TIMESTAMP")


def downgrade() -> None:
    op.execute("ALTER TABLE images DROP COLUMN IF EXISTS registered_at")
