"""
Tests for auth module functionality.
"""

import chronovista.auth


def test_auth_module():
    """Test auth module basic functionality."""
    status = chronovista.auth.get_auth_status()
    assert status == "not_authenticated"
