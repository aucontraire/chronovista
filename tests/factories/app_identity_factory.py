"""
Factory for AppIdentity Pydantic models using factory_boy (Feature 060).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import factory
from factory import LazyFunction

from chronovista.models.app_identity import (
    AppIdentity,
    AppIdentityBase,
    AppIdentityCreate,
    AppIdentitySource,
    AppIdentityUpdate,
)


class AppIdentityBaseFactory(factory.Factory[AppIdentityBase]):
    """Factory for AppIdentityBase models."""

    class Meta:
        model = AppIdentityBase

    user_id: Any = LazyFunction(lambda: "UCzYTmeK-6v3DcJ6hzRh1q9w")
    source: Any = LazyFunction(lambda: AppIdentitySource.CHANNEL)


class AppIdentityCreateFactory(factory.Factory[AppIdentityCreate]):
    """Factory for AppIdentityCreate models."""

    class Meta:
        model = AppIdentityCreate

    user_id: Any = LazyFunction(lambda: "UCzYTmeK-6v3DcJ6hzRh1q9w")
    source: Any = LazyFunction(lambda: AppIdentitySource.CHANNEL)


class AppIdentityUpdateFactory(factory.Factory[AppIdentityUpdate]):
    """Factory for AppIdentityUpdate models (all fields default None)."""

    class Meta:
        model = AppIdentityUpdate


class AppIdentityFactory(factory.Factory[AppIdentity]):
    """Factory for the full AppIdentity model."""

    class Meta:
        model = AppIdentity

    id: Any = LazyFunction(lambda: 1)
    user_id: Any = LazyFunction(lambda: "UCzYTmeK-6v3DcJ6hzRh1q9w")
    source: Any = LazyFunction(lambda: AppIdentitySource.CHANNEL)
    created_at: Any = LazyFunction(lambda: datetime.now(UTC))
    updated_at: Any = LazyFunction(lambda: datetime.now(UTC))


def create_app_identity(**kwargs: Any) -> AppIdentity:
    """Create a full AppIdentity with optional overrides."""
    return AppIdentityFactory(**kwargs)


def create_app_identity_create(**kwargs: Any) -> AppIdentityCreate:
    """Create an AppIdentityCreate with optional overrides."""
    return AppIdentityCreateFactory(**kwargs)
