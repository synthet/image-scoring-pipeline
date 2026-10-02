"""PostgreSQL embedding registries, vector tables, and model-score storage."""


def initialize_embedding_schema(
    cur,
    *,
    default_embedding_space_sql: str,
    extra_embedding_spaces_sql: tuple[str, ...] | list[str],
) -> None:
    # ------------------------------------------------------------------
    # EMBEDDING_SPACES — registry of vector kinds (fixed dim per row)
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS embedding_spaces (
        id              SERIAL PRIMARY KEY,
        code            VARCHAR(64) NOT NULL,
        dim             INTEGER NOT NULL,
        description     TEXT,
        active          SMALLINT DEFAULT 1 NOT NULL,
        created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    cur.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_embedding_spaces_code ON embedding_spaces(code);"
    )

    # ------------------------------------------------------------------
    # IMAGE_EMBEDDINGS — one row per (image, space); vector(1280) for 1280-d spaces only
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS image_embeddings (
        id                      SERIAL PRIMARY KEY,
        image_id                INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
        embedding_space_id      INTEGER NOT NULL REFERENCES embedding_spaces(id) ON DELETE CASCADE,
        embedding               vector(1280) NOT NULL,
        model_version           VARCHAR(64),
        updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (image_id, embedding_space_id)
    );
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_image_embeddings_image ON image_embeddings(image_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_image_embeddings_space ON image_embeddings(embedding_space_id);"
    )
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_image_embeddings_hnsw
      ON image_embeddings USING hnsw (embedding vector_cosine_ops);
    """)

    # ------------------------------------------------------------------
    # IMAGE_EMBEDDINGS_512 — 512-d spaces (CLIP, BioCLIP image towers)
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS image_embeddings_512 (
        id                      SERIAL PRIMARY KEY,
        image_id                INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
        embedding_space_id      INTEGER NOT NULL REFERENCES embedding_spaces(id) ON DELETE CASCADE,
        embedding               vector(512) NOT NULL,
        model_version           VARCHAR(64),
        updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (image_id, embedding_space_id)
    );
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_image_embeddings_512_image ON image_embeddings_512(image_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_image_embeddings_512_space ON image_embeddings_512(embedding_space_id);"
    )
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_image_embeddings_512_hnsw
      ON image_embeddings_512 USING hnsw (embedding vector_cosine_ops);
    """)

    # ------------------------------------------------------------------
    # IMAGE_EMBEDDINGS_768 — 768-d spaces (BLIP vision encoder)
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS image_embeddings_768 (
        id                      SERIAL PRIMARY KEY,
        image_id                INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
        embedding_space_id      INTEGER NOT NULL REFERENCES embedding_spaces(id) ON DELETE CASCADE,
        embedding               vector(768) NOT NULL,
        model_version           VARCHAR(64),
        updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        UNIQUE (image_id, embedding_space_id)
    );
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_image_embeddings_768_image ON image_embeddings_768(image_id);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_image_embeddings_768_space ON image_embeddings_768(embedding_space_id);"
    )
    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_image_embeddings_768_hnsw
      ON image_embeddings_768 USING hnsw (embedding vector_cosine_ops);
    """)

    cur.execute(default_embedding_space_sql)
    for extra_sql in extra_embedding_spaces_sql:
        cur.execute(extra_sql)

    # ------------------------------------------------------------------
    # IMAGE_MODEL_SCORES — generic per-(image, model) score storage.
    # Mirrors migration 0016. This is now the sole persistence for
    # per-model scores (spaq/ava/koniq/paq2piq/liqe and any newer
    # model); the typed ``images.score_<name>`` columns have been
    # dropped.
    # ------------------------------------------------------------------
    cur.execute("""
    CREATE TABLE IF NOT EXISTS image_model_scores (
        image_id        INTEGER     NOT NULL REFERENCES images(id) ON DELETE CASCADE,
        model_name      VARCHAR(64) NOT NULL,
        raw_score       DOUBLE PRECISION,
        normalized      DOUBLE PRECISION,
        status          VARCHAR(16) NOT NULL,
        is_shadow       BOOLEAN     NOT NULL DEFAULT FALSE,
        model_version   VARCHAR(64),
        scored_at       TIMESTAMP   NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY (image_id, model_name)
    );
    """)
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ims_model_name ON image_model_scores(model_name);"
    )
    cur.execute(
        "CREATE INDEX IF NOT EXISTS idx_ims_shadow ON image_model_scores(is_shadow) "
        "WHERE is_shadow;"
    )
    cur.execute(
        "ALTER TABLE image_model_scores DROP CONSTRAINT IF EXISTS image_model_scores_status_check;"
    )
    cur.execute(
        "ALTER TABLE image_model_scores ADD CONSTRAINT image_model_scores_status_check "
        "CHECK (status IN ('success', 'failed', 'not_loaded'));"
    )

    cur.execute("""
    CREATE TABLE IF NOT EXISTS image_technical_failures (
        image_id                INTEGER NOT NULL PRIMARY KEY
            REFERENCES images(id) ON DELETE CASCADE,
        technical_failure_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        primary_reject_reason   VARCHAR(128) NOT NULL DEFAULT 'none',
        blur                    DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        overexposed             DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        underexposed            DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        highlight_clipping      DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        shadow_crushing         DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Back-fill FK on stacks.best_image_id now that images exists
    # (Firebird adds this as a separate alter; we declare it inline above for stacks
    #  but stacks was created before images — add it as a constraint now)
    cur.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.table_constraints
            WHERE constraint_name = 'fk_stacks_best_image'
        ) THEN
            ALTER TABLE stacks
              ADD CONSTRAINT fk_stacks_best_image
              FOREIGN KEY (best_image_id) REFERENCES images(id) ON DELETE SET NULL;
        END IF;
    END$$;
    """)
