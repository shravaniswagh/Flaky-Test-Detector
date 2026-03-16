"""
conftest.py — Shared pytest fixtures for the flaky test sample suite.
"""

import os
import pytest


@pytest.fixture(autouse=True)
def clean_env():
    """Ensure environment is clean before and after each test."""
    saved = os.environ.get("TEST_API_KEY")
    yield
    # Restore original state
    if saved is not None:
        os.environ["TEST_API_KEY"] = saved
    else:
        os.environ.pop("TEST_API_KEY", None)
