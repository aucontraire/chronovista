"""
Service for transcript segment extraction, formatting, and utilities.

This module provides utility functions for parsing and formatting timestamps,
used by the transcript segment models and CLI commands. Also provides output
formatters for human-readable, JSON, and SRT subtitle formats.
"""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import TYPE_CHECKING, Optional, Sequence

if TYPE_CHECKING:
    from chronovista.models.transcript_segment import TranscriptSegment


class OutputFormat(str, Enum):
    """Output format for segment display.

    Attributes
    ----------
    HUMAN : str
        Human-readable CLI format with newlines escaped as spaces.
    JSON : str
        JSON format with newlines preserved as escape sequences.
    SRT : str
        SRT subtitle format with newlines preserved literally.
    """

    HUMAN = "human"
    JSON = "json"
    SRT = "srt"


def parse_timestamp(timestamp_str: str) -> float:
    """Parse timestamp string to seconds.

    Supported formats:
    - "90" -> 90.0 (raw seconds)
    - "90.5" -> 90.5 (raw seconds with decimal)
    - "1:30" -> 90.0 (MM:SS)
    - "01:30" -> 90.0 (MM:SS)
    - "0:01:30" -> 90.0 (H:MM:SS)
    - "00:01:30" -> 90.0 (HH:MM:SS)

    Parameters
    ----------
    timestamp_str : str
        Timestamp in various formats.

    Returns
    -------
    float
        Time in seconds.

    Raises
    ------
    ValueError
        If timestamp format is invalid.

    Examples
    --------
    >>> parse_timestamp("90")
    90.0
    >>> parse_timestamp("1:30")
    90.0
    >>> parse_timestamp("00:01:30")
    90.0
    >>> parse_timestamp("1:30.5")
    90.5
    """
    timestamp_str = timestamp_str.strip()

    # Try raw seconds first (integer or float)
    try:
        return float(timestamp_str)
    except ValueError:
        pass

    # Try time formats (HH:MM:SS, H:MM:SS, MM:SS, M:SS)
    pattern = r"^(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?:\.(\d+))?$"
    match = re.match(pattern, timestamp_str)

    if match:
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2))
        seconds = int(match.group(3))
        milliseconds = match.group(4)

        total: float = float(hours * 3600 + minutes * 60 + seconds)
        if milliseconds:
            total += float(f"0.{milliseconds}")

        return total

    raise ValueError(
        f"Invalid timestamp format: '{timestamp_str}'. "
        "Expected formats: raw seconds (90), MM:SS (1:30), or HH:MM:SS (00:01:30)"
    )


def format_timestamp(seconds: float, include_hours: bool = False) -> str:
    """Format seconds as timestamp string.

    Parameters
    ----------
    seconds : float
        Time in seconds.
    include_hours : bool, optional
        If True, always include hours. If False, only include hours
        if >= 1 hour. Default is False.

    Returns
    -------
    str
        Formatted timestamp (e.g., "1:30" or "1:30:45").

    Examples
    --------
    >>> format_timestamp(90)
    '1:30'
    >>> format_timestamp(90, include_hours=True)
    '0:01:30'
    >>> format_timestamp(3661)
    '1:01:01'
    >>> format_timestamp(-5)
    '0:00'
    """
    if seconds < 0:
        seconds = 0

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)

    if hours > 0 or include_hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes}:{secs:02d}"


def format_timestamp_srt(seconds: float) -> str:
    """Format seconds as SRT timestamp (HH:MM:SS,mmm).

    SRT (SubRip) format uses commas for millisecond separator
    and always includes all time components.

    Parameters
    ----------
    seconds : float
        Time in seconds.

    Returns
    -------
    str
        SRT-formatted timestamp (e.g., "00:01:30,500").

    Examples
    --------
    >>> format_timestamp_srt(90.5)
    '00:01:30,500'
    >>> format_timestamp_srt(3661.123)
    '01:01:01,123'
    >>> format_timestamp_srt(-5)
    '00:00:00,000'
    """
    if seconds < 0:
        seconds = 0

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int((seconds % 1) * 1000)

    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"


def format_segment_human(
    segment: "TranscriptSegment",
    max_text_length: int = 80,
) -> str:
    """Format a single segment for human-readable display.

    Format: #42 [1:30-1:33] Welcome to the video...

    Newlines are escaped as spaces per FR-EDGE-15 for single-line CLI display.

    Parameters
    ----------
    segment : TranscriptSegment
        The segment to format.
    max_text_length : int
        Maximum text length before truncation (default 80).

    Returns
    -------
    str
        Human-readable formatted segment.

    Examples
    --------
    >>> format_segment_human(segment)
    '#42 [1:30-1:33] Welcome to the video...'
    >>> format_segment_human(zero_duration_segment)
    '#1 [0:05] [0.00s] Point'
    """
    # Escape newlines as spaces per FR-EDGE-15
    text = segment.display_text.replace("\n", " ").replace("\r", "")

    # Truncate if needed
    if len(text) > max_text_length:
        text = text[: max_text_length - 3] + "..."

    start = format_timestamp(segment.start_time)
    end = format_timestamp(segment.end_time)

    # Zero duration indicator per FR-EDGE-06
    if segment.duration == 0:
        return f"#{segment.id} [{start}] [0.00s] {text}"

    return f"#{segment.id} [{start}-{end}] {text}"


def format_segment_json(segment: "TranscriptSegment") -> str:
    """Format a single segment as JSON.

    Newlines are preserved as \\n escape sequences per FR-EDGE-16.

    Parameters
    ----------
    segment : TranscriptSegment
        The segment to format.

    Returns
    -------
    str
        JSON-formatted segment with indentation.

    Examples
    --------
    >>> format_segment_json(segment)
    '{\\n  "segment_id": 42,\\n  "text": "Hello world",\\n  ...\\n}'
    """
    from chronovista.models.transcript_segment import TranscriptSegmentResponse

    response = TranscriptSegmentResponse.from_segment(segment)
    return response.model_dump_json(indent=2)


def format_segment_srt(segment: "TranscriptSegment", sequence: int) -> str:
    """Format a single segment as SRT subtitle.

    Newlines are preserved literally for multi-line subtitles per FR-EDGE-17.

    SRT format structure:
    1
    00:01:30,000 --> 00:01:33,000
    Hello world

    Parameters
    ----------
    segment : TranscriptSegment
        The segment to format.
    sequence : int
        SRT sequence number (1-indexed).

    Returns
    -------
    str
        SRT-formatted segment block.

    Examples
    --------
    >>> format_segment_srt(segment, sequence=1)
    '1\\n00:01:30,000 --> 00:01:33,000\\nHello world\\n'
    """
    start = format_timestamp_srt(segment.start_time)
    end = format_timestamp_srt(segment.end_time)
    text = segment.display_text  # Preserve newlines per FR-EDGE-17

    return f"{sequence}\n{start} --> {end}\n{text}\n"


def format_segments_human(
    segments: Sequence["TranscriptSegment"],
    title: Optional[str] = None,
) -> str:
    """Format multiple segments for human-readable display.

    Parameters
    ----------
    segments : Sequence[TranscriptSegment]
        Segments to format.
    title : Optional[str]
        Optional title/header for the output.

    Returns
    -------
    str
        Human-readable formatted segments with summary.

    Examples
    --------
    >>> format_segments_human(segments)
    '#1 [0:00-0:02] First segment\\n#2 [0:02-0:04] Second segment\\n\\n... 2 segment(s) ...'
    """
    if not segments:
        return "No segments found."

    lines: list[str] = []
    if title:
        lines.append(title)
        lines.append("")

    for segment in segments:
        lines.append(format_segment_human(segment))

    lines.append("")
    segment_word = "segment" if len(segments) == 1 else "segments"
    lines.append(f"--- {len(segments)} {segment_word} ---")

    return "\n".join(lines)


def format_segments_json(
    segments: Sequence["TranscriptSegment"],
    video_id: Optional[str] = None,
    language_code: Optional[str] = None,
) -> str:
    """Format multiple segments as JSON.

    Parameters
    ----------
    segments : Sequence[TranscriptSegment]
        Segments to format.
    video_id : Optional[str]
        Video ID for metadata.
    language_code : Optional[str]
        Language code for metadata.

    Returns
    -------
    str
        JSON-formatted segments with metadata.

    Examples
    --------
    >>> format_segments_json(segments)
    '{\\n  "count": 2,\\n  "segments": [...]\\n}'
    """
    from chronovista.models.transcript_segment import TranscriptSegmentResponse

    responses = [TranscriptSegmentResponse.from_segment(seg) for seg in segments]

    output: dict[str, object] = {
        "count": len(segments),
        "segments": [r.model_dump() for r in responses],
    }

    if video_id:
        output["video_id"] = video_id
    if language_code:
        output["language_code"] = language_code

    return json.dumps(output, indent=2)


def format_segments_srt(segments: Sequence["TranscriptSegment"]) -> str:
    """Format multiple segments as SRT subtitles.

    Parameters
    ----------
    segments : Sequence[TranscriptSegment]
        Segments to format.

    Returns
    -------
    str
        Complete SRT file content.

    Examples
    --------
    >>> format_segments_srt(segments)
    '1\\n00:00:00,000 --> 00:00:02,000\\nFirst\\n\\n2\\n00:00:02,000 --> 00:00:04,000\\nSecond\\n'
    """
    if not segments:
        return ""

    lines: list[str] = []
    for i, segment in enumerate(segments, start=1):
        lines.append(format_segment_srt(segment, i))

    return "\n".join(lines)


__all__ = [
    "OutputFormat",
    "parse_timestamp",
    "format_timestamp",
    "format_timestamp_srt",
    "format_segment_human",
    "format_segment_json",
    "format_segment_srt",
    "format_segments_human",
    "format_segments_json",
    "format_segments_srt",
]
