"""Shared Pydantic type annotations for API schemas.

Provides type aliases that handle JSON wire-format coercion
while preserving strict=True on model-level ConfigDict.
"""

from typing import Annotated
from uuid import UUID

from pydantic import BeforeValidator


def _coerce_uuid(v: object) -> object:
    """Coerce a JSON string to UUID before strict validation.

    Parameters
    ----------
    v : object
        The raw input value.

    Returns
    -------
    object
        A uuid.UUID if v was a valid UUID string, otherwise v unchanged.
    """
    if isinstance(v, str):
        return UUID(v)
    return v


CoercedUUID = Annotated[UUID, BeforeValidator(_coerce_uuid)]
"""UUID type that accepts string input under strict=True models.

Use this instead of ``uuid.UUID`` on request schema fields where
the value arrives as a JSON string from HTTP clients.
"""
