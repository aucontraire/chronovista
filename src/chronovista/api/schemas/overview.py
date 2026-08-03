"""Overview dashboard response schemas (Feature 061).

Read-only aggregates over the library: the Saved & Forgotten headline, Watch
Later depth, a playlist inventory by type, and library-wide rollups. Every
figure comes from one aggregation source (FR-026) so the cards cannot disagree
with each other.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class PlaylistTypeCount(BaseModel):
    """One row of the playlist inventory.

    Produced by grouping over the playlist types **actually present in the
    data**, never by iterating a fixed list of known types (FR-021). That is
    deliberate: Saved & Forgotten hardcodes ``curated == 'regular'``, so a
    playlist type introduced later is silently excluded from it, and this
    inventory is the only place such a type becomes visible. Rendering a fixed
    set of types would remove the sole signal that the curated definition has
    gone stale.
    """

    model_config = ConfigDict(strict=True)

    playlist_type: str = Field(..., description="Playlist type as stored")
    playlist_count: int = Field(..., description="Number of playlists of this type")
    is_system: bool = Field(
        ...,
        description=(
            "Whether this is a system list rather than user curation. Derived as "
            "'type is not regular', never from a named set, so a liked or "
            "favorites playlist is never presented as user-curated."
        ),
    )


class WatchLaterDepth(BaseModel):
    """How much is queued in Watch Later, and how much of it is unwatched."""

    model_config = ConfigDict(strict=True)

    total: int = Field(..., description="Distinct videos in Watch Later")
    unwatched: int = Field(
        ..., description="Of those, distinct videos with no watch-history record"
    )
    playlist_id: str | None = Field(
        None,
        description=(
            "Target for the FR-025 deep link, present only when exactly one "
            "Watch Later playlist exists. Null when the depth spans several, "
            "since no single playlist would match the figure clicked."
        ),
    )


class LibraryRollup(BaseModel):
    """Library-wide totals.

    ``saved_curated_videos`` counts what is *saved*; ``watched_videos`` counts
    what has been *watched*. They are independent facts and the labelling must
    keep them so (FR-024).
    """

    model_config = ConfigDict(strict=True)

    watched_videos: int = Field(
        ..., description="Distinct videos with a watch-history record"
    )
    saved_curated_videos: int = Field(
        ..., description="Distinct videos saved across curated playlists"
    )
    liked_videos: int = Field(
        ...,
        description=(
            "Distinct videos carrying the liked attribute. A video attribute, "
            "not a playlist type — presented among the video rollups and never "
            "in the playlist inventory."
        ),
    )


class OverviewResponse(BaseModel):
    """Everything the Overview Dashboard displays."""

    model_config = ConfigDict(strict=True)

    saved_and_forgotten: int = Field(
        ...,
        description=(
            "Distinct videos in at least one curated playlist with no "
            "watch-history record. Counted once per video however many curated "
            "playlists hold it."
        ),
    )
    watch_later: WatchLaterDepth | None = Field(
        ...,
        description=(
            "Watch Later depth, or null when no Watch Later playlist exists. "
            "Null is distinct from a present-but-empty queue, which is "
            "{total: 0, unwatched: 0} (FR-020a)."
        ),
    )
    playlist_inventory: list[PlaylistTypeCount] = Field(
        ..., description="Counts for the playlist types present in the data"
    )
    rollup: LibraryRollup = Field(..., description="Library-wide totals")
