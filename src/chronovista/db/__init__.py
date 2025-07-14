"""
Database module for chronovista.

Contains SQLAlchemy models, repository patterns, and database migration
management for local PostgreSQL/MySQL storage.
"""

from __future__ import annotations

__all__: list[str] = ["get_db_status"]


def get_db_status() -> str:
    """Get current database status."""
    return "not_configured"
