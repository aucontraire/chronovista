"""
Factories for the Feature 118 discussion-passage models using factory_boy.

Defaults satisfy every cross-field validator (derived fields are ``LazyAttribute``s
of the fields they summarize), so a test overrides only what it is exercising.
All values are neutral placeholders.
"""

from __future__ import annotations

import uuid
from typing import Any

import factory
from factory import LazyAttribute, LazyFunction, Sequence, SubFactory

from chronovista.models.connection_evidence import (
    CoMoment,
    GroupedPassage,
    LanguagePassage,
    MentionRef,
    PairPassages,
    PassageMoment,
    PassageSegment,
    VideoPassages,
)


class MentionRefFactory(factory.Factory[MentionRef]):
    """Factory for MentionRef models."""

    class Meta:
        model = MentionRef

    segment_id: Any = Sequence(lambda n: n + 1)
    end_segment_id: Any = None
    language_code: Any = "en"
    sequence_number: Any = Sequence(lambda n: n)
    start_time: Any = 10.0
    mention_text: Any = Sequence(lambda n: f"Entity {n}")
    match_start: Any = None
    match_end: Any = None
    detection_method: Any = "rule_match"


class CoMomentFactory(factory.Factory[CoMoment]):
    """Factory for CoMoment models."""

    class Meta:
        model = CoMoment

    start_time: Any = Sequence(lambda n: 20.0 + n)
    gap_seconds: Any = 3.0


class PassageSegmentFactory(factory.Factory[PassageSegment]):
    """Factory for PassageSegment models."""

    class Meta:
        model = PassageSegment

    segment_id: Any = Sequence(lambda n: n + 1)
    sequence_number: Any = Sequence(lambda n: n)
    start_time: Any = 10.0
    text: Any = "placeholder segment text"
    is_context: Any = False


class PassageMomentFactory(factory.Factory[PassageMoment]):
    """Factory for PassageMoment models."""

    class Meta:
        model = PassageMoment

    gap_seconds: Any = 2.0
    start_time: Any = 10.0
    segment_id: Any = 1
    mention_a: Any = SubFactory(MentionRefFactory)
    mention_b: Any = SubFactory(MentionRefFactory)
    segments: Any = LazyFunction(lambda: [PassageSegmentFactory()])


class LanguagePassageFactory(factory.Factory[LanguagePassage]):
    """Factory for LanguagePassage models (one co-mention by default)."""

    class Meta:
        model = LanguagePassage

    language_code: Any = "en"
    start_time: Any = 10.0
    end_time: Any = 14.0
    closest: Any = SubFactory(PassageMomentFactory)
    closest_gap_seconds: Any = LazyAttribute(lambda o: o.closest.gap_seconds)
    other_moments: Any = LazyFunction(list)
    co_mention_count: Any = LazyAttribute(
        lambda o: 1 + len(o.other_moments)
    )  # under the cap
    name_list: Any = False


class GroupedPassageFactory(factory.Factory[GroupedPassage]):
    """Factory for GroupedPassage models; the range and gap derive from the variants."""

    class Meta:
        model = GroupedPassage

    variants: Any = LazyFunction(lambda: [LanguagePassageFactory()])
    start_time: Any = LazyAttribute(lambda o: min(v.start_time for v in o.variants))
    end_time: Any = LazyAttribute(lambda o: max(v.end_time for v in o.variants))
    closest_gap_seconds: Any = LazyAttribute(
        lambda o: min(v.closest_gap_seconds for v in o.variants)
    )


class VideoPassagesFactory(factory.Factory[VideoPassages]):
    """Factory for VideoPassages models."""

    class Meta:
        model = VideoPassages

    video_id: Any = Sequence(lambda n: f"video-{n:03d}")
    video_title: Any = Sequence(lambda n: f"Placeholder video {n}")
    channel_title: Any = "Placeholder channel"
    passages: Any = LazyFunction(lambda: [GroupedPassageFactory()])
    closest_gap_seconds: Any = LazyAttribute(
        lambda o: min(p.closest_gap_seconds for p in o.passages)
    )


class PairPassagesFactory(factory.Factory[PairPassages]):
    """Factory for PairPassages models: one video, one passage, state ``passages``."""

    class Meta:
        model = PairPassages

    entity_a_id: Any = LazyFunction(uuid.uuid4)
    entity_b_id: Any = LazyFunction(uuid.uuid4)
    window_seconds: Any = 30
    items: Any = LazyFunction(lambda: [VideoPassagesFactory()])
    offset: Any = 0
    video_count: Any = LazyAttribute(lambda o: len(o.items))
    passage_count: Any = LazyAttribute(lambda o: sum(len(v.passages) for v in o.items))
    channel_count: Any = LazyAttribute(lambda o: 1 if o.items else 0)
    closest_gap_seconds: Any = LazyAttribute(
        lambda o: min((v.closest_gap_seconds for v in o.items), default=None)
    )
    farther_video_count: Any = 0
    pending_scopes: Any = 0
    failed_scopes: Any = LazyFunction(list)
    state: Any = LazyAttribute(
        lambda o: "passages" if o.items else "no_passage_in_window"
    )
    basis_when_empty: Any = None
