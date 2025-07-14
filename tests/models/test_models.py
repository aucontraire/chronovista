"""
Tests for models module functionality.
"""

import chronovista.models


def test_models_module():
    """Test models module basic functionality."""
    count = chronovista.models.get_model_count()
    assert count == 0
