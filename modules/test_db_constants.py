"""Shared constants for test database isolation (Postgres + docs)."""

import os

POSTGRES_TEST_DB = "image_scoring_test"

# Legacy name kept for docs; alone it no longer unlocks production under pytest (see risk env below).
POSTGRES_PRODUCTION_IN_PYTEST_ENV = "IMAGE_SCORING_POSTGRES_PRODUCTION_IN_PYTEST"

# Must be set together with POSTGRES_PRODUCTION_IN_PYTEST_ENV to use a non-test Postgres DB during pytest.
POSTGRES_PRODUCTION_PYTEST_RISK_ACCEPTED_ENV = "IMAGE_SCORING_I_ACCEPT_PRODUCTION_PYTEST_RISK"


def _env_truthy(key: str) -> bool:
    return os.environ.get(key, "").strip().lower() in ("1", "true", "yes")


def postgres_production_allowed_in_pytest() -> bool:
    """Both env vars required to point pytest at a non-test Postgres database."""
    return _env_truthy(POSTGRES_PRODUCTION_IN_PYTEST_ENV) and _env_truthy(
        POSTGRES_PRODUCTION_PYTEST_RISK_ACCEPTED_ENV
    )
