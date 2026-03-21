#!/usr/bin/env python3
"""
Verify that modules.db caches resolved host IP between get_db() calls.

Set DEBUG_DB_CONNECTION=1 to see connection debug logs. Intended for WSL/Linux
(host resolution path); on Windows this script exits with a message.

Usage (WSL, project venv per CLAUDE.md):
  export DEBUG_DB_CONNECTION=1
  python scripts/debug/verify_db_host_ip_cache.py
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

logging.basicConfig(level=logging.DEBUG)

from modules import db  # noqa: E402


def main() -> None:
    if os.name == "nt":
        print("This diagnostic is intended for WSL/Linux (host IP resolution).")
        sys.exit(0)

    print("Testing WSL IP caching...")
    os.environ["DEBUG_DB_CONNECTION"] = "1"

    print("\n--- First call ---")
    try:
        db.get_db()
    except Exception as e:
        print(f"First call (expected) failure: {e}")

    first_ip = db._cached_host_ip
    print(f"First resolved IP: {first_ip}")

    print("\n--- Second call ---")
    try:
        db.get_db()
    except Exception as e:
        print(f"Second call (expected) failure: {e}")

    second_ip = db._cached_host_ip
    print(f"Second resolved IP: {second_ip}")

    if first_ip == second_ip and first_ip is not None:
        print("\nSUCCESS: IP was cached and reused.")
    else:
        print("\nFAILURE: IP was not cached or is None.")


if __name__ == "__main__":
    main()
