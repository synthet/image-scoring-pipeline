"""Persist culling parent/child links (#368), without rewriting historical runs."""

from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS parent_job_id INTEGER REFERENCES jobs(id)")
    op.execute("ALTER TABLE job_phases ADD COLUMN IF NOT EXISTS delegated_job_id INTEGER REFERENCES jobs(id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_jobs_parent_job_id ON jobs(parent_job_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_job_phases_delegated_job_id ON job_phases(delegated_job_id)")
    op.execute("""DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_jobs_parent_older' AND conrelid = 'jobs'::regclass) THEN
            ALTER TABLE jobs ADD CONSTRAINT ck_jobs_parent_older CHECK (parent_job_id < id);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_job_phases_child_newer' AND conrelid = 'job_phases'::regclass) THEN
            ALTER TABLE job_phases ADD CONSTRAINT ck_job_phases_child_newer CHECK (delegated_job_id > job_id);
        END IF;
    END $$""")


def downgrade():
    op.execute("""DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM jobs j JOIN job_phases p ON p.job_id = j.id
                   WHERE p.delegated_job_id IS NOT NULL
                     AND j.status NOT IN ('completed', 'failed', 'cancelled', 'canceled')) THEN
            RAISE EXCEPTION 'Drain unfinished delegated jobs before downgrade';
        END IF;
    END $$""")
    op.execute("ALTER TABLE job_phases DROP COLUMN delegated_job_id")
    op.execute("ALTER TABLE jobs DROP COLUMN parent_job_id")
