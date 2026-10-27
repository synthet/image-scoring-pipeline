"""Register the ``bioclip_2_crop`` embedding space (#641).

BioCLIP vectors from a crop (a selected localization region or the embedded detector's box) must
not share ``bioclip_2_image`` with full-frame vectors: the localization rollout invariant forbids
one embedding identity across input modes. Additive and idempotent — vectors land in the existing
``image_embeddings_768`` table; no new physical storage.

Revision ID: 0042
Revises: 0041
Create Date: 2026-10-17
"""

from __future__ import annotations

from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None

# Keep in sync with modules/embedding_spaces.SPACE_DIMS and
# modules/db_postgres._SEED_EXTRA_EMBEDDING_SPACES_SQL.
_CODE = "bioclip_2_crop"
_DIM = 768
_DESCRIPTION = "BioCLIP 2 image tower ViT-L/14 on a bird crop (region or detector box) — species similarity"


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        """
        INSERT INTO embedding_spaces (code, dim, description, active)
        SELECT %s, %s, %s, 1
        WHERE NOT EXISTS (SELECT 1 FROM embedding_spaces WHERE code = %s)
        """,
        (_CODE, _DIM, _DESCRIPTION, _CODE),
    )


def downgrade() -> None:
    # Only drop the registry row; fact rows cascade via the embedding_space_id FK.
    op.get_bind().exec_driver_sql("DELETE FROM embedding_spaces WHERE code = %s", (_CODE,))
