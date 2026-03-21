#!/usr/bin/env python3
"""
Smoke requests to a running WebUI (default http://127.0.0.1:7860).

Requires: requests, WebUI already listening.

Examples:
  python scripts/debug/smoke_api_submit.py runs --path "D:\\\\Photos\\\\Z8\\\\folder"
  python scripts/debug/smoke_api_submit.py runs-culling --path "/mnt/d/Photos/Z6ii/105mm"
  python scripts/debug/smoke_api_submit.py tagging --path "/mnt/d/Photos/Z6ii/105mm"
  python scripts/debug/smoke_api_submit.py images --page 1 --page-size 100
"""
from __future__ import annotations

import argparse
import json
import sys

try:
    import requests
except ImportError:
    print("Install requests: pip install requests", file=sys.stderr)
    sys.exit(1)


def _post(base_url: str, path: str, payload: dict) -> None:
    url = base_url.rstrip("/") + path
    try:
        r = requests.post(url, json=payload, timeout=30)
        print(f"Status Code: {r.status_code}")
        print(f"Response: {json.dumps(r.json(), indent=2)}")
    except Exception as e:
        print(f"Error: {e}")


def _get(base_url: str, path: str, params: dict | None = None) -> None:
    url = base_url.rstrip("/") + path
    try:
        r = requests.get(url, params=params or {}, timeout=30)
        print(f"Status Code: {r.status_code}")
        print(f"Response: {r.text}")
    except Exception as e:
        print(f"Error: {e}")


def main() -> None:
    p = argparse.ArgumentParser(description="Smoke-test pipeline API (POST and GET).")
    p.add_argument("--base-url", default="http://127.0.0.1:7860", help="WebUI base URL")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("runs", help="POST /api/runs/submit (full default stages)")
    sp.add_argument("--path", required=True, help="Folder path (Windows or WSL)")
    sp.set_defaults(
        _run=lambda a: _post(
            a.base_url,
            "/api/runs/submit",
            {
                "scope_type": "folder",
                "scope_paths": [a.path],
                "skip_done": True,
                "force_rerun": False,
            },
        )
    )

    sp2 = sub.add_parser("runs-culling", help="POST /api/runs/submit (culling only)")
    sp2.add_argument("--path", required=True)
    sp2.set_defaults(
        _run=lambda a: _post(
            a.base_url,
            "/api/runs/submit",
            {
                "scope_type": "folder",
                "scope_paths": [a.path],
                "stages": ["culling"],
                "skip_done": True,
                "force_rerun": False,
            },
        )
    )

    sp3 = sub.add_parser("tagging", help="POST /api/tagging/start")
    sp3.add_argument("--path", required=True)
    sp3.add_argument("--overwrite", action="store_true")
    sp3.add_argument("--captions", action="store_true", help="generate_captions=True")
    sp3.set_defaults(
        _run=lambda a: _post(
            a.base_url,
            "/api/tagging/start",
            {
                "input_path": a.path,
                "overwrite": a.overwrite,
                "generate_captions": a.captions,
            },
        )
    )

    sp4 = sub.add_parser("images", help="GET /api/images (paged list)")
    sp4.add_argument("--page", type=int, default=1)
    sp4.add_argument("--page-size", type=int, default=100, dest="page_size")
    sp4.set_defaults(
        _run=lambda a: _get(
            a.base_url,
            "/api/images",
            {"page": a.page, "page_size": a.page_size},
        )
    )

    args = p.parse_args()
    args._run(args)


if __name__ == "__main__":
    main()
