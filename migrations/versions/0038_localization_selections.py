"""Production localization selections: ``image_localization_selections`` (#484, epic #345).

A selection is the *decision* that one stored region is the production answer for an image
and detector. It records who decided (rule version and hash) and on what evidence, and is
revoked rather than deleted. Before this table, the only way to publish a box was to
overwrite ``images.bird_bbox``, which hid the decision inside an unversioned JSON value and
left the published geometry outside the normalized ``image_localization_runs`` /
``image_regions`` tables.

``images.bird_bbox`` stays the legacy read path. For a selected image it becomes a
*projection* of the active selection: ``projected_bird_bbox`` is the exact value written
there, and ``previous_bird_bbox`` the value it replaced, so revocation restores it exactly
and can refuse when ``bird_bbox`` was changed outside the selection.

At most one active (not revoked) selection per (image, detector), enforced by a partial
unique index. Selection history is immutable apart from revocation.

Revision ID: 0038
Revises: 0037
Create Date: 2026-10-02
"""

from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS image_localization_selections (
            id                    BIGSERIAL PRIMARY KEY,
            image_id              INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
            detector_key          TEXT NOT NULL,
            localization_run_id   BIGINT NOT NULL
                                  REFERENCES image_localization_runs(id) ON DELETE CASCADE,
            region_id             BIGINT NOT NULL REFERENCES image_regions(id) ON DELETE CASCADE,
            selected_by           TEXT NOT NULL,
            evidence              JSONB,
            previous_bird_bbox    JSONB,
            projected_bird_bbox   JSONB NOT NULL,
            selected_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            revoked_at            TIMESTAMP,
            revoked_reason        TEXT
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_ils_active_image_detector
        ON image_localization_selections (image_id, detector_key)
        WHERE revoked_at IS NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_ils_selected_by "
        "ON image_localization_selections (selected_by, selected_at)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS image_localization_selections")
