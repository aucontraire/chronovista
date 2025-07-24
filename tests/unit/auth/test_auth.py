"""
Tests for auth module functionality.
"""

import chronovista.auth


def test_auth_module():
    """Test auth module basic functionality."""
    status = chronovista.auth.get_auth_status()
    # Status can be either authenticated or not_authenticated depending on environment
    assert status in ["authenticated", "not_authenticated"]
