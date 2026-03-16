"""
Backfill folder phase aggregate cache rows in FOLDERS.

Usage:
  python scripts/maintenance/backfill_folder_phase_aggregates.py [--limit N]
"""
import argparse
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from modules import db


def main():
    parser = argparse.ArgumentParser(description="Backfill folder phase aggregate cache")
    parser.add_argument('--limit', type=int, default=None, help='Recompute only first N folders (deepest-first)')
    args = parser.parse_args()

    db.init_db()
    result = db.backfill_folder_phase_aggregates(limit=args.limit)
    print(f"Recomputed {result['recomputed']} folders (selected {result['total']}).")


if __name__ == '__main__':
    main()
