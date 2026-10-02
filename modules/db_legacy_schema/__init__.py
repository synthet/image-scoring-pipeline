"""Composable stages for the legacy Firebird schema initializer."""

from modules.db_legacy_schema.base import initialize_base_schema
from modules.db_legacy_schema.integrity import run_integrity_phase
from modules.db_legacy_schema.keywords import run_keyword_phase
from modules.db_legacy_schema.migrations import run_additive_migrations

__all__ = [
    "initialize_base_schema",
    "run_additive_migrations",
    "run_integrity_phase",
    "run_keyword_phase",
]
