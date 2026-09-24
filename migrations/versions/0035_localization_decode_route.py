"""image_localization_runs.decode_route — which decode produced the detector's pixels.

Stage 4 of the early-localization rollout (#387, epic #345), AC-20. A RAW file has several
valid decodings (full-size ``JpgFromRaw``, a reduced ``PreviewImage``, a ``rawpy``
postprocess), and ``rendition_hash`` folds the route in but cannot be reversed to name it.
Recording the route next to ``display_width``/``display_height`` is what lets a run on a
full-size embedded JPEG be told apart from one on a small preview.

Nullable: stage 2 legacy imports never knew their route, and a run that failed before
decoding (missing file, detector disabled) has none.

Revision ID: 0035
Revises: 0034
Create Date: 2026-09-23
"""

from alembic import op

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE image_localization_runs
        ADD COLUMN IF NOT EXISTS decode_route TEXT
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE image_localization_runs DROP COLUMN IF EXISTS decode_route")
