"""
Tests for services module functionality.
"""

import chronovista.services


def test_services_module():
    """Test services module basic functionality."""
    count = chronovista.services.get_service_count()
    assert count == 0
