"""Shared sorting enums for API endpoints.

This module provides shared sort-related enums used across multiple
API routers to ensure consistent sort behavior.
"""

from __future__ import annotations

from enum import Enum


class SortOrder(str, Enum):
    """Sort order direction.

    Used by all list endpoints that support sorting to specify
    ascending or descending order.
    """

    ASC = "asc"
    DESC = "desc"
