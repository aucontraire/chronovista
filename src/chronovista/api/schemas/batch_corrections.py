"""Batch correction API request/response schemas.

This module defines Pydantic V2 models for the batch corrections API endpoints,
including preview, apply, and rebuild-text operations.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class BatchPreviewRequest(BaseModel):
    """Request body for POST /batch-corrections/preview.

    Describes the find-replace pattern and optional scope filters
    used to preview matching segments before applying corrections.

    Attributes
    ----------
    pattern : str
        The search pattern (literal string or regex).
    replacement : str
        The replacement text. Empty string is allowed for deletion.
    is_regex : bool
        Whether the pattern should be interpreted as a regular expression.
    case_insensitive : bool
        Whether matching should ignore case.
    cross_segment : bool
        Whether to match patterns that span across segment boundaries.
    language : str | None
        Optional language code filter (e.g. 'en', 'es').
    channel_id : str | None
        Optional channel ID to restrict the search scope.
    video_ids : list[str] | None
        Optional list of video IDs to restrict the search scope (max 50).
    """

    model_config = ConfigDict(strict=True, str_strip_whitespace=True)

    pattern: str = Field(
        ..., min_length=1, max_length=500, description="Search pattern"
    )
    replacement: str = Field(
        ..., max_length=2000, description="Replacement text (empty string for deletion)"
    )
    is_regex: bool = Field(default=False, description="Interpret pattern as regex")
    case_insensitive: bool = Field(
        default=False, description="Case-insensitive matching"
    )
    cross_segment: bool = Field(
        default=False, description="Match across segment boundaries"
    )
    language: str | None = Field(
        default=None, description="Optional language code filter"
    )
    channel_id: str | None = Field(
        default=None, description="Optional channel ID filter"
    )
    video_ids: list[str] | None = Field(
        default=None, description="Optional video ID filter (max 50)"
    )

    @field_validator("video_ids")
    @classmethod
    def validate_video_ids_length(
        cls, v: list[str] | None,
    ) -> list[str] | None:
        """Ensure video_ids list does not exceed 50 items.

        Parameters
        ----------
        v : list[str] | None
            The video IDs list to validate.

        Returns
        -------
        list[str] | None
            The validated list.

        Raises
        ------
        ValueError
            If the list exceeds 50 items.
        """
        if v is not None and len(v) > 50:
            raise ValueError("video_ids must contain at most 50 items")
        return v


class BatchPreviewMatch(BaseModel):
    """A single match result in the batch preview response.

    Attributes
    ----------
    segment_id : int
        The database ID of the matched segment.
    video_id : str
        The YouTube video ID containing the segment.
    video_title : str
        Title of the video.
    channel_title : str
        Title of the channel.
    language_code : str
        Language code of the transcript.
    start_time : float
        Segment start time in seconds.
    current_text : str
        The current segment text.
    proposed_text : str
        The text after applying the replacement.
    match_start : int
        Character offset where the match starts in current_text.
    match_end : int
        Character offset where the match ends in current_text.
    context_before : str | None
        Text from the preceding segment for context.
    context_after : str | None
        Text from the following segment for context.
    has_existing_correction : bool
        Whether this segment already has a correction applied.
    is_cross_segment : bool
        Whether this match spans across segment boundaries.
    pair_id : str | None
        Identifier linking paired cross-segment matches.
    deep_link_url : str
        URL to view this segment in context.
    """

    model_config = ConfigDict(strict=True, from_attributes=True)

    segment_id: int
    video_id: str
    video_title: str
    channel_title: str
    language_code: str
    start_time: float
    current_text: str
    proposed_text: str
    match_start: int
    match_end: int
    context_before: str | None
    context_after: str | None
    has_existing_correction: bool
    is_cross_segment: bool
    pair_id: str | None
    deep_link_url: str


class BatchPreviewResponse(BaseModel):
    """Response envelope for the batch preview endpoint.

    Attributes
    ----------
    matches : list[BatchPreviewMatch]
        List of matching segments with proposed replacements.
    total_count : int
        Total number of matches found.
    pattern : str
        The search pattern that was used.
    replacement : str
        The replacement text that was used.
    is_regex : bool
        Whether the pattern was interpreted as regex.
    case_insensitive : bool
        Whether case-insensitive matching was used.
    cross_segment : bool
        Whether cross-segment matching was enabled.
    """

    model_config = ConfigDict(strict=True)

    matches: list[BatchPreviewMatch]
    total_count: int
    pattern: str
    replacement: str
    is_regex: bool
    case_insensitive: bool
    cross_segment: bool


class BatchApplyRequest(BaseModel):
    """Request body for POST /batch-corrections/apply.

    Applies the find-replace pattern to a specific set of segment IDs
    previously identified through the preview endpoint.

    Attributes
    ----------
    pattern : str
        The search pattern (must match what was used in preview).
    replacement : str
        The replacement text. Empty string allowed for deletion.
    is_regex : bool
        Whether the pattern should be interpreted as a regular expression.
    case_insensitive : bool
        Whether matching should ignore case.
    cross_segment : bool
        Whether to match patterns that span across segment boundaries.
    segment_ids : list[int]
        Segment IDs to apply corrections to (1-200 items).
    correction_type : str
        The type of correction being applied.
    correction_note : str | None
        Optional note explaining the correction (max 500 chars).
    auto_rebuild : bool
        Whether to automatically rebuild full text after applying.
    """

    model_config = ConfigDict(strict=True, str_strip_whitespace=True)

    pattern: str = Field(
        ..., min_length=1, max_length=500, description="Search pattern"
    )
    replacement: str = Field(
        ..., max_length=2000, description="Replacement text (empty string for deletion)"
    )
    is_regex: bool = Field(default=False, description="Interpret pattern as regex")
    case_insensitive: bool = Field(
        default=False, description="Case-insensitive matching"
    )
    cross_segment: bool = Field(
        default=False, description="Match across segment boundaries"
    )
    segment_ids: list[int] = Field(
        ..., description="Segment IDs to apply corrections to (1-200 items)"
    )
    correction_type: str = Field(
        default="proper_noun", description="Type of correction"
    )
    correction_note: str | None = Field(
        default=None, max_length=500, description="Optional correction note"
    )
    auto_rebuild: bool = Field(
        default=True, description="Auto-rebuild full text after applying"
    )

    @field_validator("segment_ids")
    @classmethod
    def validate_segment_ids_length(cls, v: list[int]) -> list[int]:
        """Ensure segment_ids list has between 1 and 200 items.

        Parameters
        ----------
        v : list[int]
            The segment IDs list to validate.

        Returns
        -------
        list[int]
            The validated list.

        Raises
        ------
        ValueError
            If the list is empty or exceeds 200 items.
        """
        if len(v) < 1:
            raise ValueError("segment_ids must contain at least 1 item")
        if len(v) > 200:
            raise ValueError("segment_ids must contain at most 200 items")
        return v


class BatchApplyResult(BaseModel):
    """Response for the batch apply endpoint.

    Attributes
    ----------
    total_applied : int
        Number of corrections successfully applied.
    total_skipped : int
        Number of segments skipped (e.g. no match found).
    total_failed : int
        Number of segments that failed to apply.
    failed_segment_ids : list[int]
        IDs of segments that failed.
    affected_video_ids : list[str]
        Video IDs that had corrections applied.
    rebuild_triggered : bool
        Whether auto-rebuild was triggered for affected videos.
    """

    model_config = ConfigDict(strict=True, from_attributes=True)

    total_applied: int
    total_skipped: int
    total_failed: int
    failed_segment_ids: list[int]
    affected_video_ids: list[str]
    rebuild_triggered: bool


class BatchRebuildRequest(BaseModel):
    """Request body for POST /batch-corrections/rebuild-text.

    Triggers a full-text rebuild for the specified videos.

    Attributes
    ----------
    video_ids : list[str]
        Video IDs to rebuild full text for (1-50 items).
    """

    model_config = ConfigDict(strict=True, str_strip_whitespace=True)

    video_ids: list[str] = Field(
        ..., description="Video IDs to rebuild (1-50 items)"
    )

    @field_validator("video_ids")
    @classmethod
    def validate_video_ids_length(cls, v: list[str]) -> list[str]:
        """Ensure video_ids list has between 1 and 50 items.

        Parameters
        ----------
        v : list[str]
            The video IDs list to validate.

        Returns
        -------
        list[str]
            The validated list.

        Raises
        ------
        ValueError
            If the list is empty or exceeds 50 items.
        """
        if len(v) < 1:
            raise ValueError("video_ids must contain at least 1 item")
        if len(v) > 50:
            raise ValueError("video_ids must contain at most 50 items")
        return v


class BatchRebuildResult(BaseModel):
    """Response for the rebuild-text endpoint.

    Attributes
    ----------
    videos_rebuilt : int
        Number of videos successfully rebuilt.
    video_ids : list[str]
        IDs of videos that were rebuilt.
    failed_video_ids : list[str]
        IDs of videos that failed to rebuild.
    """

    model_config = ConfigDict(strict=True, from_attributes=True)

    videos_rebuilt: int
    video_ids: list[str]
    failed_video_ids: list[str]
