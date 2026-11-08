"""Add a capture key to deleted_images (#821).

Revision ID: 0049
Revises: 0048

Card originals have no ImageUniqueID, so only original_path could match a tombstone.
The key survives a new library root or a renamed lens folder. Existing tombstones
keep a NULL key.

exec_driver_sql, not op.execute: text() reads HH24:MI:SS as bind parameters.
"""

from alembic import op

revision = "0049"
down_revision = "0048"
branch_labels = None
depends_on = None

UPGRADE_SQL = (
    "ALTER TABLE deleted_images ADD COLUMN IF NOT EXISTS capture_key VARCHAR(255);",
    "CREATE INDEX IF NOT EXISTS idx_deleted_images_capture_key ON deleted_images(capture_key) "
    "WHERE capture_key IS NOT NULL;",
    """
    CREATE OR REPLACE FUNCTION image_capture_key(p_image_id INTEGER)
    RETURNS VARCHAR AS $$
        SELECT btrim(model) || '|' || shutter_count::text || '|'
               || to_char(date_time_original, 'YYYY-MM-DD"T"HH24:MI:SS')
        FROM image_exif
        WHERE image_id = p_image_id
          AND btrim(model) <> ''
          AND shutter_count > 0
          AND date_time_original IS NOT NULL;
    $$ LANGUAGE sql STABLE;
    """,
    """
    CREATE OR REPLACE FUNCTION trg_record_deleted_image_fn()
    RETURNS TRIGGER AS $$
    BEGIN
        INSERT INTO deleted_images (original_id, image_uuid, image_hash, file_name, original_path, capture_key)
        VALUES (OLD.id, OLD.image_uuid, OLD.image_hash, OLD.file_name, OLD.file_path, image_capture_key(OLD.id));
        RETURN OLD;
    END;
    $$ LANGUAGE plpgsql;
    """,
)

DOWNGRADE_SQL = (
    """
    CREATE OR REPLACE FUNCTION trg_record_deleted_image_fn()
    RETURNS TRIGGER AS $$
    BEGIN
        INSERT INTO deleted_images (original_id, image_uuid, image_hash, file_name, original_path)
        VALUES (OLD.id, OLD.image_uuid, OLD.image_hash, OLD.file_name, OLD.file_path);
        RETURN OLD;
    END;
    $$ LANGUAGE plpgsql;
    """,
    "DROP FUNCTION IF EXISTS image_capture_key(INTEGER);",
    "DROP INDEX IF EXISTS idx_deleted_images_capture_key;",
    "ALTER TABLE deleted_images DROP COLUMN IF EXISTS capture_key;",
)


def upgrade() -> None:
    bind = op.get_bind()
    for statement in UPGRADE_SQL:
        bind.exec_driver_sql(statement)


def downgrade() -> None:
    bind = op.get_bind()
    for statement in DOWNGRADE_SQL:
        bind.exec_driver_sql(statement)
