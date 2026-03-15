"""
Factory for BatchListItem Pydantic models using factory_boy.

Provides reusable test data factories for the BatchListItem model introduced
in Feature 045 (Correction Intelligence Pipeline) with sensible defaults and
easy customization.

BatchListItem is an immutable aggregation result model (frozen=True) that
summarizes a batch of corrections sharing the same batch_id.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import factory
from factory import LazyFunction, Sequence
from uuid_utils import uuid7

from chronovista.models.batch_correction_models import BatchListItem


def _uuid7() -> uuid.UUID:
    """Generate a UUIDv7 as a standard uuid.UUID for Pydantic compatibility."""
    return uuid.UUID(bytes=uuid7().bytes)


class BatchListItemFactory(factory.Factory[BatchListItem]):
    """Factory for BatchListItem models.

    Produces BatchListItem instances suitable for unit tests.  Use
    ``.build()`` to instantiate without a database session.

    BatchListItem is an immutable aggregation result (``frozen=True``), so
    only ``.build()`` is supported — ``.create()`` requires a database-backed
    session and is not meaningful for this model.
    """

    class Meta:
        model = BatchListItem

    batch_id: Any = LazyFunction(_uuid7)
    correction_count: Any = LazyFunction(lambda: 5)
    corrected_by_user_id: Any = LazyFunction(lambda: "user:batch")
    pattern: Any = Sequence(lambda n: f"original text {n}")
    replacement: Any = Sequence(lambda n: f"corrected text {n}")
    batch_timestamp: Any = LazyFunction(
        lambda: datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    )


# ---------------------------------------------------------------------------
# Convenience factory function
# ---------------------------------------------------------------------------


def create_batch_list_item(**kwargs: Any) -> BatchListItem:
    """Create a BatchListItem with keyword arguments.

    Parameters
    ----------
    **kwargs : Any
        Any field overrides to apply on top of factory defaults.

    Returns
    -------
    BatchListItem
        A built BatchListItem Pydantic model.
    """
    result = BatchListItemFactory.build(**kwargs)
    assert isinstance(result, BatchListItem)
    return result


# ---------------------------------------------------------------------------
# Common test data patterns
# ---------------------------------------------------------------------------


class BatchListItemTestData:
    """Common test data patterns for BatchListItem models."""

    VALID_USER_IDS = [
        "user:batch",
        "cli",
        "user:local",
        "api",
        "script:backfill",
    ]

    VALID_PATTERNS = [
        "Shanebam",
        "Chomski",
        "teh",
        "recieve",
        "seperate",
    ]

    VALID_REPLACEMENTS = [
        "Sheinbaum",
        "Chomsky",
        "the",
        "receive",
        "separate",
    ]

    VALID_CORRECTION_COUNTS = [1, 2, 5, 10, 50, 100]

    INVALID_CORRECTION_COUNTS = [0, -1, -100]

    @classmethod
    def valid_batch_data(cls) -> dict[str, Any]:
        """Get valid BatchListItem data with all required fields populated.

        Returns
        -------
        dict[str, Any]
            A fresh dictionary of valid field values for BatchListItem.
        """
        return {
            "batch_id": _uuid7(),
            "correction_count": 5,
            "corrected_by_user_id": cls.VALID_USER_IDS[0],
            "pattern": cls.VALID_PATTERNS[0],
            "replacement": cls.VALID_REPLACEMENTS[0],
            "batch_timestamp": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
        }

    @classmethod
    def minimal_batch_data(cls) -> dict[str, Any]:
        """Get the smallest valid BatchListItem data (single correction).

        Returns
        -------
        dict[str, Any]
            Batch data with correction_count of 1 (the minimum allowed value).
        """
        data = cls.valid_batch_data()
        data["correction_count"] = 1
        return data

    @classmethod
    def large_batch_data(cls) -> dict[str, Any]:
        """Get BatchListItem data representing a large batch operation.

        Returns
        -------
        dict[str, Any]
            Batch data with a high correction_count representing mass apply.
        """
        data = cls.valid_batch_data()
        data.update(
            {
                "correction_count": 100,
                "corrected_by_user_id": "user:batch",
                "pattern": "Shanebam",
                "replacement": "Sheinbaum",
            }
        )
        return data
