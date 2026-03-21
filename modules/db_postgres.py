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
    """Initialize PostgreSQL database schema (Phase 1 Foundation)."""
    with PGConnectionManager(commit=True) as conn:
        with conn.cursor() as cur:
            # Enable pgvector
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            
            # FOLDERS
            cur.execute("""
            CREATE TABLE IF NOT EXISTS folders (
                id SERIAL PRIMARY KEY,
                path VARCHAR(4000),
                parent_id INTEGER REFERENCES folders(id) ON DELETE CASCADE,
                is_fully_scored SMALLINT DEFAULT 0,
                is_keywords_processed SMALLINT DEFAULT 0,
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
                status VARCHAR(50),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                log TEXT
            );
            """)

            # IMAGES
            cur.execute("""
            CREATE TABLE IF NOT EXISTS images (
                id SERIAL PRIMARY KEY,
                job_id INTEGER REFERENCES jobs(id) ON DELETE SET NULL,
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
                folder_id INTEGER REFERENCES folders(id) ON DELETE SET NULL,
                stack_id INTEGER REFERENCES stacks(id) ON DELETE SET NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                burst_uuid VARCHAR(64),
                image_embedding vector(1280)
            );
            """)

            # Indexes for IMAGES
            cur.execute("CREATE INDEX IF NOT EXISTS idx_images_folder_id ON images(folder_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_images_stack_id ON images(stack_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_images_hash ON images(image_hash);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_images_burst_uuid ON images(burst_uuid);")

            # FILE_PATHS
            cur.execute("""
            CREATE TABLE IF NOT EXISTS file_paths (
                id SERIAL PRIMARY KEY,
                image_id INTEGER REFERENCES images(id) ON DELETE CASCADE,
                path VARCHAR(4000),
                last_seen TIMESTAMP,
                path_type VARCHAR(10),
                is_verified SMALLINT,
                verification_date TIMESTAMP
            );
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_file_paths_img_type ON file_paths(image_id, path_type);")

            logger.info("PostgreSQL schema initialization completed.")

