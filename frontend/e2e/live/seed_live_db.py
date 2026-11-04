#!/usr/bin/env python3
"""Seed image_scoring_test for the UI E2E live tier (run by e2e/scripts/run-live.mjs).

Refuses to run against any other database. Adds one finished run the smoke tests can look for.
"""

from __future__ import annotations

import os
import sys

from modules import db_postgres
from modules.test_db_constants import POSTGRES_TEST_DB

SEED_DESCRIPTION = "ui-e2e-live-seed"


def main() -> int:
    if os.environ.get("POSTGRES_DB") != POSTGRES_TEST_DB:
        print(f"refusing to seed: POSTGRES_DB must be {POSTGRES_TEST_DB}", file=sys.stderr)
        return 2
    if db_postgres.get_pg_config()["dbname"] != POSTGRES_TEST_DB:
        print("refusing to seed: resolved database is not the test database", file=sys.stderr)
        return 2

    db_postgres.ensure_database_exists(POSTGRES_TEST_DB)
    db_postgres.reset_pool()
    db_postgres.init_db()
    # A real WebUI runs the job dispatcher: start empty so no job left by a pytest run can execute.
    # truncate_app_tables() itself refuses any database but image_scoring_test.
    db_postgres.truncate_app_tables()

    from modules import db

    job_id = db.create_job(
        "/tmp/ui-e2e-live-folder",
        job_type="scoring",
        status="completed",
        description=SEED_DESCRIPTION,
    )
    print(f"seeded run {job_id} in {POSTGRES_TEST_DB}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
