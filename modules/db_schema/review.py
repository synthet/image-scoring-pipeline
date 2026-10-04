"""PostgreSQL tombstone, audit, cull-review, localization, and scene-label schema."""


def initialize_review_schema(cur, *, conn) -> None:
    # ------------------------------------------------------------------
    # DELETED_IMAGES — tombstone rows when an images row is removed (Sync/Import/Backup)
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS deleted_images (
        id              SERIAL PRIMARY KEY,
        original_id     INTEGER,
        image_uuid      VARCHAR(36),
        image_hash      VARCHAR(64),
        file_name       VARCHAR(255),
        original_path   VARCHAR(4000),
        deleted_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_deleted_images_original_id ON deleted_images(original_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_deleted_images_uuid ON deleted_images(image_uuid) "
        "WHERE image_uuid IS NOT NULL;"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_deleted_images_hash ON deleted_images(image_hash) "
        "WHERE image_hash IS NOT NULL;"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_deleted_images_file_uuid ON deleted_images(file_name, image_uuid) "
        "WHERE image_uuid IS NOT NULL;"
    )
    cur.execute("""
    CREATE OR REPLACE FUNCTION trg_record_deleted_image_fn()
    RETURNS TRIGGER AS $$
    BEGIN
        INSERT INTO deleted_images (original_id, image_uuid, image_hash, file_name, original_path)
        VALUES (OLD.id, OLD.image_uuid, OLD.image_hash, OLD.file_name, OLD.file_path);
        RETURN OLD;
    END;
    $$ LANGUAGE plpgsql;
    """)
    cur.execute("DROP TRIGGER IF EXISTS trg_record_deleted_image ON images;")
    cur.execute("""
    CREATE TRIGGER trg_record_deleted_image
        BEFORE DELETE ON images
        FOR EACH ROW
        EXECUTE PROCEDURE trg_record_deleted_image_fn();
    """)

    # ------------------------------------------------------------------
    # AUDITLOG — RFC 6902 (JSON Patch) change records for critical writes
    # ------------------------------------------------------------------
    # One row per audited insert/update on a critical entity. ``patch`` is
    # an RFC 6902 op array (``add`` for inserts, ``replace`` for updates)
    # with a non-standard ``oldValue`` on replaces for debugging. Written
    # by ``modules/audit.py``; see migration 0027.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS auditlog (
        id              BIGSERIAL PRIMARY KEY,
        table_name      VARCHAR(64) NOT NULL,
        record_id       BIGINT,
        operation       VARCHAR(16) NOT NULL,
        patch           JSONB NOT NULL,
        thread_name     VARCHAR(128),
        run_id          BIGINT,
        phase_code      VARCHAR(50),
        source          VARCHAR(128),
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_auditlog_table_record ON auditlog(table_name, record_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_auditlog_run_id ON auditlog(run_id) WHERE run_id IS NOT NULL;"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_auditlog_created_at ON auditlog(created_at);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_auditlog_thread_name ON auditlog(thread_name);"
    )

    # ------------------------------------------------------------------
    # Agent-assisted cull review (metadata-only removal candidates)
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS agent_cull_review_groups (
        id                      BIGSERIAL PRIMARY KEY,
        stack_id                INTEGER NOT NULL REFERENCES stacks(id) ON DELETE CASCADE,
        sub_stack_id            INTEGER REFERENCES sub_stacks(id) ON DELETE SET NULL,
        review_unit_key         VARCHAR(128) NOT NULL,
        status                  VARCHAR(32) NOT NULL DEFAULT 'discovered',
        dry_run                 BOOLEAN NOT NULL DEFAULT TRUE,
        agent_name              VARCHAR(64),
        agent_model             VARCHAR(128),
        agent_version           VARCHAR(64),
        agent_supports_vision   BOOLEAN,
        prompt_template_version VARCHAR(64),
        prompt_hash             VARCHAR(64),
        request_json            JSONB,
        response_raw            TEXT,
        response_validated      JSONB,
        group_decision          VARCHAR(32),
        group_confidence        DOUBLE PRECISION,
        summary                 TEXT,
        safety_overrides        JSONB,
        error_code              VARCHAR(64),
        error_message           TEXT,
        created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        applied_at              TIMESTAMP,
        applied_by              VARCHAR(128)
    );
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_cull_groups_unit_created "
        "ON agent_cull_review_groups(review_unit_key, created_at);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_cull_groups_stack_status "
        "ON agent_cull_review_groups(stack_id, sub_stack_id, status);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_cull_groups_status_created "
        "ON agent_cull_review_groups(status, created_at);"
    )
    try:
        cur.execute(
            "ALTER TABLE agent_cull_review_groups "
            "ALTER COLUMN prompt_template_version TYPE VARCHAR(64)"
        )
        conn.commit()
    except Exception:
        conn.rollback()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS agent_cull_recommendations (
        id                      BIGSERIAL PRIMARY KEY,
        review_group_id         BIGINT NOT NULL REFERENCES agent_cull_review_groups(id) ON DELETE CASCADE,
        image_id                INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
        agent_decision          VARCHAR(16) NOT NULL,
        final_decision          VARCHAR(16) NOT NULL,
        confidence              DOUBLE PRECISION,
        reason                  TEXT,
        better_alternatives     JSONB,
        risk_flags              JSONB,
        safety_overrides        JSONB,
        candidate_status        VARCHAR(32) NOT NULL DEFAULT 'none',
        prior_pick_status       SMALLINT,
        prior_cull_decision     VARCHAR(20),
        prior_candidate_status  VARCHAR(32),
        operator_actor          VARCHAR(128),
        operator_note           TEXT,
        operator_at             TIMESTAMP
    );
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_cull_recs_group "
        "ON agent_cull_recommendations(review_group_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_cull_recs_image_status "
        "ON agent_cull_recommendations(image_id, candidate_status);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_agent_cull_recs_status_image "
        "ON agent_cull_recommendations(candidate_status, image_id);"
    )

    # --- Normalized localization artifacts (rollout stage 2, #370) ------------
    # Mirrors migrations/versions/0034_image_localization.py, which carries the
    # design rationale. Dormant: nothing writes these yet and images.bird_bbox
    # remains the sole authority until localization.read_normalized_first flips.
    #
    # One run row per *attempt*, written even when zero regions are found -- that
    # is what makes `no_detection` a versioned observation rather than an absence.
    # An empty image_regions set therefore has no standalone meaning.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS image_localization_runs (
        id                      BIGSERIAL PRIMARY KEY,
        image_id                INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
        job_id                  INTEGER,
        detector_key            TEXT NOT NULL,
        detector_version        TEXT NOT NULL,
        detector_config_hash    TEXT NOT NULL,
        source_hash             TEXT,
        source_hash_version     TEXT,
        rendition_hash          TEXT,
        rendition_version       TEXT,
        coord_space             TEXT NOT NULL DEFAULT 'display_normalized',
        orientation             SMALLINT,
        display_width           INTEGER,
        display_height          INTEGER,
        status                  TEXT NOT NULL,
        is_retryable            BOOLEAN NOT NULL DEFAULT FALSE,
        error_code              TEXT,
        error_detail            TEXT,
        is_current              BOOLEAN NOT NULL DEFAULT FALSE,
        legacy_payload          JSONB,
        attempted_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        started_at              TIMESTAMP,
        completed_at            TIMESTAMP,
        created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT ck_ilr_status CHECK (status IN (
            'detected', 'no_detection', 'retryable_error', 'terminal_error', 'disabled'
        )),
        CONSTRAINT ck_ilr_orientation CHECK (
            orientation IS NULL OR orientation BETWEEN 1 AND 8
        ),
        CONSTRAINT ck_ilr_dimensions CHECK (
            (display_width IS NULL OR display_width > 0)
            AND (display_height IS NULL OR display_height > 0)
        )
    );
    """)
    # Partial unique index: the hot lookup for the compatibility reader, and the
    # enforcement of "at most one current attempt per (image, detector)".
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_ilr_current_image_detector "
        "ON image_localization_runs (image_id, detector_key) WHERE is_current;"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS ix_ilr_image_attempted "
        "ON image_localization_runs (image_id, attempted_at DESC);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS ix_ilr_status_detector "
        "ON image_localization_runs (status, detector_key, detector_version);"
    )
    # Mirrors migrations/versions/0035_localization_decode_route.py (#387 AC-20).
    cur.execute(
        "ALTER TABLE image_localization_runs ADD COLUMN IF NOT EXISTS decode_route TEXT;"
    )
    cur.execute("""
    CREATE TABLE IF NOT EXISTS image_regions (
        id                  BIGSERIAL PRIMARY KEY,
        localization_run_id BIGINT NOT NULL
                            REFERENCES image_localization_runs(id) ON DELETE CASCADE,
        object_class        TEXT NOT NULL,
        provider_class_id   TEXT,
        confidence          DOUBLE PRECISION,
        rank                INTEGER NOT NULL,
        x1                  DOUBLE PRECISION NOT NULL,
        y1                  DOUBLE PRECISION NOT NULL,
        x2                  DOUBLE PRECISION NOT NULL,
        y2                  DOUBLE PRECISION NOT NULL,
        geometry_hash       TEXT,
        created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT ck_ir_range CHECK (x1 >= 0 AND y1 >= 0 AND x2 <= 1 AND y2 <= 1),
        CONSTRAINT ck_ir_ordered CHECK (x2 > x1 AND y2 > y1),
        CONSTRAINT ck_ir_confidence CHECK (
            confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
        ),
        CONSTRAINT ck_ir_rank CHECK (rank >= 0),
        CONSTRAINT ux_ir_run_class_rank UNIQUE (localization_run_id, object_class, rank)
    );
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS ix_ir_run_rank "
        "ON image_regions (localization_run_id, rank);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS ix_ir_class_confidence "
        "ON image_regions (object_class, confidence DESC);"
    )

    # Region-linked keypoints (#426). Mirrors migrations/versions/0036_region_keypoints.py.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS image_keypoint_runs (
        id                    BIGSERIAL PRIMARY KEY,
        region_id             BIGINT NOT NULL REFERENCES image_regions(id) ON DELETE CASCADE,
        provider_key          TEXT NOT NULL,
        provider_version      TEXT NOT NULL,
        provider_config_hash  TEXT NOT NULL,
        pass                  TEXT NOT NULL,
        status                TEXT NOT NULL,
        error_code            TEXT,
        error_detail          TEXT,
        is_current            BOOLEAN NOT NULL DEFAULT FALSE,
        created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        CONSTRAINT ck_ikr_status CHECK (status IN (
            'detected', 'no_keypoints', 'retryable_error', 'terminal_error'
        ))
    );
    """)
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_ikr_current_region_provider "
        "ON image_keypoint_runs (region_id, provider_key) WHERE is_current;"
    )
    cur.execute("""
    CREATE TABLE IF NOT EXISTS image_region_keypoints (
        id               BIGSERIAL PRIMARY KEY,
        keypoint_run_id  BIGINT NOT NULL REFERENCES image_keypoint_runs(id) ON DELETE CASCADE,
        name             TEXT NOT NULL,
        x                DOUBLE PRECISION NOT NULL,
        y                DOUBLE PRECISION NOT NULL,
        confidence       DOUBLE PRECISION,
        visible          BOOLEAN NOT NULL,
        CONSTRAINT ck_irk_range CHECK (x >= 0 AND x <= 1 AND y >= 0 AND y <= 1),
        CONSTRAINT ck_irk_confidence CHECK (
            confidence IS NULL OR (confidence >= 0 AND confidence <= 1)
        ),
        CONSTRAINT ux_irk_run_name UNIQUE (keypoint_run_id, name)
    );
    """)

    # Production localization selections (#484). Mirrors
    # migrations/versions/0038_localization_selections.py, which carries the rationale:
    # a revocable decision that one region is the production answer; images.bird_bbox
    # becomes its projection for selected images.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS image_localization_selections (
        id                    BIGSERIAL PRIMARY KEY,
        image_id              INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
        detector_key          TEXT NOT NULL,
        localization_run_id   BIGINT NOT NULL
                              REFERENCES image_localization_runs(id) ON DELETE CASCADE,
        region_id             BIGINT NOT NULL REFERENCES image_regions(id) ON DELETE CASCADE,
        selected_by           TEXT NOT NULL,
        evidence              JSONB,
        previous_bird_bbox    JSONB,
        projected_bird_bbox   JSONB NOT NULL,
        selected_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        revoked_at            TIMESTAMP,
        revoked_reason        TEXT
    );
    """)
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_ils_active_image_detector "
        "ON image_localization_selections (image_id, detector_key) WHERE revoked_at IS NULL;"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS ix_ils_selected_by "
        "ON image_localization_selections (selected_by, selected_at);"
    )

    # Localization enablement boundary (#527). Mirrors
    # migrations/versions/0039_localization_enablement.py: images indexed at or after
    # enabled_at are "new"; the row is written on first enabled use, never seeded here.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS localization_enablement (
        detector_key  TEXT PRIMARY KEY,
        enabled_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Scene route classifications (#412). Mirrors migrations/versions/0037_image_scene_labels.py.
    cur.execute("""
    CREATE TABLE IF NOT EXISTS image_scene_labels (
        image_id        INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
        scene_version   TEXT NOT NULL,
        backend         TEXT NOT NULL,
        top_label       TEXT NOT NULL,
        top_prob        DOUBLE PRECISION NOT NULL,
        probs           JSONB NOT NULL,
        cosines         JSONB,
        rendition_hash  TEXT,
        job_id          INTEGER,
        created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (image_id, scene_version),
        CONSTRAINT ck_isl_top_prob CHECK (top_prob >= 0 AND top_prob <= 1)
    );
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS ix_isl_version_label "
        "ON image_scene_labels (scene_version, top_label);"
    )
