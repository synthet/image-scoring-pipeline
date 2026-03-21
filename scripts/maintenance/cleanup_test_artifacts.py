#!/usr/bin/env python3
"""
Remove test run artifacts: temp dirs, output dirs, and log files created by tests.
Run from project root.
"""

import argparse
import glob
import os
import shutil
import sys

# Project root (script lives in scripts/maintenance/)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))


# Directories created by test scripts
TEST_DIRS = [
    "test_output",
    "test_output_multitier",
    "temp_test_init",
    "temp_ddl_test",
    "test_images",
    "output",
    "results",
    "test_quality_results",
]

# Log/artifact file patterns (root only)
LOG_PATTERNS = [
    "test_output.txt",
    "test_results.txt",
    "test_output*.log",
    "webui_out*.txt",
    "webui_error*.txt",
    "debug_output*.txt",
    "verify_result*.txt",
    "verify_stacks*.txt",
    "test_run.log",
    "test_verification*.log",
    "verification.sql",
]


def cleanup(dry_run: bool = False) -> dict:
    """Remove test artifacts. Returns stats: {removed_dirs, removed_files, errors}."""
    os.chdir(PROJECT_ROOT)
    removed_dirs = []
    removed_files = []
    errors = []

    # Remove directories
    for d in TEST_DIRS:
        path = os.path.join(PROJECT_ROOT, d)
        if os.path.isdir(path):
            try:
                if not dry_run:
                    shutil.rmtree(path)
                removed_dirs.append(d)
            except Exception as e:
                errors.append(f"{d}: {e}")

    # Remove log files (project root only)
    for pattern in LOG_PATTERNS:
        for path in glob.glob(os.path.join(PROJECT_ROOT, pattern)):
            if os.path.isfile(path):
                try:
                    if not dry_run:
                        os.remove(path)
                    removed_files.append(os.path.basename(path))
                except Exception as e:
                    errors.append(f"{os.path.basename(path)}: {e}")

    return {"removed_dirs": removed_dirs, "removed_files": removed_files, "errors": errors}


def main():
    parser = argparse.ArgumentParser(description="Remove test run artifacts (temp dirs, logs)")
    parser.add_argument("-n", "--dry-run", action="store_true", help="Show what would be removed without deleting")
    args = parser.parse_args()

    stats = cleanup(dry_run=args.dry_run)

    if args.dry_run:
        print("Dry run – no files removed.\n")

    if stats["removed_dirs"]:
        label = "Would remove dirs:" if args.dry_run else "Removed dirs:"
        print(f"{label} {', '.join(stats['removed_dirs'])}")
    if stats["removed_files"]:
        label = "Would remove files:" if args.dry_run else "Removed files:"
        print(f"{label} {', '.join(stats['removed_files'])}")
    if stats["errors"]:
        print("Errors:")
        for e in stats["errors"]:
            print(f"  - {e}")
        sys.exit(1)

    if not stats["removed_dirs"] and not stats["removed_files"]:
        print("No test artifacts found.")


if __name__ == "__main__":
    main()
