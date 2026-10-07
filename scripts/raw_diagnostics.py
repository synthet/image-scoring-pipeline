#!/usr/bin/env python3
"""Print selected RAW geometry/decoder fields as JSON without decoding or DB access."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from modules.raw_diagnostics import probe_raw_file


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--tool", help="raw-identify executable; defaults to RAW_IDENTIFY_PATH/PATH")
    parser.add_argument("--timeout", type=float, default=5.0, help="total seconds per file (max 30)")
    args = parser.parse_args()
    reports = [{"file": str(path), **probe_raw_file(path, tool=args.tool, enabled=True, timeout=args.timeout)}
               for path in args.files]
    print(json.dumps(reports, indent=2))
    return int(any(r["status"] != "ok" for r in reports))


if __name__ == "__main__":
    raise SystemExit(main())
