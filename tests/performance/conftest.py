"""
Shared fixtures for performance tests.

Integration test fixtures are imported from the integration conftest.
"""

from __future__ import annotations

import pytest

# Import integration fixtures to make them available to performance tests
# These need to be in module scope for pytest to discover them as fixtures
from tests.integration.api.conftest import (
    integration_db_engine,
    integration_db_schema_setup,
    integration_db_session,
    integration_session_factory,
    integration_test_db_url,
    settings,
)

# Re-export fixtures so pytest discovers them
__all__ = [
    "integration_db_engine",
    "integration_db_schema_setup",
    "integration_db_session",
    "integration_session_factory",
    "integration_test_db_url",
    "settings",
]


@pytest.fixture(scope="session")
def event_loop():
    """
    Create an event loop for async performance tests.

    This overrides the default function-scoped event_loop to be session-scoped,
    which is more efficient for performance tests that need to set up database
    connections once.
    """
    import asyncio

    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
