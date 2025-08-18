"""
Alembic environment configuration.
"""

from __future__ import annotations

import contextlib
from logging.config import fileConfig
from typing import Any

from alembic import context

from chronovista.config.database import Base
from chronovista.config.settings import settings

# Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Set the SQLAlchemy URL from settings or command line override
database_url = context.get_x_argument(as_dictionary=True).get("database_url")
if database_url:
    config.set_main_option("sqlalchemy.url", database_url)
else:
    # Use sync URL for migrations
    config.set_main_option("sqlalchemy.url", settings.get_sync_database_url())

# Add your model's MetaData object here for 'autogenerate' support
target_metadata = Base.metadata

# Import all models to ensure they are registered with Base
with contextlib.suppress(ImportError):
    from chronovista.db.models import *  # noqa: F401, F403


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    if url is None:
        raise ValueError("No database URL configured for migrations")
    
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Any) -> None:
    """Run migrations with database connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    from sqlalchemy import create_engine
    
    # Use the configured URL (which may be overridden via -x database_url)
    url = config.get_main_option("sqlalchemy.url")
    if url is None:
        raise ValueError("No database URL configured for migrations")
    
    connectable = create_engine(url)

    with connectable.connect() as connection:
        do_run_migrations(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

