"""Domain models for the connection-explorer transcript-evidence panel (Feature 114).

These are Pydantic V2 *domain* models (not API schemas) so the repository can return them and the
API router can reuse them as a ``response_model`` without importing the API layer — matching the
``graph_connection`` house style (``ConfigDict(strict=True)``, ``computed_field``, ``model_validator``).

The feature is read-only: given two entity ids, it renders the transcript passages where they
co-occur. The panel's row is grained by **video** (``EvidenceItem``) — because the audit action a
reviewer takes, excluding a false mention, is keyed ``(entity, video)`` with no language. Beneath the
row, each co-occurrence is grained by **(video, language)** (``EvidenceVariant``): a video's strongest
co-mention is its ``representative``, and the pair's co-occurrence in the video's *other* transcript
languages are ``other_language_variants`` (the expander). Pairing mentions across two languages would
fabricate a co-occurrence no reader could verify, so the minimum-separation pair inside a variant is
always drawn from one language (FR-017). The *mention-side* of that invariant is enforced here by
``EvidenceVariant``'s validator; the *segment-side* (the query never joins segments across languages)
is held by the architecture guard in ``tests/unit/architecture/``.

Passages are **per-mention** (research D9, FR-015): the minimum-separation pair's two mentions are
often far apart (measured median ~228 segments), so a variant carries one bounded passage window when
the mentions are close enough to share one, or two windows (one around each mention) when they are
not — never a single joint window spanning a gap, which would be unbounded or clip a mention.
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

    Carries ``language_code`` (denormalized from the variant) so ``EvidenceVariant`` can prove both
    of its mentions share the variant's language at the serialization boundary (FR-017).

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


class Passage(BaseModel):
    """A bounded, ordered run of transcript segments rendered as prose.

    Attributes
    ----------
    text : str
        The effective (corrected-or-raw) text of the window, as prose.
    start_time : float
        Seconds offset of the window's lead segment (the deep-link ``t`` target).
    segment_id : int
        The window's lead segment id (the deep-link ``seg`` target / scroll anchor).
    """

    model_config = ConfigDict(strict=True)

    text: str
    start_time: float
    segment_id: int

    @model_validator(mode="after")
    def _non_empty(self) -> Self:
        if not self.text:
            raise ValueError("Passage.text must be non-empty")
        return self


class EvidenceVariant(BaseModel):
    """One co-occurrence grained by **(video, language)** — the min-separation pair in one language.

    An :class:`EvidenceItem` carries the video's strongest such variant as its ``representative`` and
    the rest as ``other_language_variants`` (the expander), so a surface form that differs by
    language — a different match with a different false-positive risk — stays visible instead of being
    collapsed away.

    Attributes
    ----------
    language_code : str
        The transcript language this variant is scoped to.
    mention_a, mention_b : MentionRef
        The minimum-separation mention pair (A and B), both in ``language_code``.
    separation_segments : int
        ``abs(a.sequence_number - b.sequence_number)`` — **computed** from the two mentions (FR-015),
        so it can never disagree with the mentions it summarizes.
    passages : list[Passage]
        One window when the two mentions are close enough to share it; otherwise two (one per
        mention). Never empty.
    """

    model_config = ConfigDict(strict=True)

    language_code: str
    mention_a: MentionRef
    mention_b: MentionRef
    passages: list[Passage] = Field(min_length=1, max_length=2)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def separation_segments(self) -> int:
        """Segments between the two mentions (derived from their sequence numbers; FR-015)."""
        return abs(self.mention_a.sequence_number - self.mention_b.sequence_number)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def separation_seconds(self) -> float:
        """Seconds between the two mentions (derived, not stored)."""
        return abs(self.mention_a.start_time - self.mention_b.start_time)

    @model_validator(mode="after")
    def _check_language_grain(self) -> Self:
        """Mention-side of the (video, language) invariant (FR-017).

        The segment-side (the query never joins segments across languages) cannot be proven from a
        passage string and is held by the architecture contract guard. ``separation_segments`` is
        computed from the mentions, so it needs no range check (``abs`` is always ``>= 0``).
        """
        if not (
            self.mention_a.language_code
            == self.mention_b.language_code
            == self.language_code
        ):
            raise ValueError(
                "EvidenceVariant language-grain violation: both mentions and the variant must share "
                f"one language (variant={self.language_code!r}, a={self.mention_a.language_code!r}, "
                f"b={self.mention_b.language_code!r})"
            )
        return self


class EvidenceItem(BaseModel):
    """One co-occurrence grained by **video** (FR-009) — the panel's row and the audit unit.

    The exclusion a reviewer applies is keyed ``(entity, video)`` with no language column, so the
    video is the row. ``representative`` is the video's strongest co-mention (minimum separation
    across the video's co-occurring transcript languages, shown by default);
    ``other_language_variants`` holds the same pair in the video's *other* co-occurring languages,
    ordered closest-first, for the expander.

    Attributes
    ----------
    video_id : str
        The source video (the audit / exclusion grain).
    representative : EvidenceVariant
        The minimum-separation co-occurrence across the video's co-occurring languages.
    other_language_variants : list[EvidenceVariant]
        The co-occurrence in the video's other co-occurring languages; empty for a single-language
        video. Each has a language distinct from ``representative`` and from the others, and none is
        closer than ``representative``.
    video_title, channel_title : str | None
        For display.
    """

    model_config = ConfigDict(strict=True)

    video_id: str
    representative: EvidenceVariant
    other_language_variants: list[EvidenceVariant] = Field(default_factory=list)
    video_title: str | None = None
    channel_title: str | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def cooccurring_language_count(self) -> int:
        """Transcript languages of this video in which the pair co-occurs (1 + the expander count)."""
        return 1 + len(self.other_language_variants)

    @model_validator(mode="after")
    def _check_video_grain(self) -> Self:
        """``representative`` is the min-separation variant, and every variant is a distinct language.

        A violation of either means the by-video grouping went wrong (a language rendered twice, or a
        closer variant left in the expander instead of promoted), so this fails at the boundary.
        """
        langs = [self.representative.language_code] + [
            v.language_code for v in self.other_language_variants
        ]
        if len(set(langs)) != len(langs):
            raise ValueError(
                f"EvidenceItem has duplicate languages across its variants: {langs!r}"
            )
        # Representative is the minimum AND the expander is closest-first: the whole sequence is
        # non-decreasing by separation. (Ties are allowed — "none strictly closer.")
        seps = [self.representative.separation_segments] + [
            v.separation_segments for v in self.other_language_variants
        ]
        if seps != sorted(seps):
            raise ValueError(
                "EvidenceItem variants must be ordered closest-first with the representative the "
                f"minimum (separations {seps!r} are not non-decreasing)"
            )
        return self


class ConnectionEvidence(BaseModel):
    """The transcript evidence behind a pair's co-occurrence (the response root).

    Attributes
    ----------
    entity_a_id, entity_b_id : uuid.UUID
        The queried pair.
    items : list[EvidenceItem]
        One per video, ordered closest-first by the representative variant's separation (FR-016),
        page-bounded. No cross-video collapse: every co-occurring video is its own row (a surface-form
        dedup across videos silently dropped 97-99% of dense pairs — research reversal, FR-016).
    total_available : int
        Distinct co-occurring **videos** (with an in-language co-mention) — the page-able total that
        pagination arithmetic uses (FR-010). The "spoken together" population; narrower than the
        ``/videos`` *any-source* intersection, so the panel labels its denominator rather than
        implying the two counts match.
    raw_cooccurrence_count : int
        Count of co-occurring transcripts ((video, language) pairs with an in-language co-mention):
        ``>= total_available`` because a multilingual video contributes several. With
        ``total_available`` it gives the honest "spoken together in N videos (M transcripts)" framing.
    offset : int
        The page offset these items start at (so ``truncated`` can be computed correctly).
    basis_when_empty : NonTranscriptBasis | None
        Set only on an early return where ``total_available == 0``: names a non-transcript source the
        pair co-occurs through, or ``None`` when the pair does not co-occur at all (FR-012). An empty
        ``items`` with ``total_available > 0`` is a page past the end, **not** "no co-occurrence" — so
        a client distinguishes the two states by ``total_available``, never by ``basis_when_empty``.
    """

    model_config = ConfigDict(strict=True)

    entity_a_id: uuid.UUID
    entity_b_id: uuid.UUID
    items: list[EvidenceItem] = Field(default_factory=list)
    total_available: int = 0
    raw_cooccurrence_count: int = 0
    offset: int = 0
    basis_when_empty: NonTranscriptBasis | None = None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def returned(self) -> int:
        """Number of video items on this page (derived)."""
        return len(self.items)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def truncated(self) -> bool:
        """Whether more video items remain after this page (offset-aware)."""
        return self.offset + self.returned < self.total_available

    @model_validator(mode="after")
    def _check_counts_and_basis(self) -> Self:
        # Only a page that actually returned items must fit within the total; an empty page past the
        # end (offset > total_available, returned == 0) is a legitimate response, not an error.
        if self.returned > 0 and self.offset + self.returned > self.total_available:
            raise ValueError(
                f"offset ({self.offset}) + returned ({self.returned}) cannot exceed "
                f"total_available ({self.total_available})"
            )
        # A multilingual video makes raw_cooccurrence_count exceed the video total; it can never be
        # smaller (every video contributes at least one transcript).
        if self.items and self.raw_cooccurrence_count < self.total_available:
            raise ValueError(
                f"raw_cooccurrence_count ({self.raw_cooccurrence_count}) cannot be less than "
                f"total_available ({self.total_available})"
            )
        if self.items and self.basis_when_empty is not None:
            raise ValueError("basis_when_empty must be None when items are present")
        # basis_when_empty is set only on the empty early returns (total_available == 0); it must
        # never accompany a non-zero total, where an empty page means "past the end", not "no basis".
        if self.basis_when_empty is not None and self.total_available != 0:
            raise ValueError(
                "basis_when_empty may only be set when total_available == 0 "
                f"(got total_available={self.total_available})"
            )
        return self


# --- Discussion passages (Feature 118) ---------------------------------------------------------
# The panel's second shape, served alongside ``ConnectionEvidence`` (which stays unchanged). It is
# built from the Feature 117 proximity records, so the videos it shows are, by construction, the
# videos the measurement reports for the same pair and window.

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
