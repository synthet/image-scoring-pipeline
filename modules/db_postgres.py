import logging
import os
import re
import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
from pgvector.psycopg2 import register_vector
import datetime
import json
from modules import config

logger = logging.getLogger(__name__)

_pool = None

def get_pg_config():
    db_config = config.get_config_section("database") or {}
    pg = db_config.get("postgres", {})
    return {
        "host": os.environ.get("POSTGRES_HOST", pg.get("host", "127.0.0.1")),
        "port": int(os.environ.get("POSTGRES_PORT", pg.get("port", 5432))),
        "dbname": os.environ.get("POSTGRES_DB", pg.get("dbname", "image_scoring")),
        "user": os.environ.get("POSTGRES_USER", pg.get("user", "postgres")),
        "password": os.environ.get("POSTGRES_PASSWORD", pg.get("password", "postgres")),
    }

def init_pool():
    global _pool
    if _pool is None:
        cfg = get_pg_config()
        try:
            _pool = ThreadedConnectionPool(
                1, 20,
                host=cfg["host"],
                port=cfg["port"],
                dbname=cfg["dbname"],
                user=cfg["user"],
                password=cfg["password"]
            )
            logger.info("PostgreSQL connection pool initialized.")
        except Exception as e:
            logger.error("Failed to initialize PostgreSQL connection pool: %s", e)

def get_pg_connection():
    global _pool
    if _pool is None:
        init_pool()
    if _pool:
        conn = _pool.getconn()
        try:
            register_vector(conn)
        except Exception as e:
            logger.warning("Failed to register pgvector on connection: %s", e)
        return conn
    raise Exception("PostgreSQL connection pool is not initialized")

def release_pg_connection(conn):
    global _pool
    if _pool and conn:
        _pool.putconn(conn)


def close_pool():
    """Close all pooled connections and drop the pool (e.g. after POSTGRES_DB or host changes)."""
    global _pool
    if _pool is not None:
        try:
            _pool.closeall()
        except Exception as e:
            logger.warning("Error while closing PostgreSQL pool: %s", e)
        finally:
            _pool = None


def reset_pool():
    """Alias for :func:`close_pool` (tests and fixtures)."""
    close_pool()


# Application tables for bulk TRUNCATE (CASCADE handles FK order).
def _quoted_db_identifier(name: str) -> str:
    """Quote a database name for DDL. Only allows safe unquoted-style identifiers."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
        raise ValueError(f"Refusing CREATE DATABASE for unsafe name: {name!r}")
    return '"' + name.replace('"', '""') + '"'


POSTGRES_APP_TABLES = (
    "jobs",
    "folders",
    "stacks",
    "images",
    "file_paths",
    "job_phases",
    "job_steps",
    "image_exif",
    "image_xmp",
    "cluster_progress",
    "culling_sessions",
    "culling_picks",
    "pipeline_phases",
    "image_phase_status",
    "stack_cache",
    "keywords_dim",
    "image_keywords",
)


def ensure_database_exists(dbname: str, admin_dbname: str = "postgres") -> None:
    """
    Create database ``dbname`` if missing. Uses host/port/user/password from
    config and env (same as :func:`get_pg_config`), but connects to ``admin_dbname``
    for the CREATE DATABASE statement.
    """
    db_config = config.get_config_section("database") or {}
    pg = db_config.get("postgres", {})
    host = os.environ.get("POSTGRES_HOST", pg.get("host", "127.0.0.1"))
    port = int(os.environ.get("POSTGRES_PORT", pg.get("port", 5432)))
    user = os.environ.get("POSTGRES_USER", pg.get("user", "postgres"))
    password = os.environ.get("POSTGRES_PASSWORD", pg.get("password", "postgres"))
    conn = psycopg2.connect(
        host=host,
        port=port,
        dbname=admin_dbname,
        user=user,
        password=password,
        options="-c client_encoding=UTF8",
    )
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,))
            if cur.fetchone():
                return
            cur.execute(f"CREATE DATABASE {_quoted_db_identifier(dbname)}")
            logger.info("Created PostgreSQL database %s", dbname)
    finally:
        conn.close()


def truncate_app_tables() -> None:
    """TRUNCATE all application tables and restart sequences (uses current pool)."""
    table_list = ", ".join(POSTGRES_APP_TABLES)
    with PGConnectionManager(commit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f"TRUNCATE {table_list} RESTART IDENTITY CASCADE")


class PGConnectionManager:
    """Context manager for PostgreSQL connections from the pool."""
    def __init__(self, commit=False):
        self.commit = commit
        self.conn = None

    def __enter__(self):
        self.conn = get_pg_connection()
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.conn:
            if exc_type is None and self.commit:
                self.conn.commit()
            elif exc_type is not None:
                self.conn.rollback()
            release_pg_connection(self.conn)

def execute_select(sql: str, params=None) -> list[dict]:
    """Execute a (pre-translated) SELECT on PostgreSQL and return a list of dicts."""
    with PGConnectionManager() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]


def execute_select_one(sql: str, params=None) -> "dict | None":
    """Execute a SELECT and return the first row as a dict, or None."""
    rows = execute_select(sql, params)
    return rows[0] if rows else None


def execute_write(sql: str, params=None) -> int:
    """Execute INSERT/UPDATE/DELETE on PostgreSQL and return rowcount."""
    with PGConnectionManager(commit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount


def execute_write_returning(sql: str, params=None) -> "dict | None":
    """Execute INSERT/UPDATE ... RETURNING on PostgreSQL, return first row as dict."""
    with PGConnectionManager(commit=True) as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None


def init_db():
    """Initialize PostgreSQL database schema (full parity with Firebird schema)."""
    with PGConnectionManager(commit=True) as conn:
        with conn.cursor() as cur:
            # Enable pgvector
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

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
                created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_folders_path ON folders(path);")

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
                runner_state        VARCHAR(50)
            );
            """)

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
            cur.execute("CREATE INDEX IF NOT EXISTS idx_job_phases_job_id ON job_phases(job_id);")

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
            # IMAGES  (full column set)
            # ------------------------------------------------------------------
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
                score_spaq          DOUBLE PRECISION,
                score_ava           DOUBLE PRECISION,
                score_koniq         DOUBLE PRECISION,
                score_paq2piq       DOUBLE PRECISION,
                score_liqe          DOUBLE PRECISION,
                keywords            TEXT,
                title               VARCHAR(500),
                description         TEXT,
                metadata            TEXT,
                thumbnail_path      VARCHAR(4000),
                thumbnail_path_win  VARCHAR(4000),
                scores_json         TEXT,
                model_version       VARCHAR(50),
                rating              SMALLINT,
                label               VARCHAR(50),
                image_hash          VARCHAR(64),
                folder_id           INTEGER REFERENCES folders(id) ON DELETE SET NULL,
                stack_id            INTEGER REFERENCES stacks(id) ON DELETE SET NULL,
                burst_uuid          VARCHAR(64),
                cull_decision       VARCHAR(20),
                cull_policy_version VARCHAR(50),
                image_uuid          VARCHAR(36),
                created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                image_embedding     vector(1280)
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_images_folder_id ON images(folder_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_images_stack_id ON images(stack_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_images_hash ON images(image_hash);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_images_burst_uuid ON images(burst_uuid);")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_images_image_uuid ON images(image_uuid) WHERE image_uuid IS NOT NULL;")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_images_file_path ON images(file_path);")
            # HNSW cosine index for fast similarity search
            cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_images_embedding_hnsw
              ON images USING hnsw (image_embedding vector_cosine_ops);
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
            cur.execute("CREATE INDEX IF NOT EXISTS idx_file_paths_img_type ON file_paths(image_id, path_type);")

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
            cur.execute("CREATE INDEX IF NOT EXISTS idx_culling_picks_session ON culling_picks(session_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_culling_picks_image ON culling_picks(image_id);")

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
                extracted_at            TIMESTAMP
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_exif_date ON image_exif(date_time_original);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_exif_make ON image_exif(make);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_exif_model ON image_exif(model);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_exif_lens ON image_exif(lens_model);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_exif_iso ON image_exif(iso);")

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
                create_date     TIMESTAMP,
                modify_date     TIMESTAMP,
                extracted_at    TIMESTAMP
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_xmp_burst ON image_xmp(burst_uuid);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_xmp_pick ON image_xmp(pick_status);")

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
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_pipeline_phases_code ON pipeline_phases(code);")

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
                skipped_by          VARCHAR(255)
            );
            """)
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_image_phase ON image_phase_status(image_id, phase_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ips_image_id ON image_phase_status(image_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ips_phase_id ON image_phase_status(phase_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ips_status ON image_phase_status(status);")

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
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_keywords_dim_norm ON keywords_dim(keyword_norm);")

            # ------------------------------------------------------------------
            # IMAGE_KEYWORDS — many-to-many junction (image <-> keyword)
            # ------------------------------------------------------------------
            cur.execute("""
            CREATE TABLE IF NOT EXISTS image_keywords (
                image_id    INTEGER NOT NULL REFERENCES images(id) ON DELETE CASCADE,
                keyword_id  INTEGER NOT NULL REFERENCES keywords_dim(keyword_id) ON DELETE CASCADE,
                source      VARCHAR(20) DEFAULT 'auto',
                confidence  DOUBLE PRECISION,
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (image_id, keyword_id)
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_imgkw_image_id ON image_keywords(image_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_imgkw_keyword_id ON image_keywords(keyword_id);")

            logger.info("PostgreSQL schema initialization completed.")
