"""Scene route classifications: image_scene_labels (spec 05 AC-5, #412).

One row per image and classifier version. ``scene_version`` names the prompt set, the backend
and a hash of every prompt, so a prompt or model change produces new rows instead of
overwriting old ones (AC-9). ``top_label`` is the resolved class; ``probs`` and ``cosines`` keep
every label's score so later calibrated per-label thresholds need no re-inference.
``rendition_hash`` ties the result to the localization rendition the classifier saw.

Revision ID: 0037
Revises: 0036
Create Date: 2026-10-01
"""

from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS image_scene_labels (
            image_id        INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
            scene_version   TEXT NOT NULL,
            backend         TEXT NOT NULL,
            top_label       TEXT NOT NULL,
            top_prob        DOUBLE PRECISION NOT NULL,
            probs           JSONB NOT NULL,
            cosines         JSONB,
            rendition_hash  TEXT,
            job_id          INTEGER,
            created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (image_id, scene_version),
            CONSTRAINT ck_isl_top_prob CHECK (top_prob >= 0 AND top_prob <= 1)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_isl_version_label "
        "ON image_scene_labels (scene_version, top_label)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS image_scene_labels")
