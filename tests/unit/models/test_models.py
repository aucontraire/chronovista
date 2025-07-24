"""
Tests for models module functionality.
"""

import chronovista.models


def test_models_module():
    """Test models module basic functionality."""
    count = chronovista.models.get_model_count()
    # Should have multiple Pydantic models available
    assert count > 0
