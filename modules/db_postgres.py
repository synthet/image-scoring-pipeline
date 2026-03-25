import logging
import os
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
    db_config = config.get_config_section("database")
    # Provide defaults
    return {
        "host": db_config.get("postgres", {}).get("host", "127.0.0.1"),
        "port": db_config.get("postgres", {}).get("port", 5432),
        "dbname": db_config.get("postgres", {}).get("dbname", "musiq"),
        "user": db_config.get("postgres", {}).get("user", "musiq"),
        "password": db_config.get("postgres", {}).get("password", "musiq"),
    }


def init_pool():
    global _pool
    if _pool is None:
        cfg = get_pg_config()
        # Create a connection pool (min 1, max 20 connections)
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


def init_db():
    """Initialize PostgreSQL database schema used by runtime and migration."""
    with PGConnectionManager(commit=True) as conn:
        with conn.cursor() as cur:
            # Enable pgvector
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")

            # FOLDERS
            cur.execute("""
            CREATE TABLE IF NOT EXISTS folders (
                id SERIAL PRIMARY KEY,
                path VARCHAR(4000),
                parent_id INTEGER,
                is_fully_scored SMALLINT DEFAULT 0,
                is_keywords_processed SMALLINT DEFAULT 0,
                phase_agg_dirty SMALLINT DEFAULT 1,
                phase_agg_updated_at TIMESTAMP,
                phase_agg_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # STACKS
            cur.execute("""
            CREATE TABLE IF NOT EXISTS stacks (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255),
                best_image_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # JOBS
            cur.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id SERIAL PRIMARY KEY,
                input_path VARCHAR(4000),
                phase_id INTEGER,
                job_type VARCHAR(50),
                status VARCHAR(50),
                priority SMALLINT DEFAULT 100,
                retry_count INTEGER DEFAULT 0,
                target_scope VARCHAR(255),
                paused_at TIMESTAMP,
                queue_position INTEGER,
                cancel_requested SMALLINT DEFAULT 0,
                queue_payload TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                enqueued_at TIMESTAMP,
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                completed_at TIMESTAMP,
                log TEXT,
                current_phase VARCHAR(50),
                next_phase_index INTEGER,
                runner_state VARCHAR(50),
                scope_type VARCHAR(30),
                scope_paths TEXT
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_phase_id ON jobs(phase_id);")

            # IMAGES
            cur.execute("""
            CREATE TABLE IF NOT EXISTS images (
                id SERIAL PRIMARY KEY,
                job_id INTEGER,
                file_path VARCHAR(4000),
                file_name VARCHAR(255),
                file_type VARCHAR(20),
                score DOUBLE PRECISION,
                score_general DOUBLE PRECISION,
                score_technical DOUBLE PRECISION,
                score_aesthetic DOUBLE PRECISION,
                score_spaq DOUBLE PRECISION,
                score_ava DOUBLE PRECISION,
                score_koniq DOUBLE PRECISION,
                score_paq2piq DOUBLE PRECISION,
                score_liqe DOUBLE PRECISION,
                keywords TEXT,
                title VARCHAR(500),
                description TEXT,
                metadata TEXT,
                thumbnail_path VARCHAR(4000),
                scores_json TEXT,
                model_version VARCHAR(50),
                rating SMALLINT,
                label VARCHAR(50),
                image_hash VARCHAR(64),
                folder_id INTEGER,
                stack_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                burst_uuid VARCHAR(64),
                image_embedding vector(1280)
            );
            """)

            # FILE_PATHS
            cur.execute("""
            CREATE TABLE IF NOT EXISTS file_paths (
                id SERIAL PRIMARY KEY,
                image_id INTEGER,
                path VARCHAR(4000),
                last_seen TIMESTAMP,
                path_type VARCHAR(10),
                is_verified SMALLINT,
                verification_date TIMESTAMP
            );
            """)

            # IMAGE_EXIF
            cur.execute("""
            CREATE TABLE IF NOT EXISTS image_exif (
                image_id INTEGER PRIMARY KEY,
                make VARCHAR(100),
                model VARCHAR(200),
                lens_model VARCHAR(255),
                focal_length VARCHAR(50),
                focal_length_35mm SMALLINT,
                date_time_original TIMESTAMP,
                create_date TIMESTAMP,
                exposure_time VARCHAR(30),
                f_number VARCHAR(20),
                iso INTEGER,
                exposure_compensation VARCHAR(20),
                image_width INTEGER,
                image_height INTEGER,
                orientation SMALLINT,
                flash SMALLINT,
                image_unique_id VARCHAR(64),
                shutter_count INTEGER,
                sub_sec_time_original VARCHAR(10),
                extracted_at TIMESTAMP
            );
            """)

            # IMAGE_XMP
            cur.execute("""
            CREATE TABLE IF NOT EXISTS image_xmp (
                image_id INTEGER PRIMARY KEY,
                rating SMALLINT,
                label VARCHAR(50),
                pick_status SMALLINT,
                burst_uuid VARCHAR(64),
                stack_id VARCHAR(64),
                keywords TEXT,
                title VARCHAR(500),
                description TEXT,
                create_date TIMESTAMP,
                modify_date TIMESTAMP,
                extracted_at TIMESTAMP
            );
            """)

            # CLUSTER_PROGRESS
            cur.execute("""
            CREATE TABLE IF NOT EXISTS cluster_progress (
                folder_path VARCHAR(512) PRIMARY KEY,
                last_run TIMESTAMP
            );
            """)

            # CULLING_SESSIONS
            cur.execute("""
            CREATE TABLE IF NOT EXISTS culling_sessions (
                id SERIAL PRIMARY KEY,
                folder_path VARCHAR(4000),
                mode VARCHAR(50),
                status VARCHAR(50) DEFAULT 'active',
                total_images INTEGER DEFAULT 0,
                total_groups INTEGER DEFAULT 0,
                reviewed_groups INTEGER DEFAULT 0,
                picked_count INTEGER DEFAULT 0,
                rejected_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            );
            """)

            # CULLING_PICKS
            cur.execute("""
            CREATE TABLE IF NOT EXISTS culling_picks (
                id SERIAL PRIMARY KEY,
                session_id INTEGER NOT NULL,
                image_id INTEGER NOT NULL,
                group_id INTEGER,
                decision VARCHAR(50),
                auto_suggested SMALLINT DEFAULT 0,
                is_best_in_group SMALLINT DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """)

            # PIPELINE_PHASES
            cur.execute("""
            CREATE TABLE IF NOT EXISTS pipeline_phases (
                id SERIAL PRIMARY KEY,
                code VARCHAR(50) NOT NULL,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                sort_order INTEGER DEFAULT 0 NOT NULL,
                enabled SMALLINT DEFAULT 1 NOT NULL,
                optional SMALLINT DEFAULT 0 NOT NULL,
                default_skip SMALLINT DEFAULT 0 NOT NULL
            );
            """)

            # IMAGE_PHASE_STATUS
            cur.execute("""
            CREATE TABLE IF NOT EXISTS image_phase_status (
                id SERIAL PRIMARY KEY,
                image_id INTEGER NOT NULL,
                phase_id INTEGER NOT NULL,
                status VARCHAR(20) DEFAULT 'not_started' NOT NULL,
                executor_version VARCHAR(50),
                app_version VARCHAR(50),
                job_id INTEGER,
                attempt_count SMALLINT DEFAULT 0 NOT NULL,
                last_error TEXT,
                started_at TIMESTAMP,
                finished_at TIMESTAMP,
                updated_at TIMESTAMP,
                skip_reason TEXT,
                skipped_by VARCHAR(255)
            );
            """)

            # Indexes
            cur.execute("CREATE INDEX IF NOT EXISTS idx_images_folder_id ON images(folder_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_images_stack_id ON images(stack_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_images_hash ON images(image_hash);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_images_burst_uuid ON images(burst_uuid);")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_images_file_path ON images(file_path);")

            cur.execute("CREATE INDEX IF NOT EXISTS idx_file_paths_img_type ON file_paths(image_id, path_type);")

            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_exif_date ON image_exif(date_time_original);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_exif_make ON image_exif(make);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_exif_model ON image_exif(model);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_exif_lens ON image_exif(lens_model);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_exif_iso ON image_exif(iso);")

            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_xmp_burst ON image_xmp(burst_uuid);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_image_xmp_pick ON image_xmp(pick_status);")

            cur.execute("CREATE INDEX IF NOT EXISTS idx_culling_sessions_status ON culling_sessions(status);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_culling_sessions_folder ON culling_sessions(folder_path);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_culling_picks_session ON culling_picks(session_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_culling_picks_image ON culling_picks(image_id);")

            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_pipeline_phases_code ON pipeline_phases(code);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_pipeline_phases_enabled ON pipeline_phases(enabled);")

            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_image_phase ON image_phase_status(image_id, phase_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ips_image_id ON image_phase_status(image_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ips_phase_id ON image_phase_status(phase_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ips_status ON image_phase_status(status);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ips_job_id ON image_phase_status(job_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_ips_updated_at ON image_phase_status(updated_at);")

            # Idempotent constraints
            cur.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_folders_parent') THEN
                    ALTER TABLE folders ADD CONSTRAINT fk_folders_parent
                    FOREIGN KEY (parent_id) REFERENCES folders(id) ON DELETE CASCADE;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_images_jobs') THEN
                    ALTER TABLE images ADD CONSTRAINT fk_images_jobs
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_images_folders') THEN
                    ALTER TABLE images ADD CONSTRAINT fk_images_folders
                    FOREIGN KEY (folder_id) REFERENCES folders(id) ON DELETE SET NULL;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_images_stacks') THEN
                    ALTER TABLE images ADD CONSTRAINT fk_images_stacks
                    FOREIGN KEY (stack_id) REFERENCES stacks(id) ON DELETE SET NULL;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_file_paths_images') THEN
                    ALTER TABLE file_paths ADD CONSTRAINT fk_file_paths_images
                    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_image_exif_images') THEN
                    ALTER TABLE image_exif ADD CONSTRAINT fk_image_exif_images
                    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_image_xmp_images') THEN
                    ALTER TABLE image_xmp ADD CONSTRAINT fk_image_xmp_images
                    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_culling_picks_sessions') THEN
                    ALTER TABLE culling_picks ADD CONSTRAINT fk_culling_picks_sessions
                    FOREIGN KEY (session_id) REFERENCES culling_sessions(id) ON DELETE CASCADE;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_culling_picks_images') THEN
                    ALTER TABLE culling_picks ADD CONSTRAINT fk_culling_picks_images
                    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_jobs_phases') THEN
                    ALTER TABLE jobs ADD CONSTRAINT fk_jobs_phases
                    FOREIGN KEY (phase_id) REFERENCES pipeline_phases(id);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_ips_images') THEN
                    ALTER TABLE image_phase_status ADD CONSTRAINT fk_ips_images
                    FOREIGN KEY (image_id) REFERENCES images(id) ON DELETE CASCADE;
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_ips_phases') THEN
                    ALTER TABLE image_phase_status ADD CONSTRAINT fk_ips_phases
                    FOREIGN KEY (phase_id) REFERENCES pipeline_phases(id);
                END IF;
                IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_ips_job') THEN
                    ALTER TABLE image_phase_status ADD CONSTRAINT fk_ips_job
                    FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE SET NULL;
                END IF;
            END$$;
            """)

            logger.info("PostgreSQL schema initialization completed.")
