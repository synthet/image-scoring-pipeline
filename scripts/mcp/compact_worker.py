#!/usr/bin/env python3
"""DEPRECATED JSONL worker (old is-be-mcp Node host). Delegates to the vexlum worker.

Use ``python -m modules.vexlum worker``. The vexlum worker understands the old tool names
(``search``, ``dispatch``, ``sse_status``) as well as ``resolve`` / ``execute`` / ``list``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Project root: scripts/mcp -> scripts -> root
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from modules.vexlum.worker import dumps as dumps_response  # noqa: E402,F401 - kept for imports
from modules.vexlum.worker import main as _vexlum_worker_main  # noqa: E402


def main() -> int:
    logging.getLogger(__name__).warning(
        "scripts/mcp/compact_worker.py is deprecated; use `python -m modules.vexlum worker`."
    )
    return _vexlum_worker_main()


if __name__ == "__main__":
    raise SystemExit(main())
