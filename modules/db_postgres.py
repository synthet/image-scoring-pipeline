import logging
import os
import re
import sys

import psycopg2
import psycopg2.extras
from pgvector.psycopg2 import register_vector
from psycopg2.pool import ThreadedConnectionPool

from modules import config
from modules.db_schema import initialize_schema
from modules.test_db_constants import (
    POSTGRES_PRODUCTION_IN_PYTEST_ENV,
    POSTGRES_PRODUCTION_PYTEST_RISK_ACCEPTED_ENV,
    POSTGRES_TEST_DB,
    postgres_production_allowed_in_pytest,
)

logger = logging.getLogger(__name__)

_pool = None

_warned_production_pytest_incomplete = False


def _pytest_active() -> bool:
    return "pytest" in sys.modules or bool(os.environ.get("PYTEST_CURRENT_TEST"))


def _env_truthy(key: str) -> bool:
    return os.environ.get(key, "").strip().lower() in ("1", "true", "yes")


def get_pg_config():
    global _warned_production_pytest_incomplete
    db_config = config.get_config_section("database") or {}
    pg = db_config.get("postgres", {})
    config_dbname = pg.get("dbname", "image_scoring")
    if "POSTGRES_DB" in os.environ:
        dbname = os.environ["POSTGRES_DB"]
    else:
        dbname = config_dbname

    if _pytest_active():
        if postgres_production_allowed_in_pytest():
            pass  # keep dbname from POSTGRES_DB / config above
        else:
            if _env_truthy(POSTGRES_PRODUCTION_IN_PYTEST_ENV) and not _env_truthy(
                POSTGRES_PRODUCTION_PYTEST_RISK_ACCEPTED_ENV
            ):
                if not _warned_production_pytest_incomplete:
                    logger.warning(
                        "%s is set but pytest still uses %r unless %s is also set (dangerous).",
                        POSTGRES_PRODUCTION_IN_PYTEST_ENV,
                        POSTGRES_TEST_DB,
                        POSTGRES_PRODUCTION_PYTEST_RISK_ACCEPTED_ENV,
                    )
                    _warned_production_pytest_incomplete = True
            dbname = POSTGRES_TEST_DB
    return {
        "host": os.environ.get("POSTGRES_HOST", pg.get("host", "127.0.0.1")),
        "port": int(os.environ.get("POSTGRES_PORT", pg.get("port", 5432))),
        "dbname": dbname,
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
    "image_embeddings_768",
    "image_embeddings_512",
    "image_embeddings",
    "embedding_spaces",
    "images",
    "file_paths",
    "job_phases",
    "job_steps",
    "job_image_actions",
    "image_phase_work_claims",
    "image_incidents",
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
    "deleted_images",
    # Localization artifacts (#370). CASCADE from `images` would clear these anyway,
    # but naming them keeps the list honest as the schema grows.
    "image_localization_runs",
    "image_regions",
    "image_keypoint_runs",
    "image_region_keypoints",
    # Scene route classifications (#412).
    "image_scene_labels",
)

# Default visual-embedding catalog row (re-applied after TRUNCATE in tests).
_SEED_DEFAULT_EMBEDDING_SPACE_SQL = """
            INSERT INTO embedding_spaces (code, dim, description, active)
            SELECT 'mobilenet_v2_imagenet_gap', 1280,
                   'MobileNetV2 ImageNet weights, GAP — visual similarity / culling', 1
            WHERE NOT EXISTS (SELECT 1 FROM embedding_spaces WHERE code = 'mobilenet_v2_imagenet_gap')
            """

# Additional embedding-space rows seeded alongside the default (CLIP/BioCLIP/BLIP
# image towers — see docs/technical/EMBEDDINGS.md and migrations 0012).
_SEED_EXTRA_EMBEDDING_SPACES_SQL = [
    (
        """
        INSERT INTO embedding_spaces (code, dim, description, active)
        SELECT 'clip_vit_b32_image', 512,
               'CLIP ViT-B/32 image tower (transformers) — tagging/similarity', 1
        WHERE NOT EXISTS (SELECT 1 FROM embedding_spaces WHERE code = 'clip_vit_b32_image')
        """
    ),
    (
        """
        INSERT INTO embedding_spaces (code, dim, description, active)
        SELECT 'bioclip_2_image', 768,
               'BioCLIP 2 image tower ViT-L/14 (open_clip) — bird/species similarity', 1
        WHERE NOT EXISTS (SELECT 1 FROM embedding_spaces WHERE code = 'bioclip_2_image')
        """
    ),
    (
        """
        INSERT INTO embedding_spaces (code, dim, description, active)
        SELECT 'blip_vit_b16_image', 768,
               'BLIP base vision encoder pooler_output — caption-aligned similarity', 1
        WHERE NOT EXISTS (SELECT 1 FROM embedding_spaces WHERE code = 'blip_vit_b16_image')
        """
    ),
    # Optional culling towers (2026-05-29 spike) — 768-d image embeddings,
    # opt-in via embeddings.culling_spaces; selectable per two-level level.
    (
        """
        INSERT INTO embedding_spaces (code, dim, description, active)
        SELECT 'openclip_l14_laion2b_image', 768,
               'OpenCLIP ViT-L/14 laion2b_s32b_b82k image tower — culling grouping (A/B)', 1
        WHERE NOT EXISTS (SELECT 1 FROM embedding_spaces WHERE code = 'openclip_l14_laion2b_image')
        """
    ),
    (
        """
        INSERT INTO embedding_spaces (code, dim, description, active)
        SELECT 'openai_clip_vit_l14_image', 768,
               'OpenAI CLIP ViT-L/14 image tower — culling grouping / semantic sub-stack', 1
        WHERE NOT EXISTS (SELECT 1 FROM embedding_spaces WHERE code = 'openai_clip_vit_l14_image')
        """
    ),
    (
        """
        INSERT INTO embedding_spaces (code, dim, description, active)
        SELECT 'dinov2_reg_base_image', 768,
               'DINOv2-reg base image tower (timm proxy) — culling grouping (HOLD)', 1
        WHERE NOT EXISTS (SELECT 1 FROM embedding_spaces WHERE code = 'dinov2_reg_base_image')
        """
    ),
    (
        """
        INSERT INTO embedding_spaces (code, dim, description, active)
        SELECT 'siglip2_base_image', 768,
               'SigLIP2 base patch16-224 image tower — culling grouping / keywords', 1
        WHERE NOT EXISTS (SELECT 1 FROM embedding_spaces WHERE code = 'siglip2_base_image')
        """
    ),
]


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
    cfg = get_pg_config()
    if cfg["dbname"] != POSTGRES_TEST_DB and not postgres_production_allowed_in_pytest():
        raise RuntimeError(
            f"truncate_app_tables refused: current PostgreSQL database is {cfg['dbname']!r}, "
            f"expected {POSTGRES_TEST_DB!r}. Under pytest, POSTGRES_DB and config dbname are ignored "
            f"unless both {POSTGRES_PRODUCTION_IN_PYTEST_ENV} and "
            f"{POSTGRES_PRODUCTION_PYTEST_RISK_ACCEPTED_ENV} are set."
        )
    from modules.phases import SEED_PHASES

    table_list = ", ".join(POSTGRES_APP_TABLES)
    # A reseed failure must raise, not be swallowed: an aborted transaction is rolled back
    # on exit, which silently undoes the TRUNCATE too (#399).
    with PGConnectionManager(commit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f"TRUNCATE {table_list} RESTART IDENTITY CASCADE")
            cur.execute(_SEED_DEFAULT_EMBEDDING_SPACE_SQL)
            for extra_sql in _SEED_EXTRA_EMBEDDING_SPACES_SQL:
                cur.execute(extra_sql)
            for phase in SEED_PHASES:
                code = phase["code"].value if hasattr(phase["code"], "value") else str(phase["code"])
                # enabled/optional/default_skip are SMALLINT — bind ints, not bools.
                cur.execute(
                    """
                    INSERT INTO pipeline_phases (code, name, description, sort_order, enabled, optional, default_skip)
                    VALUES (%s, %s, %s, %s, 1, %s, %s)
                    ON CONFLICT (code) DO UPDATE
                    SET optional = EXCLUDED.optional, default_skip = EXCLUDED.default_skip
                    """,
                    (
                        code,
                        phase["name"],
                        phase.get("description", ""),
                        int(phase["sort_order"]),
                        1 if phase.get("optional") else 0,
                        1 if phase.get("default_skip") else 0,
                    ),
                )


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
            try:
                if exc_type is None and self.commit:
                    self.conn.commit()
                else:
                    self.conn.rollback()
            except Exception:
                pass
            release_pg_connection(self.conn)

def is_deadlock_error(exc: BaseException) -> bool:
    """True when ``exc`` is a PostgreSQL deadlock (SQLSTATE 40P01)."""
    pgcode = getattr(exc, "pgcode", None)
    if pgcode == "40P01":
        return True
    return "deadlock detected" in str(exc).lower()


def run_with_deadlock_retry(fn, *, max_attempts: int = 4, op_name: str = "db op"):
    """Invoke ``fn`` with automatic retry on PostgreSQL deadlock (SQLSTATE 40P01).

    Each retry runs ``fn`` again from scratch (the failing transaction has
    already been rolled back by Postgres / the connection manager). Backoff is
    exponential with light jitter to break lock-order ties between racing
    workers.
    """
    import random
    import time

    from psycopg2 import DatabaseError

    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except DatabaseError as e:
            if not is_deadlock_error(e) or attempt == max_attempts:
                raise
            wait = min(2.0, 0.10 * (2 ** (attempt - 1))) + random.uniform(0, 0.10)
            logger.warning(
                "PostgreSQL deadlock during %s (attempt %d/%d), retrying in %.2fs: %s",
                op_name, attempt, max_attempts, wait, e,
            )
            time.sleep(wait)


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
    """Execute INSERT/UPDATE/DELETE on PostgreSQL and return rowcount.

    Retries automatically on SQLSTATE 40P01 (deadlock detected).
    """
    def _do() -> int:
        with PGConnectionManager(commit=True) as conn, conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.rowcount

    return run_with_deadlock_retry(_do, op_name="execute_write")


def execute_write_returning(sql: str, params=None) -> "dict | None":
    """Execute INSERT/UPDATE ... RETURNING on PostgreSQL, return first row as dict.

    Retries automatically on SQLSTATE 40P01 (deadlock detected).
    """
    def _do() -> "dict | None":
        with PGConnectionManager(commit=True) as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute(sql, params)
                row = cur.fetchone()
                return dict(row) if row else None

    return run_with_deadlock_retry(_do, op_name="execute_write_returning")


def init_db():
    """Initialize PostgreSQL database schema (full parity with Firebird schema)."""
    import time

    from psycopg2 import DatabaseError

    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        try:
            _init_db_transaction()
            return
        except DatabaseError as e:
            # DeadlockDetected subclasses DatabaseError, not OperationalError (psycopg2 2.9+).
            pgcode = getattr(e, "pgcode", None)
            is_deadlock = pgcode == "40P01" or "deadlock" in str(e).lower()
            if is_deadlock and attempt < max_attempts:
                wait = min(2.0, 0.25 * (2 ** (attempt - 1)))
                logger.warning(
                    "PostgreSQL schema init deadlock (attempt %s/%s), retrying in %.2fs: %s",
                    attempt,
                    max_attempts,
                    wait,
                    e,
                )
                time.sleep(wait)
                continue
            raise


def _init_db_transaction():
    """Run ordered DDL helpers in one transaction.

    :func:`init_db` owns deadlock retries; the domain helpers preserve the
    previous statement order and share this cursor and transaction.
    """
    with PGConnectionManager(commit=True) as conn:
        with conn.cursor() as cur:
            initialize_schema(
                cur,
                conn=conn,
                default_embedding_space_sql=_SEED_DEFAULT_EMBEDDING_SPACE_SQL,
                extra_embedding_spaces_sql=_SEED_EXTRA_EMBEDDING_SPACES_SQL,
            )

    logger.info("PostgreSQL schema initialization completed.")
