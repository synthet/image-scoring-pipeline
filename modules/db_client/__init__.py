"""
DbClient abstraction layer.

Provides a Protocol-based interface for database operations, enabling
scoring/pipeline modules to be decoupled from direct db.py imports.

Usage:
    from modules.db_client import get_db_client
    client = get_db_client()
    details = client.get_image_details(file_path)

Two implementations:
    - DbClientLocal: delegates to modules.db (monolith mode)
    - DbClientHttp: calls a remote DB API service (microservice mode)
"""

from modules.db_client.factory import get_db_client
from modules.db_client.protocol import DbClientProtocol

__all__ = ["get_db_client", "DbClientProtocol"]
