"""
DbClient factory — returns the appropriate implementation based on config.

Reads ``database.client_mode`` from config.json:
    - ``"local"``  (default) → DbClientLocal (direct db.py calls)
    - ``"http"``              → DbClientHttp  (remote DB API service)

The factory caches the singleton so all modules share one instance.
"""

from __future__ import annotations

import logging
import threading
from typing import Union

from modules.db_client.local import DbClientLocal
from modules.db_client.http import DbClientHttp
from modules.db_client.protocol import DbClientProtocol

logger = logging.getLogger(__name__)

_instance: Union[DbClientLocal, DbClientHttp, None] = None
_lock = threading.Lock()


def get_db_client() -> DbClientProtocol:
    """Get or create the singleton DbClient instance.

    Thread-safe. First call reads config to pick the implementation;
    subsequent calls return the cached instance.
    """
    global _instance
    if _instance is not None:
        return _instance

    with _lock:
        # Double-checked locking
        if _instance is not None:
            return _instance

        try:
            from modules import config
            db_cfg = config.get_config_section("database")
            mode = str(db_cfg.get("client_mode", "local")).strip().lower()
        except Exception:
            mode = "local"

        if mode == "http":
            try:
                from modules import config as _cfg
                db_cfg = _cfg.get_config_section("database")
            except Exception:
                db_cfg = {}
            api_url = str(db_cfg.get("api_url", "http://localhost:7861")).strip()
            logger.info("DbClient: using HTTP mode → %s", api_url)
            _instance = DbClientHttp(base_url=api_url)
        else:
            if mode != "local":
                logger.warning("Unknown database.client_mode=%r, falling back to 'local'", mode)
            logger.info("DbClient: using local mode (direct db.py)")
            _instance = DbClientLocal()

        return _instance


def reset_db_client() -> None:
    """Reset the cached instance (for testing or config reload)."""
    global _instance
    with _lock:
        _instance = None
