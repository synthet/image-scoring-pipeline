"""Initial PostgreSQL schema — full parity with Firebird

Revision ID: 0001
Revises:
Create Date: 2026-03-23

Creates all tables, indexes, and constraints that match the Firebird schema
defined in modules/db.py.  The pgvector extension is required (included in the
ankane/pgvector Docker image used by docker-compose.postgres.yml).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    # pgvector extension
    conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector;"))

    # ------------------------------------------------------------------
    # FOLDERS
    # ------------------------------------------------------------------
    op.create_table(
        "folders",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("path", sa.String(4000), nullable=True),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("is_fully_scored", sa.SmallInteger(), server_default="0", nullable=True),
        sa.Column("is_keywords_processed", sa.SmallInteger(), server_default="0", nullable=True),
        sa.Column("phase_agg_dirty", sa.Integer(), server_default="1", nullable=True),
        sa.Column("phase_agg_updated_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("phase_agg_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["parent_id"], ["folders.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_folders_path", "folders", ["path"], unique=True)

    # ------------------------------------------------------------------
    # STACKS
    # ------------------------------------------------------------------
    op.create_table(
        "stacks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("best_image_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # ------------------------------------------------------------------
    # JOBS
    # ------------------------------------------------------------------
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("input_path", sa.String(4000), nullable=True),
        sa.Column("phase_id", sa.Integer(), nullable=True),
        sa.Column("job_type", sa.String(50), nullable=True),
        sa.Column("status", sa.String(50), nullable=True),
        sa.Column("priority", sa.SmallInteger(), server_default="100", nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=True),
        sa.Column("target_scope", sa.String(255), nullable=True),
        sa.Column("paused_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("queue_position", sa.Integer(), nullable=True),
        sa.Column("cancel_requested", sa.SmallInteger(), server_default="0", nullable=True),
        sa.Column("queue_payload", sa.Text(), nullable=True),
        sa.Column("scope_type", sa.String(30), nullable=True),
        sa.Column("scope_paths", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("enqueued_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("log", sa.Text(), nullable=True),
        sa.Column("current_phase", sa.String(50), nullable=True),
        sa.Column("next_phase_index", sa.Integer(), nullable=True),
        sa.Column("runner_state", sa.String(50), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # ------------------------------------------------------------------
    # JOB_PHASES
    # ------------------------------------------------------------------
    op.create_table(
        "job_phases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("phase_order", sa.Integer(), nullable=False),
        sa.Column("phase_code", sa.String(50), nullable=False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_job_phases_job_id", "job_phases", ["job_id"])

    # ------------------------------------------------------------------
    # JOB_STEPS
    # ------------------------------------------------------------------
    op.create_table(
        "job_steps",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("phase_code", sa.String(50), nullable=False),
        sa.Column("step_code", sa.String(50), nullable=False),
        sa.Column("step_name", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("items_total", sa.Integer(), server_default="0", nullable=True),
        sa.Column("items_done", sa.Integer(), server_default="0", nullable=True),
        sa.Column("throughput_rps", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_job_steps_job_id", "job_steps", ["job_id"])

    # ------------------------------------------------------------------
    # IMAGES
    # ------------------------------------------------------------------
    # vector(1280) is a pgvector type — created via raw DDL
    op.create_table(
        "images",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("file_path", sa.String(4000), nullable=True),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("file_type", sa.String(20), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("score_general", sa.Float(), nullable=True),
        sa.Column("score_technical", sa.Float(), nullable=True),
        sa.Column("score_aesthetic", sa.Float(), nullable=True),
        sa.Column("score_spaq", sa.Float(), nullable=True),
        sa.Column("score_ava", sa.Float(), nullable=True),
        sa.Column("score_koniq", sa.Float(), nullable=True),
        sa.Column("score_paq2piq", sa.Float(), nullable=True),
        sa.Column("score_liqe", sa.Float(), nullable=True),
        sa.Column("keywords", sa.Text(), nullable=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column("thumbnail_path", sa.String(4000), nullable=True),
        sa.Column("thumbnail_path_win", sa.String(4000), nullable=True),
        sa.Column("scores_json", sa.Text(), nullable=True),
        sa.Column("model_version", sa.String(50), nullable=True),
        sa.Column("rating", sa.SmallInteger(), nullable=True),
        sa.Column("label", sa.String(50), nullable=True),
        sa.Column("image_hash", sa.String(64), nullable=True),
        sa.Column("folder_id", sa.Integer(), nullable=True),
        sa.Column("stack_id", sa.Integer(), nullable=True),
        sa.Column("burst_uuid", sa.String(64), nullable=True),
        sa.Column("cull_decision", sa.String(20), nullable=True),
        sa.Column("cull_policy_version", sa.String(50), nullable=True),
        sa.Column("image_uuid", sa.String(36), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["folder_id"], ["folders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["stack_id"], ["stacks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    # image_embedding vector(1280) added separately — not a SQLAlchemy native type
    conn.execute(sa.text(
        "ALTER TABLE images ADD COLUMN IF NOT EXISTS image_embedding vector(1280);"
    ))

    op.create_index("idx_images_folder_id", "images", ["folder_id"])
    op.create_index("idx_images_stack_id", "images", ["stack_id"])
    op.create_index("idx_images_hash", "images", ["image_hash"])
    op.create_index("idx_images_burst_uuid", "images", ["burst_uuid"])
    conn.execute(sa.text(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_images_image_uuid "
        "ON images(image_uuid) WHERE image_uuid IS NOT NULL;"
    ))
    conn.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_images_embedding_hnsw "
        "ON images USING hnsw (image_embedding vector_cosine_ops);"
    ))

    # stacks.best_image_id FK (back-fill after images exists)
    op.create_foreign_key(
        "fk_stacks_best_image", "stacks", "images",
        ["best_image_id"], ["id"], ondelete="SET NULL",
    )

    # ------------------------------------------------------------------
    # FILE_PATHS
    # ------------------------------------------------------------------
    op.create_table(
        "file_paths",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("image_id", sa.Integer(), nullable=True),
        sa.Column("path", sa.String(4000), nullable=True),
        sa.Column("last_seen", sa.TIMESTAMP(), nullable=True),
        sa.Column("path_type", sa.String(10), nullable=True),
        sa.Column("is_verified", sa.SmallInteger(), server_default="0", nullable=True),
        sa.Column("verification_date", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_file_paths_img_type", "file_paths", ["image_id", "path_type"])

    # ------------------------------------------------------------------
    # CLUSTER_PROGRESS
    # ------------------------------------------------------------------
    op.create_table(
        "cluster_progress",
        sa.Column("folder_path", sa.String(512), nullable=False),
        sa.Column("last_run", sa.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("folder_path"),
    )

    # ------------------------------------------------------------------
    # CULLING_SESSIONS
    # ------------------------------------------------------------------
    op.create_table(
        "culling_sessions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("folder_path", sa.String(4000), nullable=True),
        sa.Column("mode", sa.String(50), nullable=True),
        sa.Column("status", sa.String(50), server_default="active", nullable=True),
        sa.Column("total_images", sa.Integer(), server_default="0", nullable=True),
        sa.Column("total_groups", sa.Integer(), server_default="0", nullable=True),
        sa.Column("reviewed_groups", sa.Integer(), server_default="0", nullable=True),
        sa.Column("picked_count", sa.Integer(), server_default="0", nullable=True),
        sa.Column("rejected_count", sa.Integer(), server_default="0", nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    # ------------------------------------------------------------------
    # CULLING_PICKS
    # ------------------------------------------------------------------
    op.create_table(
        "culling_picks",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("image_id", sa.Integer(), nullable=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("decision", sa.String(50), nullable=True),
        sa.Column("auto_suggested", sa.SmallInteger(), server_default="0", nullable=True),
        sa.Column("is_best_in_group", sa.SmallInteger(), server_default="0", nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=True),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["culling_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_culling_picks_session", "culling_picks", ["session_id"])
    op.create_index("idx_culling_picks_image", "culling_picks", ["image_id"])

    # ------------------------------------------------------------------
    # IMAGE_EXIF
    # ------------------------------------------------------------------
    op.create_table(
        "image_exif",
        sa.Column("image_id", sa.Integer(), nullable=False),
        sa.Column("make", sa.String(100), nullable=True),
        sa.Column("model", sa.String(200), nullable=True),
        sa.Column("lens_model", sa.String(255), nullable=True),
        sa.Column("focal_length", sa.String(50), nullable=True),
        sa.Column("focal_length_35mm", sa.SmallInteger(), nullable=True),
        sa.Column("date_time_original", sa.TIMESTAMP(), nullable=True),
        sa.Column("create_date", sa.TIMESTAMP(), nullable=True),
        sa.Column("exposure_time", sa.String(30), nullable=True),
        sa.Column("f_number", sa.String(20), nullable=True),
        sa.Column("iso", sa.Integer(), nullable=True),
        sa.Column("exposure_compensation", sa.String(20), nullable=True),
        sa.Column("image_width", sa.Integer(), nullable=True),
        sa.Column("image_height", sa.Integer(), nullable=True),
        sa.Column("orientation", sa.SmallInteger(), nullable=True),
        sa.Column("flash", sa.SmallInteger(), nullable=True),
        sa.Column("image_unique_id", sa.String(64), nullable=True),
        sa.Column("shutter_count", sa.Integer(), nullable=True),
        sa.Column("sub_sec_time_original", sa.String(10), nullable=True),
        sa.Column("extracted_at", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("image_id"),
    )
    op.create_index("idx_image_exif_date", "image_exif", ["date_time_original"])
    op.create_index("idx_image_exif_make", "image_exif", ["make"])
    op.create_index("idx_image_exif_model", "image_exif", ["model"])
    op.create_index("idx_image_exif_lens", "image_exif", ["lens_model"])
    op.create_index("idx_image_exif_iso", "image_exif", ["iso"])

    # ------------------------------------------------------------------
    # IMAGE_XMP
    # ------------------------------------------------------------------
    op.create_table(
        "image_xmp",
        sa.Column("image_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.SmallInteger(), nullable=True),
        sa.Column("label", sa.String(50), nullable=True),
        sa.Column("pick_status", sa.SmallInteger(), nullable=True),
        sa.Column("burst_uuid", sa.String(64), nullable=True),
        sa.Column("stack_id", sa.String(64), nullable=True),
        sa.Column("keywords", sa.Text(), nullable=True),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("create_date", sa.TIMESTAMP(), nullable=True),
        sa.Column("modify_date", sa.TIMESTAMP(), nullable=True),
        sa.Column("extracted_at", sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("image_id"),
    )
    op.create_index("idx_image_xmp_burst", "image_xmp", ["burst_uuid"])
    op.create_index("idx_image_xmp_pick", "image_xmp", ["pick_status"])

    # ------------------------------------------------------------------
    # PIPELINE_PHASES
    # ------------------------------------------------------------------
    op.create_table(
        "pipeline_phases",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("enabled", sa.SmallInteger(), server_default="1", nullable=False),
        sa.Column("optional", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("default_skip", sa.SmallInteger(), server_default="0", nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_pipeline_phases_code", "pipeline_phases", ["code"], unique=True)

    # ------------------------------------------------------------------
    # IMAGE_PHASE_STATUS
    # ------------------------------------------------------------------
    op.create_table(
        "image_phase_status",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("image_id", sa.Integer(), nullable=False),
        sa.Column("phase_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(20), server_default="not_started", nullable=False),
        sa.Column("executor_version", sa.String(50), nullable=True),
        sa.Column("app_version", sa.String(50), nullable=True),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("attempt_count", sa.SmallInteger(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("finished_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("skip_reason", sa.Text(), nullable=True),
        sa.Column("skipped_by", sa.String(255), nullable=True),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["phase_id"], ["pipeline_phases.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_image_phase", "image_phase_status", ["image_id", "phase_id"], unique=True)
    op.create_index("idx_ips_image_id", "image_phase_status", ["image_id"])
    op.create_index("idx_ips_phase_id", "image_phase_status", ["phase_id"])
    op.create_index("idx_ips_status", "image_phase_status", ["status"])

    # ------------------------------------------------------------------
    # STACK_CACHE
    # ------------------------------------------------------------------
    op.create_table(
        "stack_cache",
        sa.Column("stack_id", sa.Integer(), nullable=False),
        sa.Column("image_count", sa.Integer(), server_default="0", nullable=True),
        sa.Column("rep_image_id", sa.Integer(), nullable=True),
        sa.Column("min_score_general", sa.Float(), nullable=True),
        sa.Column("max_score_general", sa.Float(), nullable=True),
        sa.Column("min_score_technical", sa.Float(), nullable=True),
        sa.Column("max_score_technical", sa.Float(), nullable=True),
        sa.Column("min_score_aesthetic", sa.Float(), nullable=True),
        sa.Column("max_score_aesthetic", sa.Float(), nullable=True),
        sa.Column("min_score_spaq", sa.Float(), nullable=True),
        sa.Column("max_score_spaq", sa.Float(), nullable=True),
        sa.Column("min_score_ava", sa.Float(), nullable=True),
        sa.Column("max_score_ava", sa.Float(), nullable=True),
        sa.Column("min_score_liqe", sa.Float(), nullable=True),
        sa.Column("max_score_liqe", sa.Float(), nullable=True),
        sa.Column("min_rating", sa.Integer(), nullable=True),
        sa.Column("max_rating", sa.Integer(), nullable=True),
        sa.Column("min_created_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("max_created_at", sa.TIMESTAMP(), nullable=True),
        sa.Column("folder_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["folder_id"], ["folders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["rep_image_id"], ["images.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["stack_id"], ["stacks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("stack_id"),
    )


def downgrade() -> None:
    op.drop_table("stack_cache")
    op.drop_table("image_phase_status")
    op.drop_table("pipeline_phases")
    op.drop_table("image_xmp")
    op.drop_table("image_exif")
    op.drop_table("culling_picks")
    op.drop_table("culling_sessions")
    op.drop_table("cluster_progress")
    op.drop_table("file_paths")
    op.drop_table("images")
    op.drop_table("job_steps")
    op.drop_table("job_phases")
    op.drop_table("jobs")
    op.drop_table("stacks")
    op.drop_table("folders")
