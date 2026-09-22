"""Normalized localization persistence: ``image_localization_runs`` + ``image_regions``.

Stage 2 of the early-localization rollout (issue #370, epic #345). Additive and dormant:
nothing writes these tables yet, ``images.bird_bbox`` stays the sole authority, and no
read path changes until ``localization.read_normalized_first`` is enabled.

Why two tables rather than a richer JSONB column:

``images.bird_bbox`` overloads one unversioned value with four meanings (never scanned /
no bird / scan failed / one box) and carries no provenance, so nothing can decide whether
a stored box is still current. Splitting attempt from result fixes both halves:

* ``image_localization_runs`` is one row per *attempt*, written even when zero regions are
  found. That is what makes ``no_detection`` a positive, versioned observation rather than
  an absence. An empty ``image_regions`` set has no standalone meaning -- "not attempted"
  and "attempted, found nothing" are distinguished by the run row, never by region count.
* ``image_regions`` holds the geometry, so the detector's existing ``max_det`` cap can be
  retained instead of discarding every box but the best one.

Attempt history is immutable; ``is_current`` is the only mutable publication flag, and a
partial unique index enforces at most one current attempt per (image, detector). Retry
scheduling deliberately lives elsewhere -- this migration stores facts, not queue state.

Coordinates are normalized 0..1 in a *display-oriented* space, with the orientation and
the pixel dimensions they were computed against recorded on the run. Legacy imports carry
``legacy_unversioned`` provenance precisely because that orientation cannot be recovered
after the fact, and must not be guessed from the current ``images`` row.

Revision ID: 0034
Revises: 0033
Create Date: 2026-09-22
"""

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS image_localization_runs (
            id                      BIGSERIAL PRIMARY KEY,
            image_id                INTEGER NOT NULL
                                    REFERENCES images(id) ON DELETE CASCADE,
            job_id                  INTEGER,

            -- provenance: what produced this attempt
            detector_key            TEXT NOT NULL,
            detector_version        TEXT NOT NULL,
            detector_config_hash    TEXT NOT NULL,

            -- provenance: what it was run against
            source_hash             TEXT,
            source_hash_version     TEXT,
            rendition_hash          TEXT,
            rendition_version       TEXT,

            -- the display-oriented space region coordinates are normalized against
            coord_space             TEXT NOT NULL DEFAULT 'display_normalized',
            orientation             SMALLINT,
            display_width           INTEGER,
            display_height          INTEGER,

            status                  TEXT NOT NULL,
            is_retryable            BOOLEAN NOT NULL DEFAULT FALSE,
            error_code              TEXT,
            error_detail            TEXT,

            -- publication: history is immutable, exactly one attempt may be current
            is_current              BOOLEAN NOT NULL DEFAULT FALSE,

            -- legacy import only: the original images.bird_bbox payload, verbatim
            legacy_payload          JSONB,

            attempted_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            started_at              TIMESTAMP,
            completed_at            TIMESTAMP,
            created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT ck_ilr_status CHECK (status IN (
                'detected', 'no_detection', 'retryable_error', 'terminal_error', 'disabled'
            )),
            CONSTRAINT ck_ilr_orientation CHECK (
                orientation IS NULL OR orientation BETWEEN 1 AND 8
            ),
            CONSTRAINT ck_ilr_dimensions CHECK (
                (display_width IS NULL OR display_width > 0)
                AND (display_height IS NULL OR display_height > 0)
            )
        )
        """
    )

    # Current-artifact lookup by image and detector -- the hot read path for the
    # compatibility reader. Partial, so it also enforces "at most one current attempt".
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_ilr_current_image_detector
        ON image_localization_runs (image_id, detector_key)
        WHERE is_current
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_ilr_image_attempted
        ON image_localization_runs (image_id, attempted_at DESC)
        """
    )
    # Backlog / repair queries scan by outcome, e.g. "every retryable error for this
    # detector version".
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_ilr_status_detector
        ON image_localization_runs (status, detector_key, detector_version)
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS image_regions (
            id                  BIGSERIAL PRIMARY KEY,
            localization_run_id BIGINT NOT NULL
                                REFERENCES image_localization_runs(id) ON DELETE CASCADE,

            object_class        TEXT NOT NULL,
            provider_class_id   TEXT,

            confidence          DOUBLE PRECISION,
            rank                INTEGER NOT NULL,

            -- normalized against the run's display-oriented space
            x1                  DOUBLE PRECISION NOT NULL,
            y1                  DOUBLE PRECISION NOT NULL,
            x2                  DOUBLE PRECISION NOT NULL,
            y2                  DOUBLE PRECISION NOT NULL,

            geometry_hash       TEXT,

            created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT ck_ir_range CHECK (
                x1 >= 0 AND y1 >= 0 AND x2 <= 1 AND y2 <= 1
            ),
            CONSTRAINT ck_ir_ordered CHECK (x2 > x1 AND y2 > y1),
            CONSTRAINT ck_ir_confidence CHECK (
                confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
            ),
            CONSTRAINT ck_ir_rank CHECK (rank >= 0),
            CONSTRAINT ux_ir_run_class_rank UNIQUE (localization_run_id, object_class, rank)
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_ir_run_rank
        ON image_regions (localization_run_id, rank)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_ir_class_confidence
        ON image_regions (object_class, confidence DESC)
        """
    )


def downgrade() -> None:
    # image_regions first: it references image_localization_runs.
    op.execute("DROP TABLE IF EXISTS image_regions")
    op.execute("DROP TABLE IF EXISTS image_localization_runs")
