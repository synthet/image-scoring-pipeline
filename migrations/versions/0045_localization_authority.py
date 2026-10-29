"""Add dormant localization authority metadata; no backfill or production effects.

Only creates new tables/indexes and a default-off singleton. Existing image tables
are not rewritten. Old application versions ignore the additive metadata. Downgrade
requires an explicit maintenance decision; no application path performs it.
"""
from alembic import op

revision = "0045"
down_revision = "0044"
branch_labels = None
depends_on = None

# Immutable copy: migration history must not import changing application DDL.
AUTHORITY_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS localization_authority_control (
    id SMALLINT PRIMARY KEY CHECK (id = 1),
    mode TEXT NOT NULL DEFAULT 'off' CHECK (mode IN ('off', 'shadow')),
    revision BIGINT NOT NULL DEFAULT 0 CHECK (revision >= 0),
    scan_cursor BIGINT NOT NULL DEFAULT 0,
    scan_upper_bound BIGINT NOT NULL DEFAULT 0,
    reservation_inventory_sha256 TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
INSERT INTO localization_authority_control (id) VALUES (1) ON CONFLICT DO NOTHING;
ALTER TABLE localization_authority_control ADD COLUMN IF NOT EXISTS scan_upper_bound BIGINT NOT NULL DEFAULT 0;
CREATE TABLE IF NOT EXISTS localization_authority_policies (
    policy_hash TEXT PRIMARY KEY CHECK (length(policy_hash) = 64),
    rule_id TEXT NOT NULL,
    rule_sha256 TEXT NOT NULL CHECK (length(rule_sha256) = 64),
    scope JSONB NOT NULL,
    approval_revision BIGINT NOT NULL DEFAULT 0 CHECK (approval_revision = 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS localization_authority_observations (
    image_id INTEGER PRIMARY KEY REFERENCES images(id) ON DELETE CASCADE,
    revision BIGINT NOT NULL DEFAULT 1 CHECK (revision > 0),
    authority_revision BIGINT NOT NULL DEFAULT 1,
    discovery_revision BIGINT NOT NULL DEFAULT 1,
    ownership_revision BIGINT NOT NULL DEFAULT 1,
    source_revision BIGINT NOT NULL DEFAULT 1,
    reservation_revision BIGINT NOT NULL DEFAULT 1,
    components JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS localization_authority_reservations (
    inventory_sha256 TEXT NOT NULL CHECK (length(inventory_sha256) = 64),
    image_id INTEGER NOT NULL CHECK (image_id > 0),
    original_run_id BIGINT NOT NULL,
    original_region_id BIGINT NOT NULL,
    evidence JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (inventory_sha256, image_id)
);
CREATE INDEX IF NOT EXISTS ix_authority_reservations_image
    ON localization_authority_reservations (image_id);
CREATE TABLE IF NOT EXISTS localization_authority_evaluations (
    id BIGSERIAL PRIMARY KEY,
    policy_hash TEXT NOT NULL REFERENCES localization_authority_policies(policy_hash),
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    run_id BIGINT NOT NULL REFERENCES image_localization_runs(id) ON DELETE CASCADE,
    artifact_fingerprint TEXT NOT NULL CHECK (length(artifact_fingerprint) = 64),
    outcome TEXT NOT NULL CHECK (outcome IN ('accept', 'reject', 'abstain', 'invalid')),
    reason TEXT NOT NULL,
    result JSONB NOT NULL,
    population_snapshot JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (policy_hash, artifact_fingerprint)
);
CREATE INDEX IF NOT EXISTS ix_authority_evaluations_image
    ON localization_authority_evaluations (image_id, id);
CREATE TABLE IF NOT EXISTS localization_authority_attempts (
    id BIGSERIAL PRIMARY KEY,
    evaluation_id BIGINT NOT NULL REFERENCES localization_authority_evaluations(id) ON DELETE CASCADE,
    context_hash TEXT NOT NULL CHECK (length(context_hash) = 64),
    context JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'completed')),
    fencing_token BIGINT NOT NULL DEFAULT 0 CHECK (fencing_token >= 0),
    fenced_rejections BIGINT NOT NULL DEFAULT 0,
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    lease_until TIMESTAMPTZ,
    available_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    disposition TEXT,
    proposal JSONB,
    last_error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    completed_at TIMESTAMPTZ,
    UNIQUE (evaluation_id, context_hash)
);
CREATE INDEX IF NOT EXISTS ix_authority_attempts_claim
    -- Bootstrap also tolerates the earlier local development table shape.
    ON localization_authority_attempts (available_at, id) WHERE status <> 'completed';
ALTER TABLE localization_authority_attempts ADD COLUMN IF NOT EXISTS fenced_rejections BIGINT NOT NULL DEFAULT 0;
CREATE TABLE IF NOT EXISTS localization_authority_lineage (
    attempt_id BIGINT PRIMARY KEY REFERENCES localization_authority_attempts(id) ON DELETE CASCADE,
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    input_state JSONB NOT NULL,
    proposed_action TEXT NOT NULL CHECK (proposed_action IN ('classify', 'fallback', 'cleanup', 'preserve', 'none')),
    outputs_protected BOOLEAN NOT NULL DEFAULT TRUE CHECK (outputs_protected),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE TABLE IF NOT EXISTS localization_authority_scan_faults (
    image_id INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
    policy_hash TEXT NOT NULL REFERENCES localization_authority_policies(policy_hash),
    input_fingerprint TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'waiting' CHECK (status IN ('waiting','exhausted','recovered')),
    retry_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()+interval '60 seconds',
    error_code TEXT NOT NULL,
    PRIMARY KEY (image_id,policy_hash,input_fingerprint)
);
CREATE INDEX IF NOT EXISTS ix_authority_scan_faults_retry
    ON localization_authority_scan_faults (retry_at) WHERE status='waiting';
CREATE OR REPLACE FUNCTION localization_authority_immutable() RETURNS trigger
LANGUAGE plpgsql AS $authority$
BEGIN
    RAISE EXCEPTION 'localization authority evidence is immutable';
END;
$authority$;
CREATE OR REPLACE TRIGGER trg_authority_policy_immutable
    BEFORE UPDATE ON localization_authority_policies
    FOR EACH ROW EXECUTE FUNCTION localization_authority_immutable();
CREATE OR REPLACE TRIGGER trg_authority_evaluation_immutable
    BEFORE UPDATE ON localization_authority_evaluations
    FOR EACH ROW EXECUTE FUNCTION localization_authority_immutable();
"""


def upgrade() -> None:
    op.execute(AUTHORITY_SCHEMA_SQL)


def downgrade() -> None:
    for table in (
        "localization_authority_scan_faults",
        "localization_authority_lineage", "localization_authority_attempts",
        "localization_authority_evaluations", "localization_authority_reservations",
        "localization_authority_observations", "localization_authority_policies",
        "localization_authority_control",
    ):
        op.execute(f"DROP TABLE {table}")
    op.execute("DROP FUNCTION localization_authority_immutable()")
