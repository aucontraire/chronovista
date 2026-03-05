"""
Pydantic V2 models for batch transcript correction results.

This module provides immutable result models for Feature 036 batch correction
operations, including find-replace results, export records, pattern discovery,
and aggregate statistics.

All result models use ``ConfigDict(frozen=True)`` to enforce immutability,
since they represent computed outputs that should not be mutated after creation.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class TypeCount(BaseModel):
    """Breakdown row for correction_type statistics.

    Represents a single row in the ``by_type`` aggregate, pairing a
    correction type string with its occurrence count.

    Attributes
    ----------
    correction_type : str
        The correction type label (e.g. ``"spelling"``, ``"asr_error"``).
    count : int
        Number of corrections of this type (must be >= 0).
    """

    correction_type: str = Field(
        ...,
        description="The correction type label (e.g. 'spelling', 'asr_error')",
    )
    count: int = Field(
        ...,
        ge=0,
        description="Number of corrections of this type",
    )

    model_config = ConfigDict(frozen=True)


class VideoCount(BaseModel):
    """Row for most-corrected videos ranking.

    Represents a single entry in the ``top_videos`` aggregate, identifying
    a video and its correction count.

    Attributes
    ----------
    video_id : str
        YouTube video ID.
    title : str | None
        Video title, or ``None`` if the title has not been loaded.
    count : int
        Number of corrections for this video (must be >= 0).
    """

    video_id: str = Field(
        ...,
        description="YouTube video ID",
    )
    title: str | None = Field(
        default=None,
        description="Video title (may be None if not loaded)",
    )
    count: int = Field(
        ...,
        ge=0,
        description="Number of corrections for this video",
    )

    model_config = ConfigDict(frozen=True)


class BatchCorrectionResult(BaseModel):
    """Result of a find-replace or batch-revert operation.

    Captures the full outcome of a batch correction pass, including how many
    segments were scanned, matched, applied, skipped, and failed.

    Attributes
    ----------
    total_scanned : int
        Total segments within filter scope (before pattern matching).
    total_matched : int
        Segments matching the search pattern.
    total_applied : int
        Corrections successfully applied.
    total_skipped : int
        No-ops where the segment was already correct.
    total_failed : int
        Errors encountered during apply.
    failed_batches : int
        Transaction batches that failed entirely.
    unique_videos : int
        Distinct video_ids affected by the operation.
    """

    total_scanned: int = Field(
        ...,
        ge=0,
        description="Total segments within filter scope (before pattern matching)",
    )
    total_matched: int = Field(
        ...,
        ge=0,
        description="Segments matching the search pattern",
    )
    total_applied: int = Field(
        ...,
        ge=0,
        description="Corrections successfully applied",
    )
    total_skipped: int = Field(
        ...,
        ge=0,
        description="No-ops where the segment was already correct",
    )
    total_failed: int = Field(
        ...,
        ge=0,
        description="Errors encountered during apply",
    )
    failed_batches: int = Field(
        ...,
        ge=0,
        description="Transaction batches that failed entirely",
    )
    unique_videos: int = Field(
        ...,
        ge=0,
        description="Distinct video_ids affected by the operation",
    )

    model_config = ConfigDict(frozen=True)


class CorrectionExportRecord(BaseModel):
    """Flat record for CSV/JSON export of a single correction.

    All fields are serialised as strings or primitives suitable for
    tabular export. The ``id`` is a UUID rendered as a string, and
    ``corrected_at`` is an ISO 8601 datetime string.

    Attributes
    ----------
    id : str
        Correction UUID as a string.
    video_id : str
        YouTube video ID.
    language_code : str
        BCP-47 language code for the corrected transcript.
    segment_id : int | None
        Optional transcript segment reference.
    correction_type : str
        Category of correction applied.
    original_text : str
        Original transcript text before correction.
    corrected_text : str
        Corrected transcript text after applying the correction.
    correction_note : str | None
        Optional human-readable explanation for the correction.
    corrected_by_user_id : str | None
        Identifier of the user who made the correction.
    corrected_at : str
        ISO 8601 datetime string when the correction was recorded.
    version_number : int
        Version number of this correction (must be >= 1).
    """

    id: str = Field(
        ...,
        description="Correction UUID as a string",
    )
    video_id: str = Field(
        ...,
        description="YouTube video ID",
    )
    language_code: str = Field(
        ...,
        description="BCP-47 language code for the corrected transcript",
    )
    segment_id: int | None = Field(
        default=None,
        description="Optional transcript segment reference",
    )
    correction_type: str = Field(
        ...,
        description="Category of correction applied",
    )
    original_text: str = Field(
        ...,
        description="Original transcript text before correction",
    )
    corrected_text: str = Field(
        ...,
        description="Corrected transcript text after applying the correction",
    )
    correction_note: str | None = Field(
        default=None,
        description="Optional human-readable explanation for the correction",
    )
    corrected_by_user_id: str | None = Field(
        default=None,
        description="Identifier of the user who made the correction",
    )
    corrected_at: str = Field(
        ...,
        description="ISO 8601 datetime string when the correction was recorded",
    )
    version_number: int = Field(
        ...,
        ge=1,
        description="Version number of this correction (must be >= 1)",
    )

    model_config = ConfigDict(frozen=True)


class CorrectionPattern(BaseModel):
    """Result row for correction pattern discovery.

    Represents a recurring original-to-corrected text transformation
    that has been applied multiple times, along with how many un-corrected
    instances remain.

    Attributes
    ----------
    original_text : str
        The original (incorrect) text pattern.
    corrected_text : str
        The corrected text that replaced the original.
    occurrences : int
        Number of times this correction has been applied (must be >= 0).
    remaining_matches : int
        Number of remaining segments that still contain the original text
        (must be >= 0).
    """

    original_text: str = Field(
        ...,
        description="The original (incorrect) text pattern",
    )
    corrected_text: str = Field(
        ...,
        description="The corrected text that replaced the original",
    )
    occurrences: int = Field(
        ...,
        ge=0,
        description="Number of times this correction has been applied",
    )
    remaining_matches: int = Field(
        ...,
        ge=0,
        description="Number of remaining segments still containing the original text",
    )

    model_config = ConfigDict(frozen=True)


class CorrectionStats(BaseModel):
    """Aggregate correction statistics.

    Provides a high-level summary of all corrections, including totals,
    breakdowns by correction type, and a ranking of the most-corrected videos.

    Attributes
    ----------
    total_corrections : int
        Total number of corrections excluding reverts (must be >= 0).
    total_reverts : int
        Total number of revert operations (must be >= 0).
    unique_segments : int
        Number of distinct segments that have been corrected (must be >= 0).
    unique_videos : int
        Number of distinct videos with corrections (must be >= 0).
    by_type : list[TypeCount]
        Breakdown of corrections by type.
    top_videos : list[VideoCount]
        Ranking of the most-corrected videos.
    """

    total_corrections: int = Field(
        ...,
        ge=0,
        description="Total number of corrections excluding reverts",
    )
    total_reverts: int = Field(
        ...,
        ge=0,
        description="Total number of revert operations",
    )
    unique_segments: int = Field(
        ...,
        ge=0,
        description="Number of distinct segments that have been corrected",
    )
    unique_videos: int = Field(
        ...,
        ge=0,
        description="Number of distinct videos with corrections",
    )
    by_type: list[TypeCount] = Field(
        default_factory=list,
        description="Breakdown of corrections by type",
    )
    top_videos: list[VideoCount] = Field(
        default_factory=list,
        description="Ranking of the most-corrected videos",
    )

    model_config = ConfigDict(frozen=True)


__all__ = [
    "TypeCount",
    "VideoCount",
    "BatchCorrectionResult",
    "CorrectionExportRecord",
    "CorrectionPattern",
    "CorrectionStats",
]
