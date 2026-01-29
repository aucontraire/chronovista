"""
Factory for TranscriptSegment Pydantic models using factory_boy.

Provides reusable test data factories for all TranscriptSegment model variants
with sensible defaults and easy customization.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List

import factory
from factory import LazyAttribute, LazyFunction, Sequence

from chronovista.models.transcript_segment import (
    TranscriptSegment,
    TranscriptSegmentBase,
    TranscriptSegmentCreate,
    TranscriptSegmentResponse,
)


class TranscriptSegmentBaseFactory(factory.Factory[TranscriptSegmentBase]):
    """Factory for TranscriptSegmentBase models."""

    class Meta:
        model = TranscriptSegmentBase

    video_id: Any = LazyFunction(lambda: "dQw4w9WgXcQ")  # Default test video (11 chars)
    language_code: Any = LazyFunction(lambda: "en")
    text: Any = factory.Faker("sentence")
    start_time: Any = Sequence(lambda n: float(n * 3))  # 0, 3, 6, 9...
    duration: Any = LazyFunction(lambda: 2.5)
    end_time: Any = LazyAttribute(lambda obj: obj.start_time + obj.duration)
    sequence_number: Any = Sequence(lambda n: n)


class TranscriptSegmentCreateFactory(TranscriptSegmentBaseFactory):
    """Factory for TranscriptSegmentCreate models."""

    class Meta:
        model = TranscriptSegmentCreate


class TranscriptSegmentFactory(TranscriptSegmentBaseFactory):
    """Factory for full TranscriptSegment models with database fields."""

    class Meta:
        model = TranscriptSegment

    id: Any = Sequence(lambda n: n + 1)
    has_correction: Any = LazyFunction(lambda: False)
    corrected_text: Any = LazyFunction(lambda: None)
    created_at: Any = LazyFunction(
        lambda: datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
    )


class TranscriptSegmentResponseFactory(factory.Factory[TranscriptSegmentResponse]):
    """Factory for TranscriptSegmentResponse models."""

    class Meta:
        model = TranscriptSegmentResponse

    segment_id: Any = Sequence(lambda n: n + 1)
    text: Any = factory.Faker("sentence")
    start_time: Any = Sequence(lambda n: float(n * 3))
    duration: Any = LazyFunction(lambda: 2.5)
    end_time: Any = LazyAttribute(lambda obj: obj.start_time + obj.duration)
    start_formatted: Any = LazyAttribute(
        lambda obj: _format_time(obj.start_time)
    )
    end_formatted: Any = LazyAttribute(
        lambda obj: _format_time(obj.end_time)
    )


def _format_time(seconds: float) -> str:
    """Helper to format seconds for factory."""
    if seconds < 0:
        seconds = 0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


# Convenience factory methods
def create_transcript_segment_base(**kwargs: Any) -> TranscriptSegmentBase:
    """Create a TranscriptSegmentBase with keyword arguments."""
    result = TranscriptSegmentBaseFactory.build(**kwargs)
    assert isinstance(result, TranscriptSegmentBase)
    return result


def create_transcript_segment_create(**kwargs: Any) -> TranscriptSegmentCreate:
    """Create a TranscriptSegmentCreate with keyword arguments."""
    result = TranscriptSegmentCreateFactory.build(**kwargs)
    assert isinstance(result, TranscriptSegmentCreate)
    return result


def create_transcript_segment(**kwargs: Any) -> TranscriptSegment:
    """Create a TranscriptSegment with keyword arguments."""
    result = TranscriptSegmentFactory.build(**kwargs)
    assert isinstance(result, TranscriptSegment)
    return result


def create_transcript_segment_response(**kwargs: Any) -> TranscriptSegmentResponse:
    """Create a TranscriptSegmentResponse with keyword arguments."""
    result = TranscriptSegmentResponseFactory.build(**kwargs)
    assert isinstance(result, TranscriptSegmentResponse)
    return result


def create_batch_transcript_segments(
    video_id: str = "dQw4w9WgXcQ",
    language_code: str = "en",
    count: int = 5,
) -> List[TranscriptSegment]:
    """Create a batch of sequential TranscriptSegment instances.

    Parameters
    ----------
    video_id : str
        YouTube video ID to use for all segments.
    language_code : str
        Language code to use for all segments.
    count : int
        Number of segments to create.

    Returns
    -------
    List[TranscriptSegment]
        List of sequential transcript segments.
    """
    segments: List[TranscriptSegment] = []
    base_texts = [
        "Hello and welcome to this video.",
        "Today we'll be discussing important topics.",
        "Let's dive right into the content.",
        "This is a key point to remember.",
        "Thank you for watching until the end.",
    ]

    current_time = 0.0
    for i in range(count):
        duration = 2.5 + (i * 0.5)  # Varying durations
        segment_result = TranscriptSegmentFactory.build(
            id=i + 1,
            video_id=video_id,
            language_code=language_code,
            text=base_texts[i % len(base_texts)],
            start_time=current_time,
            duration=duration,
            end_time=current_time + duration,
            sequence_number=i,
        )
        assert isinstance(segment_result, TranscriptSegment)
        segments.append(segment_result)
        current_time += duration

    return segments


def create_corrected_transcript_segment(**kwargs: Any) -> TranscriptSegment:
    """Create a TranscriptSegment with correction applied.

    Parameters
    ----------
    **kwargs : Any
        Keyword arguments to override defaults.
        If 'corrected_text' is not provided, a default is generated.

    Returns
    -------
    TranscriptSegment
        A segment with has_correction=True and corrected_text set.
    """
    if "corrected_text" not in kwargs:
        kwargs["corrected_text"] = "This is the corrected text."
    kwargs["has_correction"] = True
    result = TranscriptSegmentFactory.build(**kwargs)
    assert isinstance(result, TranscriptSegment)
    return result


# Common test data patterns
class TranscriptSegmentTestData:
    """Common test data patterns for TranscriptSegment models."""

    VALID_VIDEO_IDS = [
        "dQw4w9WgXcQ",  # Rick Astley (11 chars)
        "9bZkp7q19f0",  # Google I/O (11 chars)
        "3tmd-ClpJxA",  # Late Show (11 chars)
        "jNQXAC9IVRw",  # MKBHD (11 chars)
        "MejbOFk7H6c",  # Another video (11 chars)
    ]

    VALID_LANGUAGE_CODES = [
        "en",
        "en-US",
        "es",
        "fr",
        "de",
        "ja",
        "ko",
        "zh-CN",
        "pt-BR",
    ]

    VALID_TEXTS = [
        "Hello world!",
        "This is a test segment with multiple words.",
        "A",  # Minimum length
        "Multilingual content: Hola, Bonjour, Guten Tag",
        "Technical content with numbers: 23.5 degrees at 15:30 UTC",
    ]

    INVALID_VIDEO_IDS = [
        "",  # Empty
        "   ",  # Whitespace
        "short",  # Too short
        "x" * 25,  # Too long
    ]

    INVALID_LANGUAGE_CODES = [
        "",  # Empty
        "a",  # Too short
        "x" * 15,  # Too long
    ]

    INVALID_TEXTS = [
        "",  # Empty
    ]

    # Sample JSONB snippet data for from_snippet testing
    SAMPLE_SNIPPETS = [
        {"text": "Hello and welcome", "start": 0.0, "duration": 2.5},
        {"text": "to this video", "start": 2.5, "duration": 1.8},
        {"text": "about programming", "start": 4.3, "duration": 2.2},
    ]

    @classmethod
    def valid_segment_data(cls) -> dict[str, Any]:
        """Get valid transcript segment data."""
        return {
            "video_id": cls.VALID_VIDEO_IDS[0],
            "language_code": cls.VALID_LANGUAGE_CODES[0],
            "text": cls.VALID_TEXTS[0],
            "start_time": 0.0,
            "duration": 2.5,
            "end_time": 2.5,
            "sequence_number": 0,
        }

    @classmethod
    def valid_full_segment_data(cls) -> dict[str, Any]:
        """Get valid full transcript segment data with DB fields."""
        data = cls.valid_segment_data()
        data.update(
            {
                "id": 1,
                "has_correction": False,
                "corrected_text": None,
                "created_at": datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc),
            }
        )
        return data

    @classmethod
    def edge_case_zero_duration_data(cls) -> dict[str, Any]:
        """Get segment data with zero duration (FR-EDGE-07 compliant)."""
        return {
            "video_id": cls.VALID_VIDEO_IDS[0],
            "language_code": "en",
            "text": "Quick flash text",
            "start_time": 10.0,
            "duration": 0.0,
            "end_time": 10.0,
            "sequence_number": 5,
        }

    @classmethod
    def sample_raw_transcript_data(cls) -> dict[str, Any]:
        """Get sample raw transcript data structure from VideoTranscript."""
        return {
            "video_id": cls.VALID_VIDEO_IDS[0],
            "language_code": "en",
            "language_name": "English",
            "snippets": cls.SAMPLE_SNIPPETS,
            "is_generated": False,
            "is_translatable": True,
            "source": "youtube_transcript_api",
            "retrieved_at": "2024-01-15T10:30:00Z",
        }
