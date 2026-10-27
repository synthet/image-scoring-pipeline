"""Localization enablement boundary: ``localization_enablement`` (#527, epic #345).

Stage 4 of the localization rollout runs the phase automatically only for *new* or
source-changed images; unchanged legacy images need an explicit selection. "New" needs a
persisted point in time: an image indexed at or after ``enabled_at`` for a detector is new.

One row per detector key. The migration does not seed it: ``modules.localization_policy``
writes the row (insert-if-absent) the first time gated code runs with
``localization.enabled`` on, so an upgrade never makes the existing library "new".

Revision ID: 0039
Revises: 0038
Create Date: 2026-10-04
"""

from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS localization_enablement (
            detector_key  TEXT PRIMARY KEY,
            enabled_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS localization_enablement")
