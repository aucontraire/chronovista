"""
Canonical local-user identity models (Feature 060).

The application resolves *who the local user is* exactly once and persists that
identity in a singleton database row (``app_identities``). Every writer and
reader of user-scoped data obtains its ``user_id`` from this identity rather
than deriving it from ambient auth state or a hardcoded literal.

See ``specs/060-canonical-user-identity`` for the full rationale.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from .youtube_types import UserId

# The documented offline fallback identity, used when no YouTube channel can be
# resolved. It is a valid ``UserId`` and fits the ``app_identities.user_id`` /
# ``user_videos.user_id`` column width (varchar(50)). Once persisted it is final
# and is never promoted; ``identity reset`` folds it into a real channel later.
LOCAL_USER_ID: UserId = "local_user"


class AppIdentitySource(str, Enum):
    """How the canonical identity was resolved."""

    CHANNEL = "channel"
    LOCAL_CONSTANT = "local_constant"


class AppIdentityBase(BaseModel):
    """Base model for the canonical local-user identity."""

    user_id: UserId = Field(..., description="The canonical local-user identifier")
    source: AppIdentitySource = Field(
        ..., description="How the identity was resolved (channel or local constant)"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )


class AppIdentityCreate(AppIdentityBase):
    """Model for establishing the canonical identity for the first time."""

    pass


class AppIdentityUpdate(BaseModel):
    """Model for updating the canonical identity (used only by ``identity reset``)."""

    user_id: UserId | None = None
    source: AppIdentitySource | None = None

    model_config = ConfigDict(
        validate_assignment=True,
    )


class IdentityInvariants(BaseModel):
    """Integrity totals over ``user_videos`` compared before/after the repair.

    All three are computed **per distinct video** so they are invariant under the
    merge's ``GREATEST``/``OR`` collapse of rows that share a ``video_id`` — a raw
    row/sum aggregate would over-count a video present under two identities and
    falsely trip the regression guard on an otherwise-lossless merge.
    """

    distinct_watched_videos: int  # distinct videos with a watch timestamp
    liked_count: int  # distinct videos liked on any row
    rewatch_sum: int  # sum of the per-video max rewatch_count


class MergeStats(BaseModel):
    """Row-level outcome of merging one placeholder identity into the survivor."""

    merged: int
    deleted: int
    rekeyed: int


class AppIdentity(AppIdentityBase):
    """Full canonical-identity model with row id and timestamps."""

    id: int = Field(..., description="Singleton row id (always 1)")
    created_at: datetime = Field(..., description="When the identity was established")
    updated_at: datetime = Field(..., description="When the identity was last changed")

    model_config = ConfigDict(
        from_attributes=True,
        validate_assignment=True,
    )
