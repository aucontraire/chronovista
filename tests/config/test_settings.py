"""
Tests for settings configuration.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from chronovista.config.settings import Settings


def test_settings_defaults():
    """Test default settings values."""
    settings = Settings(
        youtube_api_key="test_key",
        youtube_client_id="test_id",
        youtube_client_secret="test_secret",
        secret_key="test_secret",
    )

    assert settings.app_name == "chronovista"
    assert settings.app_version == "0.1.0"
    assert settings.debug is False
    assert settings.log_level == "INFO"
    assert settings.nlp_batch_size == 100
    assert settings.tag_confidence_threshold == 0.7


def test_settings_path_validation():
    """Test path validation in settings."""
    settings = Settings(
        youtube_api_key="test_key",
        youtube_client_id="test_id",
        youtube_client_secret="test_secret",
        secret_key="test_secret",
        data_dir="./test_data",
    )

    assert isinstance(settings.data_dir, Path)
    assert settings.data_dir == Path("./test_data")


def test_settings_database_detection():
    """Test database type detection."""
    pg_settings = Settings(
        youtube_api_key="test_key",
        youtube_client_id="test_id",
        youtube_client_secret="test_secret",
        secret_key="test_secret",
        database_url="postgresql://user:pass@localhost/db",
    )

    assert pg_settings.is_postgresql is True
    assert pg_settings.is_mysql is False

    mysql_settings = Settings(
        youtube_api_key="test_key",
        youtube_client_id="test_id",
        youtube_client_secret="test_secret",
        secret_key="test_secret",
        database_url="mysql://user:pass@localhost/db",
    )

    assert mysql_settings.is_postgresql is False
    assert mysql_settings.is_mysql is True


def test_settings_oauth_scopes_parsing():
    """Test OAuth scopes parsing."""
    settings = Settings(
        youtube_api_key="test_key",
        youtube_client_id="test_id",
        youtube_client_secret="test_secret",
        secret_key="test_secret",
        oauth_scopes="scope1,scope2,scope3",
    )

    assert settings.oauth_scopes == ["scope1", "scope2", "scope3"]


def test_settings_log_level_validation():
    """Test log level validation."""
    with pytest.raises(ValueError, match="Invalid log level"):
        Settings(
            youtube_api_key="test_key",
            youtube_client_id="test_id",
            youtube_client_secret="test_secret",
            secret_key="test_secret",
            log_level="INVALID",
        )
