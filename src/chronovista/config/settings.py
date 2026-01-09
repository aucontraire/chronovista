"""
Application settings and configuration management.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

from chronovista import __version__


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Application
    app_name: str = Field(default="chronovista")
    app_version: str = Field(default=__version__)
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")

    # YouTube API
    youtube_api_key: str = Field(default="")
    youtube_client_id: str = Field(default="")
    youtube_client_secret: str = Field(default="")

    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://user:password@localhost:5432/chronovista"
    )
    database_dev_url: str = Field(
        default="postgresql+asyncpg://dev_user:dev_password@localhost:5434/chronovista_dev"
    )
    database_integration_url: str = Field(
        default="postgresql+asyncpg://dev_user:dev_password@localhost:5434/chronovista_integration_test"
    )

    # OAuth
    oauth_redirect_uri: str = Field(default="http://localhost:8080/auth/callback")
    oauth_scopes: list[str] = Field(
        default=[
            "https://www.googleapis.com/auth/youtube.readonly",
            "https://www.googleapis.com/auth/youtube.force-ssl",
        ]
    )

    # Storage
    data_dir: Path = Field(default=Path("./data"))
    cache_dir: Path = Field(default=Path("./cache"))
    logs_dir: Path = Field(default=Path("./logs"))

    # NLP
    nlp_model: str = Field(default="en_core_web_sm")
    nlp_batch_size: int = Field(default=100)
    tag_confidence_threshold: float = Field(default=0.7)

    # Export
    export_format: str = Field(default="json")
    export_dir: Path = Field(default=Path("./exports"))
    max_export_size: str = Field(default="100MB")

    # Security
    secret_key: str = Field(default="dev-secret-key")
    session_timeout: int = Field(default=3600)
    token_refresh_threshold: int = Field(default=300)

    # Performance
    api_rate_limit: int = Field(default=100)
    concurrent_requests: int = Field(default=10)
    request_timeout: int = Field(default=30)
    retry_attempts: int = Field(default=3)
    retry_backoff: int = Field(default=2)

    # Development
    pytest_timeout: int = Field(default=30)
    coverage_threshold: int = Field(default=90)
    mypy_strict: bool = Field(default=True)

    # Database Development
    development_mode: bool = Field(default=False)
    db_create_all: bool = Field(default=False)  # Use create_all() instead of migrations
    db_reset_on_start: bool = Field(default=False)  # Reset schema on startup
    db_log_queries: bool = Field(default=False)  # Log all SQL queries
    db_validate_schema: bool = Field(default=True)  # Validate schema matches models

    @field_validator("oauth_scopes", mode="before")
    @classmethod
    def parse_oauth_scopes(cls, v: str | list[str]) -> list[str]:
        """Parse OAuth scopes from comma-separated string or list."""
        if isinstance(v, str):
            return [scope.strip() for scope in v.split(",")]
        return v

    @field_validator("data_dir", "cache_dir", "logs_dir", "export_dir", mode="before")
    @classmethod
    def ensure_path(cls, v: str | Path) -> Path:
        """Ensure directory paths are Path objects."""
        if isinstance(v, str):
            return Path(v)
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level."""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level: {v}")
        return v.upper()

    @field_validator("export_format")
    @classmethod
    def validate_export_format(cls, v: str) -> str:
        """Validate export format."""
        valid_formats = ["json", "csv", "xlsx"]
        if v.lower() not in valid_formats:
            raise ValueError(f"Invalid export format: {v}")
        return v.lower()

    def create_directories(self) -> None:
        """Create required directories if they don't exist."""
        for directory in [
            self.data_dir,
            self.cache_dir,
            self.logs_dir,
            self.export_dir,
        ]:
            directory.mkdir(parents=True, exist_ok=True)

    @property
    def is_postgresql(self) -> bool:
        """Check if database is PostgreSQL."""
        return "postgresql" in self.database_url

    @property
    def is_mysql(self) -> bool:
        """Check if database is MySQL."""
        return "mysql" in self.database_url

    @property
    def effective_database_url(self) -> str:
        """Get the effective database URL based on development mode."""
        return self.database_dev_url if self.development_mode else self.database_url

    @property
    def is_development_database(self) -> bool:
        """Check if using development database."""
        return self.development_mode or "chronovista_dev" in self.effective_database_url

    def get_sync_database_url(self) -> str:
        """Get synchronous database URL for Alembic migrations."""
        url = self.effective_database_url
        # Convert async drivers to sync
        return url.replace("+asyncpg", "").replace("+aiomysql", "")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
    }


def get_settings() -> Settings:
    """Get application settings."""
    return Settings()


# Global settings instance
settings = get_settings()
