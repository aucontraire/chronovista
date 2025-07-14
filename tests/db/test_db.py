"""
Tests for db module functionality.
"""

import chronovista.db
import chronovista.db.models


def test_db_module():
    """Test database module basic functionality."""
    status = chronovista.db.get_db_status()
    assert status == "not_configured"


def test_db_models_module():
    """Test database models module basic functionality."""
    count = chronovista.db.models.get_table_count()
    assert count == 0
