"""Core PostgreSQL schema: folders, stacks, jobs, images, and job execution tables."""


def initialize_core_schema(cur) -> None:
    # ------------------------------------------------------------------
    # FOLDERS
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS folders (
        id                  SERIAL PRIMARY KEY,
        path                VARCHAR(4000),
        parent_id           INTEGER REFERENCES folders(id) ON DELETE CASCADE,
        is_fully_scored     SMALLINT DEFAULT 0,
        is_keywords_processed SMALLINT DEFAULT 0,
        phase_agg_dirty     INTEGER DEFAULT 1,
        phase_agg_updated_at TIMESTAMP,
        phase_agg_json      TEXT,
        -- DEPRECATED: image_count is unmaintained (no backend writer).
        -- Every backend reader uses ``COUNT(i.id) ... JOIN images i ON i.folder_id = f.id``;
        -- the column is retained only until the Electron consumer is audited
        -- (see audit Issue B3 / Fix 3 in the v7.14 consistency plan).
        image_count         INTEGER DEFAULT 0,
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_folders_path ON folders(path);")
    cur.execute(
        "ALTER TABLE folders ADD COLUMN IF NOT EXISTS image_count INTEGER DEFAULT 0;"
    )

    cur.execute("""
    CREATE TABLE IF NOT EXISTS pipeline_tool_folder_last_touch (
        tool_key          TEXT NOT NULL,
        folder_id         INTEGER NOT NULL REFERENCES folders(id) ON DELETE CASCADE,
        last_touched_at   TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (tool_key, folder_id)
    );
    """)
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_pipeline_tool_folder_touch_tool_time
    ON pipeline_tool_folder_last_touch (tool_key, last_touched_at);
    """)

    # ------------------------------------------------------------------
    # STACKS
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS stacks (
        id              SERIAL PRIMARY KEY,
        name            VARCHAR(255),
        best_image_id   INTEGER,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sub_stacks (
        id                      SERIAL PRIMARY KEY,
        stack_id                INTEGER NOT NULL REFERENCES stacks(id) ON DELETE CASCADE,
        name                    VARCHAR(255),
        best_image_id           INTEGER,
        level1_space            VARCHAR(64),
        level2_visual_space     VARCHAR(64),
        level2_semantic_space   VARCHAR(64),
        policy_version          VARCHAR(50),
        created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_sub_stacks_stack_id ON sub_stacks(stack_id);"
    )

    # ------------------------------------------------------------------
    # JOBS  (full column set matching Firebird schema)
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS jobs (
        id                  SERIAL PRIMARY KEY,
        input_path          VARCHAR(4000),
        phase_id            INTEGER,
        job_type            VARCHAR(50),
        status              VARCHAR(50),
        priority            SMALLINT DEFAULT 100,
        retry_count         INTEGER DEFAULT 0,
        target_scope        VARCHAR(255),
        paused_at           TIMESTAMP,
        queue_position      INTEGER,
        cancel_requested    SMALLINT DEFAULT 0,
        queue_payload       TEXT,
        scope_type          VARCHAR(30),
        scope_paths         TEXT,
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        enqueued_at         TIMESTAMP,
        started_at          TIMESTAMP,
        finished_at         TIMESTAMP,
        completed_at        TIMESTAMP,
        log                 TEXT,
        current_phase       VARCHAR(50),
        next_phase_index    INTEGER,
        runner_state        VARCHAR(50),
        description         TEXT,
        report_json         JSONB
    );
    """)

    # ------------------------------------------------------------------
    # IMAGES  (full column set)
    # ------------------------------------------------------------------
    # Per-model scores (spaq/ava/koniq/paq2piq/liqe) live in
    # ``image_model_scores`` (migration 0016); they no longer have a
    # dedicated column on ``images``.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS images (
        id                  SERIAL PRIMARY KEY,
        job_id              INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
        file_path           VARCHAR(4000),
        file_name           VARCHAR(255),
        file_type           VARCHAR(20),
        score               DOUBLE PRECISION,
        score_general       DOUBLE PRECISION,
        score_technical     DOUBLE PRECISION,
        score_aesthetic     DOUBLE PRECISION,
        keywords            TEXT,
        title               VARCHAR(500),
        description         TEXT,
        metadata            TEXT,
        thumbnail_path      VARCHAR(4000),
        thumbnail_path_win  VARCHAR(4000),
        model_version       VARCHAR(50),
        rating              SMALLINT,
        label               VARCHAR(50),
        pick_status         SMALLINT NOT NULL DEFAULT 0,
        image_hash          VARCHAR(64),
        hash_version        INTEGER NOT NULL DEFAULT 1,
        folder_id           INTEGER REFERENCES folders(id) ON DELETE SET NULL,
        stack_id            INTEGER REFERENCES stacks(id) ON DELETE SET NULL,
        sub_stack_id        INTEGER REFERENCES sub_stacks(id) ON DELETE SET NULL,
        burst_uuid          VARCHAR(64),
        cull_decision       VARCHAR(20),
        cull_policy_version VARCHAR(50),
        image_uuid          VARCHAR(36),
        bird_bbox           JSONB,
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at          TIMESTAMP,
        registered_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cur.execute("ALTER TABLE images ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;")
    # Registration time for the localization new-image boundary (#584). Mirrors
    # migrations/versions/0041_images_registered_at.py: backfill before the default, or
    # every existing row would be stamped "now" and count as new.
    cur.execute("ALTER TABLE images ADD COLUMN IF NOT EXISTS registered_at TIMESTAMP;")
    cur.execute("UPDATE images SET registered_at = created_at WHERE registered_at IS NULL;")
    cur.execute("ALTER TABLE images ALTER COLUMN registered_at SET DEFAULT CURRENT_TIMESTAMP;")
    cur.execute(
        "ALTER TABLE images ADD COLUMN IF NOT EXISTS hash_version INTEGER NOT NULL DEFAULT 1;"
    )
    cur.execute(
        "ALTER TABLE images ADD COLUMN IF NOT EXISTS pick_status SMALLINT NOT NULL DEFAULT 0;"
    )
    cur.execute(
        "ALTER TABLE images ADD COLUMN IF NOT EXISTS sub_stack_id "
        "INTEGER REFERENCES sub_stacks(id) ON DELETE SET NULL;"
    )
    cur.execute("ALTER TABLE images ADD COLUMN IF NOT EXISTS bird_bbox JSONB;")
    cur.execute(
        "UPDATE images SET updated_at = COALESCE(created_at, CURRENT_TIMESTAMP) "
        "WHERE updated_at IS NULL"
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_images_folder_id ON images(folder_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_images_stack_id ON images(stack_id);")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_images_sub_stack_id ON images(sub_stack_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_images_pick_status ON images(pick_status);"
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_images_hash ON images(image_hash);")
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_images_image_hash_hash_version "
        "ON images(image_hash, hash_version) WHERE image_hash IS NOT NULL;"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_images_burst_uuid ON images(burst_uuid);"
    )
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_images_image_uuid ON images(image_uuid) WHERE image_uuid IS NOT NULL;"
    )
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_images_file_path ON images(file_path);"
    )

    # ------------------------------------------------------------------
    # JOB_PHASES — persisted multi-step pipeline plans
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS job_phases (
        id              SERIAL PRIMARY KEY,
        job_id          INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
        phase_order     INTEGER NOT NULL,
        phase_code      VARCHAR(50) NOT NULL,
        state           VARCHAR(20) NOT NULL,
        started_at      TIMESTAMP,
        completed_at    TIMESTAMP,
        error_message   TEXT
    );
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_job_phases_job_id ON job_phases(job_id);"
    )
    cur.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS description TEXT;")
    cur.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS report_json JSONB;")
    cur.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS parent_job_id INTEGER REFERENCES jobs(id);")
    cur.execute("ALTER TABLE job_phases ADD COLUMN IF NOT EXISTS delegated_job_id INTEGER REFERENCES jobs(id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_parent_job_id ON jobs(parent_job_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_job_phases_delegated_job_id ON job_phases(delegated_job_id);")
    cur.execute("""DO $$ BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_jobs_parent_older' AND conrelid = 'jobs'::regclass) THEN
            ALTER TABLE jobs ADD CONSTRAINT ck_jobs_parent_older CHECK (parent_job_id < id);
        END IF;
        IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_job_phases_child_newer' AND conrelid = 'job_phases'::regclass) THEN
            ALTER TABLE job_phases ADD CONSTRAINT ck_job_phases_child_newer CHECK (delegated_job_id > job_id);
        END IF;
    END $$""")

    # job_phases counter columns
    cur.execute(
        "ALTER TABLE job_phases ADD COLUMN IF NOT EXISTS images_in_scope INTEGER DEFAULT 0;"
    )
    cur.execute(
        "ALTER TABLE job_phases ADD COLUMN IF NOT EXISTS images_targeted INTEGER DEFAULT 0;"
    )
    cur.execute(
        "ALTER TABLE job_phases ADD COLUMN IF NOT EXISTS images_processed INTEGER DEFAULT 0;"
    )
    cur.execute(
        "ALTER TABLE job_phases ADD COLUMN IF NOT EXISTS images_skipped INTEGER DEFAULT 0;"
    )
    cur.execute(
        "ALTER TABLE job_phases ADD COLUMN IF NOT EXISTS images_failed INTEGER DEFAULT 0;"
    )

    # ------------------------------------------------------------------
    # JOB_STEPS — sub-phase telemetry
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS job_steps (
        id              SERIAL PRIMARY KEY,
        job_id          INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
        phase_code      VARCHAR(50) NOT NULL,
        step_code       VARCHAR(50) NOT NULL,
        step_name       VARCHAR(100) NOT NULL,
        status          VARCHAR(20) DEFAULT 'pending',
        started_at      TIMESTAMP,
        completed_at    TIMESTAMP,
        items_total     INTEGER DEFAULT 0,
        items_done      INTEGER DEFAULT 0,
        throughput_rps  DOUBLE PRECISION,
        error_message   TEXT
    );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS idx_job_steps_job_id ON job_steps(job_id);")

    # ------------------------------------------------------------------
    # JOB_IMAGE_ACTIONS — per-image execution trail with before/after snapshots
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS job_image_actions (
        id              SERIAL PRIMARY KEY,
        job_id          INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
        image_id        INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
        phase_code      VARCHAR(50) NOT NULL,
        action          VARCHAR(30) NOT NULL,
        reason          TEXT,
        before_snapshot JSONB,
        after_snapshot  JSONB,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_jia_job_id ON job_image_actions(job_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_jia_job_phase ON job_image_actions(job_id, phase_code);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_jia_image_id ON job_image_actions(image_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_jia_created_at ON job_image_actions(created_at);"
    )

    # ------------------------------------------------------------------
    # IMAGE_PHASE_WORK_CLAIMS — dedupe open image×phase work across runs
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS image_phase_work_claims (
        id              SERIAL PRIMARY KEY,
        job_id          INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
        image_id        INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
        phase_code      VARCHAR(50) NOT NULL,
        status          VARCHAR(20) NOT NULL DEFAULT 'queued',
        claimed_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        released_at     TIMESTAMP
    );
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ipwc_job_phase ON image_phase_work_claims(job_id, phase_code);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ipwc_image_phase ON image_phase_work_claims(image_id, phase_code);"
    )
    cur.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS uq_ipwc_open_image_phase
      ON image_phase_work_claims (image_id, phase_code)
      WHERE status IN ('queued', 'running');
    """)
