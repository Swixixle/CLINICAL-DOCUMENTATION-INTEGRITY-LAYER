"""
Pytest configuration for CDIL tests.

This file is loaded by pytest before any test modules are imported.
It sets up the test environment, including disabling rate limiting.

The environment variables are set at module level (not in pytest_configure)
because they need to be available before any modules are imported during
pytest's collection phase.
"""

import os

# Set ENV=TEST to disable rate limiting BEFORE any modules are imported
# This happens during pytest's initial import phase, before test collection
os.environ["ENV"] = "TEST"
os.environ["DISABLE_RATE_LIMITS"] = "1"

import pytest


@pytest.fixture(autouse=True, scope="session")
def setup_test_database():
    """Ensure the database schema is created before any tests run.

    TestClient in newer starlette versions does not run the app lifespan
    unless used as a context manager. This fixture ensures the schema is
    initialised once for the entire test session.
    """
    from gateway.app.db.migrate import ensure_schema

    ensure_schema()
