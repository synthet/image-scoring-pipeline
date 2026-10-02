"""PostgreSQL file, metadata, pipeline-state, stack-cache, and keyword schema."""

import logging


logger = logging.getLogger(__name__)


def initialize_pipeline_schema(cur) -> None:
    # ------------------------------------------------------------------
    # FILE_PATHS
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS file_paths (
        id                  SERIAL PRIMARY KEY,
        image_id            INTEGER REFERENCES images(id) ON DELETE CASCADE,
        path                VARCHAR(4000),
        last_seen           TIMESTAMP,
        path_type           VARCHAR(10),
        is_verified         SMALLINT DEFAULT 0,
        verification_date   TIMESTAMP
    );
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_file_paths_img_type ON file_paths(image_id, path_type);"
    )
    cur.execute(
        "SELECT 1 FROM pg_indexes WHERE schemaname = ANY (current_schemas(false)) "
        "AND indexname = 'uq_file_paths_image_id_path'"
    )
    if cur.fetchone() is None:
        cur.execute(
            """
            DELETE FROM file_paths AS fp1
            USING file_paths AS fp2
            WHERE fp1.id > fp2.id
              AND fp1.image_id IS NOT DISTINCT FROM fp2.image_id
              AND fp1.path IS NOT DISTINCT FROM fp2.path
            """
        )
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_file_paths_image_id_path "
        "ON file_paths(image_id, path);"
    )

    # ------------------------------------------------------------------
    # CLUSTER_PROGRESS
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS cluster_progress (
        folder_path VARCHAR(512) NOT NULL PRIMARY KEY,
        last_run    TIMESTAMP
    );
    """)

    # ------------------------------------------------------------------
    # CULLING_SESSIONS
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS culling_sessions (
        id                  SERIAL PRIMARY KEY,
        folder_path         VARCHAR(4000),
        mode                VARCHAR(50),
        status              VARCHAR(50) DEFAULT 'active',
        total_images        INTEGER DEFAULT 0,
        total_groups        INTEGER DEFAULT 0,
        reviewed_groups     INTEGER DEFAULT 0,
        picked_count        INTEGER DEFAULT 0,
        rejected_count      INTEGER DEFAULT 0,
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        completed_at        TIMESTAMP
    );
    """)

    # ------------------------------------------------------------------
    # CULLING_PICKS
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS culling_picks (
        id                  SERIAL PRIMARY KEY,
        session_id          INTEGER REFERENCES culling_sessions(id) ON DELETE CASCADE,
        image_id            INTEGER REFERENCES images(id) ON DELETE CASCADE,
        group_id            INTEGER,
        decision            VARCHAR(50),
        auto_suggested      SMALLINT DEFAULT 0,
        is_best_in_group    SMALLINT DEFAULT 0,
        created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_culling_picks_session ON culling_picks(session_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_culling_picks_image ON culling_picks(image_id);"
    )

    # ------------------------------------------------------------------
    # IMAGE_EXIF — cached EXIF metadata (one row per image)
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS image_exif (
        image_id                INTEGER NOT NULL PRIMARY KEY REFERENCES images(id) ON DELETE CASCADE,
        make                    VARCHAR(100),
        model                   VARCHAR(200),
        lens_model              VARCHAR(255),
        focal_length            VARCHAR(50),
        focal_length_35mm       SMALLINT,
        date_time_original      TIMESTAMP,
        create_date             TIMESTAMP,
        exposure_time           VARCHAR(30),
        f_number                VARCHAR(20),
        iso                     INTEGER,
        exposure_compensation   VARCHAR(20),
        image_width             INTEGER,
        image_height            INTEGER,
        orientation             SMALLINT,
        flash                   SMALLINT,
        image_unique_id         VARCHAR(64),
        shutter_count           INTEGER,
        sub_sec_time_original   VARCHAR(10),
        gps_latitude            DOUBLE PRECISION,
        gps_longitude           DOUBLE PRECISION,
        gps_altitude            DOUBLE PRECISION,
        gps_position_source       VARCHAR(20),
        location_resolved       JSONB,
        geocoded_at             TIMESTAMP,
        geocode_provider        VARCHAR(50),
        extracted_at            TIMESTAMP
    );
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_image_exif_date ON image_exif(date_time_original);"
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_image_exif_make ON image_exif(make);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_image_exif_model ON image_exif(model);")
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_image_exif_lens ON image_exif(lens_model);"
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_image_exif_iso ON image_exif(iso);")
    cur.execute(
        "ALTER TABLE image_exif ADD COLUMN IF NOT EXISTS gps_latitude DOUBLE PRECISION;"
    )
    cur.execute(
        "ALTER TABLE image_exif ADD COLUMN IF NOT EXISTS gps_longitude DOUBLE PRECISION;"
    )
    cur.execute(
        "ALTER TABLE image_exif ADD COLUMN IF NOT EXISTS gps_altitude DOUBLE PRECISION;"
    )
    cur.execute(
        "ALTER TABLE image_exif ADD COLUMN IF NOT EXISTS gps_position_source VARCHAR(20);"
    )
    cur.execute(
        "ALTER TABLE image_exif ADD COLUMN IF NOT EXISTS location_resolved JSONB;"
    )
    cur.execute(
        "ALTER TABLE image_exif ADD COLUMN IF NOT EXISTS geocoded_at TIMESTAMP;"
    )
    cur.execute(
        "ALTER TABLE image_exif ADD COLUMN IF NOT EXISTS geocode_provider VARCHAR(50);"
    )

    # ------------------------------------------------------------------
    # IMAGE_XMP — cached XMP sidecar metadata (one row per image)
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS image_xmp (
        image_id        INTEGER NOT NULL PRIMARY KEY REFERENCES images(id) ON DELETE CASCADE,
        rating          SMALLINT,
        label           VARCHAR(50),
        pick_status     SMALLINT,
        burst_uuid      VARCHAR(64),
        stack_id        VARCHAR(64),
        keywords        TEXT,
        title           VARCHAR(500),
        description     TEXT,
        alt_text        TEXT,
        extended_description TEXT,
        create_date     TIMESTAMP,
        modify_date     TIMESTAMP,
        extracted_at    TIMESTAMP
    );
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_image_xmp_burst ON image_xmp(burst_uuid);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_image_xmp_pick ON image_xmp(pick_status);"
    )
    cur.execute("ALTER TABLE image_xmp ADD COLUMN IF NOT EXISTS alt_text TEXT;")
    cur.execute(
        "ALTER TABLE image_xmp ADD COLUMN IF NOT EXISTS extended_description TEXT;"
    )

    # ------------------------------------------------------------------
    # PIPELINE_PHASES — phase registry
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS pipeline_phases (
        id              SERIAL PRIMARY KEY,
        code            VARCHAR(50) NOT NULL,
        name            VARCHAR(100) NOT NULL,
        description     TEXT,
        sort_order      INTEGER DEFAULT 0 NOT NULL,
        enabled         SMALLINT DEFAULT 1 NOT NULL,
        optional        SMALLINT DEFAULT 0 NOT NULL,
        default_skip    SMALLINT DEFAULT 0 NOT NULL
    );
    """)
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_pipeline_phases_code ON pipeline_phases(code);"
    )

    # ------------------------------------------------------------------
    # IMAGE_PHASE_STATUS — per-image per-phase tracking
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS image_phase_status (
        id                  SERIAL PRIMARY KEY,
        image_id            INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
        phase_id            INTEGER NOT NULL REFERENCES pipeline_phases(id),
        status              VARCHAR(20) DEFAULT 'not_started' NOT NULL,
        executor_version    VARCHAR(50),
        app_version         VARCHAR(50),
        job_id              INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
        attempt_count       SMALLINT DEFAULT 0 NOT NULL,
        last_error          TEXT,
        started_at          TIMESTAMP,
        finished_at         TIMESTAMP,
        updated_at          TIMESTAMP,
        skip_reason         TEXT,
        skipped_by          VARCHAR(255),
        CONSTRAINT ck_image_phase_status_status CHECK (status IN (
            'not_started', 'queued', 'running', 'paused',
            'cancel_requested', 'restarting',
            'done', 'skipped', 'failed'
        ))
    );
    """)
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_image_phase ON image_phase_status(image_id, phase_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ips_image_id ON image_phase_status(image_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ips_phase_id ON image_phase_status(phase_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ips_status ON image_phase_status(status);"
    )

    # ------------------------------------------------------------------
    # IMAGE_INCIDENTS — append-only image-scoped failures / validations
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS image_incidents (
        id              SERIAL PRIMARY KEY,
        image_id        INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
        folder_id       INTEGER REFERENCES folders(id) ON DELETE SET NULL,
        job_id          INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
        phase_id        INTEGER REFERENCES pipeline_phases(id) ON DELETE SET NULL,
        kind            VARCHAR(32) NOT NULL,
        source          VARCHAR(128),
        message         TEXT NOT NULL,
        detail          JSONB,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_image_incidents_created_at "
        "ON image_incidents (created_at DESC);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_image_incidents_image_id ON image_incidents(image_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_image_incidents_folder_id ON image_incidents(folder_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_image_incidents_job_id ON image_incidents(job_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_image_incidents_kind ON image_incidents(kind);"
    )

    # ------------------------------------------------------------------
    # STACK_CACHE — pre-computed score aggregates per stack
    # (created by Electron but defined here for Postgres parity)
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS stack_cache (
        stack_id                INTEGER NOT NULL PRIMARY KEY REFERENCES stacks(id) ON DELETE CASCADE,
        image_count             INTEGER DEFAULT 0,
        rep_image_id            INTEGER REFERENCES images(id) ON DELETE SET NULL,
        min_score_general       DOUBLE PRECISION,
        max_score_general       DOUBLE PRECISION,
        min_score_technical     DOUBLE PRECISION,
        max_score_technical     DOUBLE PRECISION,
        min_score_aesthetic     DOUBLE PRECISION,
        max_score_aesthetic     DOUBLE PRECISION,
        min_score_spaq          DOUBLE PRECISION,
        max_score_spaq          DOUBLE PRECISION,
        min_score_ava           DOUBLE PRECISION,
        max_score_ava           DOUBLE PRECISION,
        min_score_liqe          DOUBLE PRECISION,
        max_score_liqe          DOUBLE PRECISION,
        min_rating              INTEGER,
        max_rating              INTEGER,
        min_created_at          TIMESTAMP,
        max_created_at          TIMESTAMP,
        folder_id               INTEGER REFERENCES folders(id) ON DELETE SET NULL
    );
    """)

    # ------------------------------------------------------------------
    # KEYWORDS_DIM — normalized keyword dictionary
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS keywords_dim (
        keyword_id      SERIAL PRIMARY KEY,
        keyword_norm    VARCHAR(200) NOT NULL,
        keyword_display VARCHAR(200),
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_keywords_dim_norm ON keywords_dim(keyword_norm);"
    )

    # ------------------------------------------------------------------
    # IMAGE_KEYWORDS — many-to-many junction (image <-> keyword)
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS image_keywords (
        image_id    INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
        keyword_id  INTEGER NOT NULL REFERENCES keywords_dim(keyword_id) ON DELETE CASCADE,
        source      VARCHAR(128) DEFAULT 'auto',
        confidence  DOUBLE PRECISION,
        relevance_weight DOUBLE PRECISION NOT NULL DEFAULT 1.0,
        created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (image_id, keyword_id)
    );
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_imgkw_image_id ON image_keywords(image_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_imgkw_keyword_id ON image_keywords(keyword_id);"
    )
    try:
        cur.execute("ALTER TABLE image_keywords ALTER COLUMN source TYPE VARCHAR(128)")
    except Exception as e:
        logger.debug("image_keywords.source widen (optional): %s", e)
    try:
        cur.execute(
            "ALTER TABLE image_keywords ADD COLUMN IF NOT EXISTS relevance_weight "
            "DOUBLE PRECISION NOT NULL DEFAULT 1.0"
        )
    except Exception as e:
        logger.debug("image_keywords.relevance_weight add (optional): %s", e)
