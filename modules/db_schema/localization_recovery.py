"""Targeted negative-recovery markers (#706); mirrored in migration 0048."""

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


def initialize_recovery_schema(cur):
    cur.execute(RECOVERY_SCHEMA_SQL)
