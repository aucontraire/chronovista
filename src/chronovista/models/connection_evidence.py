"""Domain models for the connection-explorer evidence panel (Features 114, 118).

These are Pydantic V2 *domain* models (not API schemas) so the repository can return them and the
API router can reuse them as a ``response_model`` without importing the API layer — matching the
``graph_connection`` house style (``ConfigDict(strict=True)``, ``computed_field``, ``model_validator``).

The panel is read-only: given two entity ids, it shows the discussion passages where they are
mentioned close together, built from the Feature 117 proximity records (``PairPassages``). Mentions
are only ever paired within one transcript language; languages are variants of a passage, never
extra evidence.
"""

from __future__ import annotations

import uuid
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

# The six detection methods permitted by the ``entity_mentions.detection_method`` CHECK constraint
# (``db/models.py``). Kept as a Literal so a drifted value fails at the boundary; a same-PR fitness
# guard keeps this list and the DB CHECK in lockstep.
DetectionMethod = Literal[
    "rule_match",
    "spacy_ner",
    "llm_extraction",
    "manual",
    "user_correction",
    "asr_match",
]

# The non-transcript co-occurrence sources the empty-state names (``_PROVENANCE_SOURCES`` minus
# ``transcript``). A Literal so the panel can never surface ``transcript`` as a "no passage" basis.
NonTranscriptBasis = Literal["title", "description", "tag", "manual"]


class MentionRef(BaseModel):
    """One matched mention within a specific transcript segment.

    Attributes
    ----------
    segment_id : int
        The start-anchor ``transcript_segments.id``.
    end_segment_id : int | None
        Last segment of a cross-segment mention; ``None`` when contained within ``segment_id``.
    language_code : str
        The transcript language this mention was matched in.
    sequence_number : int
        Per-(video, language) ordering of the start-anchor segment; basis of the separation metric.
    start_time : float
        Seconds offset of the start-anchor segment.
    mention_text : str
        The matched surface form (``entity_mentions.mention_text``).
    match_start, match_end : int | None
        Character offsets of the match within the segment text (for in-passage highlighting).
    detection_method : DetectionMethod
        Provenance of the match.
    """

    model_config = ConfigDict(strict=True)

    segment_id: int
    end_segment_id: int | None = None
    language_code: str
    sequence_number: int
    start_time: float
    mention_text: str
    match_start: int | None = None
    match_end: int | None = None
    detection_method: DetectionMethod


# --- Discussion passages (Feature 118) ---------------------------------------------------------
# Built from the Feature 117 proximity records, so the videos the panel shows are, by construction,
# the videos the measurement reports for the same pair and window.

# Version of the passage-grouping rule (chaining within a language, then cross-language grouping).
# The rule itself is documented where it runs: ``proximity_service.chain_passages``.
PASSAGE_RULE_VERSION = "118.0"

# A sustained passage can hold thousands of co-mentions; the response lists the first this many
# other moments by time (``co_mention_count`` keeps the true total).
OTHER_MOMENTS_LIMIT = 50

ProximityWindow = Literal[15, 30, 60, 120]
PROXIMITY_WINDOWS: tuple[ProximityWindow, ...] = (15, 30, 60, 120)

PairPassagesState = Literal[
    "passages", "not_computed", "no_transcript", "no_passage_in_window"
]


class CoMoment(BaseModel):
    """One co-mention of a passage, by time only (a passage's "other moments", FR-004)."""

    model_config = ConfigDict(strict=True)

    start_time: float = Field(ge=0)
    gap_seconds: float = Field(ge=0)


class PassageSegment(BaseModel):
    """One transcript segment of a rendered passage, in effective (corrected-or-raw) text.

    ``is_context`` marks the segment after a mention: shown as reading context, never counted.
    ``sequence_number`` is the segment's position in its transcript, so a reader can tell where
    shown segments are not adjacent and mark the omitted text.
    """

    model_config = ConfigDict(strict=True)

    segment_id: int
    sequence_number: int = Field(ge=0)
    start_time: float
    text: str = Field(min_length=1)
    is_context: bool = False


class PassageMoment(BaseModel):
    """A passage's closest co-mention, rendered with its text (FR-003).

    ``mention_a`` and ``mention_b`` are oriented to the request's ``a`` and ``b``, whatever order the
    proximity records store the pair in. ``segment_id`` and ``start_time`` are the deep-link target:
    the earlier of the two mentions' start segments.
    """

    model_config = ConfigDict(strict=True)

    gap_seconds: float = Field(ge=0)
    start_time: float = Field(ge=0)
    segment_id: int
    mention_a: MentionRef
    mention_b: MentionRef
    segments: list[PassageSegment] = Field(min_length=1, max_length=6)


class LanguagePassage(BaseModel):
    """Co-mentions in one video and language, merged by the chaining rule (FR-001)."""

    model_config = ConfigDict(strict=True)

    language_code: str
    start_time: float = Field(ge=0)
    end_time: float = Field(ge=0)
    co_mention_count: int = Field(ge=1)
    closest_gap_seconds: float = Field(ge=0)
    closest: PassageMoment
    other_moments: list[CoMoment] = Field(default_factory=list)
    name_list: bool = False

    @model_validator(mode="after")
    def _check_moments(self) -> Self:
        if self.start_time > self.end_time:
            raise ValueError(
                f"passage starts after it ends ({self.start_time} > {self.end_time})"
            )
        expected = min(self.co_mention_count - 1, OTHER_MOMENTS_LIMIT)
        if len(self.other_moments) != expected:
            raise ValueError(
                f"other_moments must list min(co_mention_count - 1, {OTHER_MOMENTS_LIMIT}) "
                f"moments ({expected}), got {len(self.other_moments)}"
            )
        if self.closest.gap_seconds != self.closest_gap_seconds:
            raise ValueError(
                "closest_gap_seconds must be the rendered closest moment's gap "
                f"({self.closest_gap_seconds} != {self.closest.gap_seconds})"
            )
        return self


class GroupedPassage(BaseModel):
    """Overlapping language passages of one video: the unit the summary counts (FR-011, FR-012).

    ``variants[0]`` leads (the reviewer's preferred language, else the closest; FR-011a). A
    language can appear twice when its own passages split inside the group. The closest gap is
    over every variant, so it does not depend on which variant leads.
    """

    model_config = ConfigDict(strict=True)

    start_time: float = Field(ge=0)
    end_time: float = Field(ge=0)
    closest_gap_seconds: float = Field(ge=0)
    variants: list[LanguagePassage] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_group(self) -> Self:
        if self.closest_gap_seconds != min(
            v.closest_gap_seconds for v in self.variants
        ):
            raise ValueError(
                "GroupedPassage.closest_gap_seconds must be the minimum over its variants"
            )
        if self.start_time != min(v.start_time for v in self.variants) or (
            self.end_time != max(v.end_time for v in self.variants)
        ):
            raise ValueError(
                "GroupedPassage range must be the union of its variants' ranges"
            )
        return self


class VideoPassages(BaseModel):
    """One video's grouped passages, in time order; all of them (the client folds after 3)."""

    model_config = ConfigDict(strict=True)

    video_id: str
    video_title: str | None = None
    channel_title: str | None = None
    closest_gap_seconds: float = Field(ge=0)
    passages: list[GroupedPassage] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_video(self) -> Self:
        if self.closest_gap_seconds != min(
            p.closest_gap_seconds for p in self.passages
        ):
            raise ValueError(
                "VideoPassages.closest_gap_seconds must be the minimum over all its "
                "passages, folded or not (FR-014a)"
            )
        starts = [p.start_time for p in self.passages]
        if starts != sorted(starts):
            raise ValueError("a video's passages must be in time order (FR-014)")
        return self


class FailedScope(BaseModel):
    """A transcript Feature 117 reports as failing, listed so the reviewer can see it (FR-015a)."""

    model_config = ConfigDict(strict=True)

    video_id: str
    language_code: str
    video_title: str | None = None
    channel_title: str | None = None


class FartherVideo(BaseModel):
    """A video where both entities are spoken, but never within the window (FR-010)."""

    model_config = ConfigDict(strict=True)

    video_id: str
    video_title: str | None = None
    channel_title: str | None = None
    language_code: str
    # > window when every transcript the pair depends on is current. While one is pending or has
    # failed, its records can lag its mentions, so this is only bounded below by 0; the panel then
    # shows the "updating" or "could not be computed" note.
    nearest_gap_seconds: float = Field(ge=0)
    nearest_start_time: float = Field(ge=0)


class PairPassages(BaseModel):
    """A pair's discussion passages for one window (the passages response root, Feature 118).

    The counts cover every video in the window, never just the page, and do not depend on paging,
    on the order the two entities are given in, or on language preferences (FR-013, FR-013a).
    ``state`` is the one outcome the panel shows, decided in the order of FR-015b.
    """

    model_config = ConfigDict(strict=True)

    entity_a_id: uuid.UUID
    entity_b_id: uuid.UUID
    window_seconds: ProximityWindow
    passage_rule_version: str = PASSAGE_RULE_VERSION
    items: list[VideoPassages] = Field(default_factory=list)
    offset: int = Field(default=0, ge=0)
    video_count: int = Field(default=0, ge=0)
    passage_count: int = Field(default=0, ge=0)
    channel_count: int = Field(default=0, ge=0)
    closest_gap_seconds: float | None = None
    farther_video_count: int = Field(default=0, ge=0)
    pending_scopes: int = Field(default=0, ge=0)
    failed_scopes: list[FailedScope] = Field(default_factory=list)
    state: PairPassagesState
    basis_when_empty: NonTranscriptBasis | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def returned(self) -> int:
        """Number of videos on this page (derived)."""
        return len(self.items)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def truncated(self) -> bool:
        """Whether more videos remain after this page (offset-aware)."""
        return self.offset + self.returned < self.video_count

    @model_validator(mode="after")
    def _check_counts_and_state(self) -> Self:
        if (self.state == "passages") != (self.video_count > 0):
            raise ValueError(
                f"state {self.state!r} contradicts video_count={self.video_count}"
            )
        if self.passage_count < self.video_count:
            raise ValueError(
                f"passage_count ({self.passage_count}) cannot be less than "
                f"video_count ({self.video_count})"
            )
        if self.returned > 0 and self.offset + self.returned > self.video_count:
            raise ValueError(
                f"offset ({self.offset}) + returned ({self.returned}) cannot exceed "
                f"video_count ({self.video_count})"
            )
        if self.basis_when_empty is not None and self.state != "no_transcript":
            raise ValueError("basis_when_empty is only set with state 'no_transcript'")
        if (self.closest_gap_seconds is None) != (self.video_count == 0):
            raise ValueError(
                "closest_gap_seconds is None exactly when video_count == 0"
            )
        return self


class FartherVideos(BaseModel):
    """One page of the farther-apart list, nearest-first (FR-010)."""

    model_config = ConfigDict(strict=True)

    items: list[FartherVideo] = Field(default_factory=list)
    offset: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def returned(self) -> int:
        """Number of videos on this page (derived)."""
        return len(self.items)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def truncated(self) -> bool:
        """Whether more videos remain after this page (offset-aware)."""
        return self.offset + self.returned < self.total
