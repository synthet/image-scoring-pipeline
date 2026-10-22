"""Add the selection-aware bird bbox compatibility view for SQL consumers.

Additive catalog-only DDL: no data backfill, column removal or feature activation.
Gallery must retain its default-off flag until migration and rollout gates pass.

Revision ID: 0043
Revises: 0042
Create Date: 2026-10-22
"""
from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None

# Keep identical to modules/db_schema/review.py. Self-contained for immutable history.
_CREATE_VIEW_SQL = """
CREATE OR REPLACE VIEW image_bird_bbox_compat AS
SELECT i.id AS image_id,
       CASE WHEN s.id IS NOT NULL THEN
           CASE WHEN r.id IS NOT NULL AND selected_run.display_width > 0
                     AND selected_run.display_height > 0
                THEN s.projected_bird_bbox ELSE i.bird_bbox END
       ELSE COALESCE(NULLIF(imported.legacy_payload, 'null'::jsonb), i.bird_bbox)
       END AS bird_bbox
FROM images i
LEFT JOIN image_localization_selections s
    ON s.image_id = i.id AND s.detector_key = 'bird' AND s.revoked_at IS NULL
LEFT JOIN image_regions r
    ON r.id = s.region_id AND r.localization_run_id = s.localization_run_id
LEFT JOIN image_localization_runs selected_run
    ON selected_run.id = s.localization_run_id AND selected_run.image_id = s.image_id
    AND selected_run.detector_key = s.detector_key
LEFT JOIN image_localization_runs imported
    ON imported.image_id = i.id AND imported.detector_key = 'bird' AND imported.is_current
    AND imported.legacy_payload IS NOT NULL
"""


def upgrade() -> None:
    op.execute(_CREATE_VIEW_SQL)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS image_bird_bbox_compat")
