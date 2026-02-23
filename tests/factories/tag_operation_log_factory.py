"""
Factory for TagOperationLog ORM model using factory_boy.

Provides reusable test data factories for TagOperationLog instances
with sensible defaults and easy customization.

Note: TagOperationLog does not have a separate Pydantic model, so this
factory targets the SQLAlchemy ORM model directly.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

import factory
from factory import LazyFunction
from uuid_utils import uuid7

from chronovista.db.models import TagOperationLog


class TagOperationLogFactory(factory.Factory[TagOperationLog]):
    """Factory for TagOperationLog ORM models."""

    class Meta:
        model = TagOperationLog
        exclude = ["_skip_session"]

    # Exclude from SQLAlchemy session management — these are in-memory only
    _skip_session: Any = True

    id: Any = LazyFunction(uuid7)
    operation_type: Any = LazyFunction(lambda: "create")
    source_canonical_ids: Any = LazyFunction(list)
    target_canonical_id: Any = LazyFunction(lambda: None)
    affected_alias_ids: Any = LazyFunction(list)
    reason: Any = LazyFunction(lambda: None)
    performed_by: Any = LazyFunction(lambda: "system")
    performed_at: Any = LazyFunction(
        lambda: datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    )
    rollback_data: Any = LazyFunction(dict)
    rolled_back: Any = LazyFunction(lambda: False)
    rolled_back_at: Any = LazyFunction(lambda: None)


# Convenience factory methods
def create_tag_operation_log(**kwargs: Any) -> TagOperationLog:
    """Create a TagOperationLog with keyword arguments."""
    result = TagOperationLogFactory.build(**kwargs)
    assert isinstance(result, TagOperationLog)
    return result


def create_merge_operation_log(**kwargs: Any) -> TagOperationLog:
    """Create a TagOperationLog for a merge operation.

    Parameters
    ----------
    **kwargs : Any
        Override any TagOperationLog fields.

    Returns
    -------
    TagOperationLog
        A TagOperationLog instance configured for a merge operation.
    """
    source_id = uuid7()
    target_id = uuid7()
    alias_id = uuid7()
    defaults: Dict[str, Any] = {
        "operation_type": "merge",
        "source_canonical_ids": [str(source_id)],
        "target_canonical_id": target_id,
        "affected_alias_ids": [str(alias_id)],
        "reason": "Duplicate tags identified during normalization",
        "performed_by": "system",
    }
    defaults.update(kwargs)
    result = TagOperationLogFactory.build(**defaults)
    assert isinstance(result, TagOperationLog)
    return result


def create_split_operation_log(**kwargs: Any) -> TagOperationLog:
    """Create a TagOperationLog for a split operation.

    Parameters
    ----------
    **kwargs : Any
        Override any TagOperationLog fields.

    Returns
    -------
    TagOperationLog
        A TagOperationLog instance configured for a split operation.
    """
    source_id = uuid7()
    defaults: Dict[str, Any] = {
        "operation_type": "split",
        "source_canonical_ids": [str(source_id)],
        "reason": "Tag split into more specific variants",
        "performed_by": "admin",
    }
    defaults.update(kwargs)
    result = TagOperationLogFactory.build(**defaults)
    assert isinstance(result, TagOperationLog)
    return result


# Common test data patterns
class TagOperationLogTestData:
    """Common test data patterns for TagOperationLog models."""

    VALID_OPERATION_TYPES = [
        "merge",
        "split",
        "rename",
        "delete",
        "create",
    ]

    VALID_PERFORMED_BY = [
        "system",
        "admin",
        "user_123",
        "backfill_script",
    ]

    @classmethod
    def valid_operation_log_data(cls) -> Dict[str, Any]:
        """Get valid tag operation log data."""
        return {
            "operation_type": "create",
            "source_canonical_ids": [],
            "target_canonical_id": None,
            "affected_alias_ids": [],
            "reason": None,
            "performed_by": "system",
            "rollback_data": {},
            "rolled_back": False,
            "rolled_back_at": None,
        }

    @classmethod
    def merge_operation_data(cls) -> Dict[str, Any]:
        """Get data for a merge operation."""
        source_id = uuid7()
        target_id = uuid7()
        return {
            "operation_type": "merge",
            "source_canonical_ids": [str(source_id)],
            "target_canonical_id": target_id,
            "affected_alias_ids": [],
            "reason": "Duplicate canonical tags",
            "performed_by": "system",
            "rollback_data": {
                "original_canonical_form": "Python3",
                "original_normalized_form": "python3",
            },
            "rolled_back": False,
            "rolled_back_at": None,
        }
