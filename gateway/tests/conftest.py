"""
Pytest configuration for CDIL tests.

This file is loaded by pytest before any test modules are imported.
It sets up the test environment, including disabling rate limiting.
"""

import os

# CRITICAL: Set ENV=TEST to disable rate limiting BEFORE any modules are imported
# This must happen at the very start, before pytest starts collecting tests
os.environ["ENV"] = "TEST"
os.environ["DISABLE_RATE_LIMITS"] = "1"

def pytest_configure(config):
    """
    Pytest hook that runs at the very beginning of test execution.
    This ensures environment variables are set before any test collection happens.
    """
    os.environ["ENV"] = "TEST"
    os.environ["DISABLE_RATE_LIMITS"] = "1"
