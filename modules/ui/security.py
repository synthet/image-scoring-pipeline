"""Lightweight security helpers (rate limiting, path validation, SQL guards).

Extracted from app.py so tests and api.py can import these without pulling in
the full UI/ML dependency chain.
"""

import os
import re
import time
from collections import defaultdict

# --- Rate limiting ---
_rate_limits: dict = defaultdict(list)
_RATE_LIMIT_WINDOW = 60  # seconds
_RATE_LIMIT_MAX_REQUESTS = 10


def _check_rate_limit(endpoint: str):
    """Simple in-memory rate limiter per endpoint."""
    from fastapi import HTTPException
    now = time.time()
    _rate_limits[endpoint] = [t for t in _rate_limits[endpoint] if now - t < _RATE_LIMIT_WINDOW]
    if len(_rate_limits[endpoint]) >= _RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    _rate_limits[endpoint].append(now)

# --- Path validation ---
_ALLOWED_IMAGE_ROOTS = None


def _validate_file_path(file_path: str) -> str:
    """Validate and resolve a file path, rejecting traversal attempts."""
    from fastapi import HTTPException
    from modules import config
    if ".." in file_path:
        raise HTTPException(status_code=400, detail="Invalid path")

    resolved = os.path.realpath(file_path)

    global _ALLOWED_IMAGE_ROOTS
    if _ALLOWED_IMAGE_ROOTS is None:
        _ALLOWED_IMAGE_ROOTS = config.get_config_value("allowed_paths", [])
        _ALLOWED_IMAGE_ROOTS.extend(config.get_default_allowed_paths())

    if _ALLOWED_IMAGE_ROOTS and not any(
        resolved.startswith(os.path.realpath(root)) for root in _ALLOWED_IMAGE_ROOTS
    ):
        raise HTTPException(status_code=403, detail="Access denied")

    return resolved

# --- SQL query validation ---
_SQL_FORBIDDEN_PATTERNS = re.compile(
    r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|EXECUTE|INTO|GRANT|REVOKE)\b',
    re.IGNORECASE
)
