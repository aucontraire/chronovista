"""
Tests for CLI package functionality.
"""

import chronovista.cli


def test_cli_module():
    """Test CLI module basic functionality."""
    # Test that the CLI module can be imported
    assert hasattr(chronovista.cli, "__name__")
    assert chronovista.cli.__name__ == "chronovista.cli"
