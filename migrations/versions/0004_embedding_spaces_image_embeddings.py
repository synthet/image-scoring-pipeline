"""Embedding registry + image_embeddings (1280-d pgvector); backfill from images.

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-01
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector;"))
    op.create_table(
        "embedding_spaces",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("dim", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("active", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_embedding_spaces_code"),
    )
    op.create_table(
        "image_embeddings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("image_id", sa.Integer(), nullable=False),
        sa.Column("embedding_space_id", sa.Integer(), nullable=False),
        sa.Column("model_version", sa.String(64), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["embedding_space_id"], ["embedding_spaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("image_id", "embedding_space_id", name="uq_image_embeddings_image_space"),
    )
    conn.execute(sa.text("ALTER TABLE image_embeddings ADD COLUMN embedding vector(1280);"))
    op.create_index("idx_image_embeddings_image", "image_embeddings", ["image_id"], unique=False)
    op.create_index("idx_image_embeddings_space", "image_embeddings", ["embedding_space_id"], unique=False)
    conn.execute(
        sa.text(
            """
            CREATE INDEX IF NOT EXISTS idx_image_embeddings_hnsw
            ON image_embeddings USING hnsw (embedding vector_cosine_ops);
            """
        )
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO embedding_spaces (code, dim, description, active)
            SELECT 'mobilenet_v2_imagenet_gap', 1280,
                   'MobileNetV2 ImageNet weights, GAP — visual similarity / culling', 1
            WHERE NOT EXISTS (SELECT 1 FROM embedding_spaces WHERE code = 'mobilenet_v2_imagenet_gap');
            """
        )
    )
    conn.execute(
        sa.text(
            """
            INSERT INTO image_embeddings (image_id, embedding_space_id, embedding, updated_at)
            SELECT i.id, s.id, i.image_embedding, CURRENT_TIMESTAMP
            FROM images i
            CROSS JOIN (SELECT id FROM embedding_spaces WHERE code = 'mobilenet_v2_imagenet_gap' LIMIT 1) s
            WHERE i.image_embedding IS NOT NULL
            ON CONFLICT (image_id, embedding_space_id) DO NOTHING;
            """
        )
    )
    conn.execute(sa.text("ALTER TABLE image_embeddings ALTER COLUMN embedding SET NOT NULL;"))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP INDEX IF EXISTS idx_image_embeddings_hnsw;"))
    op.drop_index("idx_image_embeddings_space", table_name="image_embeddings")
    op.drop_index("idx_image_embeddings_image", table_name="image_embeddings")
    op.drop_table("image_embeddings")
    op.drop_table("embedding_spaces")
