"""Add targeted negative-recovery markers for the localization lane."""
from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None

RECOVERY_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS localization_recovery_attempts (
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    detector_key TEXT NOT NULL,
    detector_config_hash TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    source_hash_version TEXT NOT NULL,
    policy_key TEXT NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (image_id,detector_key,detector_config_hash,source_hash,source_hash_version,policy_key)
);
"""

def upgrade():
    op.get_bind().exec_driver_sql(RECOVERY_SCHEMA_SQL)

def downgrade():
    op.get_bind().exec_driver_sql("DROP TABLE IF EXISTS localization_recovery_attempts")
