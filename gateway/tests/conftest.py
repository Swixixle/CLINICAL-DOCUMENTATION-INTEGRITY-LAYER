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
