"""Alembic environment — uses modules/db_postgres.py for the connection URL."""

import sys
import os
from logging.config import fileConfig

from alembic import context

# Make the project root importable so modules.db_postgres is reachable.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# We use run_migrations_offline / run_migrations_online with a plain psycopg2
# connection rather than SQLAlchemy engine, keeping the stack minimal.

def get_url() -> str:
    """Build the database URL from modules.db_postgres config."""
    from modules.db_postgres import get_pg_config
    cfg = get_pg_config()
    return (
        f"postgresql+psycopg2://{cfg['user']}:{cfg['password']}"
        f"@{cfg['host']}:{cfg['port']}/{cfg['dbname']}"
    )


def run_migrations_offline() -> None:
    """Run migrations without a live database connection (SQL output only)."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=None,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database."""
    from sqlalchemy import create_engine

    engine = create_engine(get_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
