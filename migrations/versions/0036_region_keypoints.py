"""Region-linked subject keypoints: image_keypoint_runs + image_region_keypoints.

Stage 2 schema addendum of the early-localization rollout (#426, epic #345). Keypoints
(eyes, beak, head top, shoulders) are an artifact *of a region*, versioned like the
detector regions they hang off:

* ``image_keypoint_runs`` -- one row per keypoint attempt on one region, written even when
  the provider finds no subject in the crop, so ``no_keypoints`` is a versioned observation
  and not an absence. At most one current attempt per (region, provider).
* ``image_region_keypoints`` -- the points of a ``detected`` attempt. Coordinates are in the
  parent run's display-normalized space (0..1 of the display-oriented frame), so any
  consumer draws them with the same mapping as the region box. ``visible`` is the provider's
  gate (confidence >= its threshold); invisible points are still stored for calibration.

Both cascade from ``image_regions``, so a new localization attempt (which creates new
regions) never leaves keypoints pointing at a stale box.

Revision ID: 0036
Revises: 0035
Create Date: 2026-09-26
"""

from alembic import op

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS image_keypoint_runs (
            id                    BIGSERIAL PRIMARY KEY,
            region_id             BIGINT NOT NULL REFERENCES image_regions(id) ON DELETE CASCADE,
            provider_key          TEXT NOT NULL,
            provider_version      TEXT NOT NULL,
            provider_config_hash  TEXT NOT NULL,
            pass                  TEXT NOT NULL,
            status                TEXT NOT NULL,
            error_code            TEXT,
            error_detail          TEXT,
            is_current            BOOLEAN NOT NULL DEFAULT FALSE,
            created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_ikr_status CHECK (status IN (
                'detected', 'no_keypoints', 'retryable_error', 'terminal_error'
            ))
        )
        """
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_ikr_current_region_provider "
        "ON image_keypoint_runs (region_id, provider_key) WHERE is_current"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS image_region_keypoints (
            id               BIGSERIAL PRIMARY KEY,
            keypoint_run_id  BIGINT NOT NULL REFERENCES image_keypoint_runs(id) ON DELETE CASCADE,
            name             TEXT NOT NULL,
            x                DOUBLE PRECISION NOT NULL,
            y                DOUBLE PRECISION NOT NULL,
            confidence       DOUBLE PRECISION,
            visible          BOOLEAN NOT NULL,
            CONSTRAINT ck_irk_range CHECK (x >= 0 AND x <= 1 AND y >= 0 AND y <= 1),
            CONSTRAINT ck_irk_confidence CHECK (
                confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
            ),
            CONSTRAINT ux_irk_run_name UNIQUE (keypoint_run_id, name)
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS image_region_keypoints")
    op.execute("DROP TABLE IF EXISTS image_keypoint_runs")
