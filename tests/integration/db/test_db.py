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
    # Test that we can import all the models
    from chronovista.db.models import Base, Channel, Video

    assert Base is not None
    assert Channel is not None
    assert Video is not None

    # Test that models have the expected table names
    assert Channel.__tablename__ == "channels"
    assert Video.__tablename__ == "videos"
