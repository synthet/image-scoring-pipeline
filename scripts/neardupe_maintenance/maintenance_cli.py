"""Explicit maintenance entrypoint; scoring never imports or calls this command."""

import argparse
import json
import os
from pathlib import Path
import sys

from .maintenance import Executor, SafetyError
from .postgres_adapter import PostgresAdapter


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--backup-dir", type=Path, required=True)
    p.add_argument("--source-root", type=Path, action="append", required=True)
    p.add_argument("--backend", type=Path, required=True)
    p.add_argument(
        "--mode", choices=["dry-run", "apply", "resume", "recover"], default="dry-run"
    )
    a = p.parse_args()
    if a.mode != "dry-run" and os.name != "nt":
        raise SafetyError(
            "Live library changes require the native Windows exclusive-handle executor"
        )
    # Backend is an explicitly verified checkout; credentials remain in its
    # configured environment/protected configuration and are never printed.
    sys.path.insert(0, str(a.backend.resolve()))
    import psycopg2
    from modules.db_postgres import get_pg_config

    conn = psycopg2.connect(**get_pg_config())
    try:
        adapter = PostgresAdapter(conn)
        manifest = json.loads(a.manifest.read_text(encoding="utf-8"))
        if manifest.get("source_identity") != adapter.identity():
            raise SafetyError(
                "Manifest targets a different PostgreSQL database/cluster"
            )
        executor = Executor(a.manifest, a.backup_dir, adapter, a.source_root)
        if a.mode == "dry-run":
            result = executor.dry_run()
        elif a.mode in ("apply", "resume"):
            result = executor.apply(resume=a.mode == "resume")
        else:
            result = executor.recover()
        print(json.dumps(result, indent=1), flush=True)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
