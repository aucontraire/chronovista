"""Shared span-resolution primitive for cross-segment mention detection (Feature 081).

Single source of truth (FR-013/FR-014) for two things both mention-writing paths need:

1. The "effective text" rule — ``corrected_text`` when a segment is corrected, else ``text``.
2. Assembling a transcript's segments into one string (joined by a single, consistent
   separator) and mapping any character offset in that string back to the segment(s) it
   falls in, so a match that crosses a boundary resolves to one span anchored at its first
   segment with ``end_segment_id`` at its last.

Both the detection scanner and the correction service MUST build their anchoring through
this module — never a second implementation of the adjacent-segment join — so detection and
corrections anchor spanning mentions identically.
"""

from __future__ import annotations

import bisect
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict

#: The one separator inserted between segments when assembling transcript text (FR-014).
SEGMENT_SEPARATOR = " "


def effective_text(text: str, corrected_text: str | None, has_correction: bool) -> str:
    """The single definition of a segment's effective text (FR-013).

    Parameters
    ----------
    text : str
        The segment's original transcript text.
    corrected_text : str | None
        The applied correction, if any.
    has_correction : bool
        Whether this segment carries a correction.

    Returns
    -------
    str
        ``corrected_text`` when the segment is corrected and non-null, else ``text``.
    """
    if has_correction and corrected_text is not None:
        return corrected_text
    return text


class SegmentInput(BaseModel):
    """One segment fed into the index, in ``sequence_number`` order."""

    model_config = ConfigDict(frozen=True)

    segment_id: int
    text: str
    corrected_text: str | None = None
    has_correction: bool = False

    @property
    def effective(self) -> str:
        return effective_text(self.text, self.corrected_text, self.has_correction)


class SpanAnchor(BaseModel):
    """Where a match in the assembled text lands, in segment terms.

    ``end_segment_id`` is ``None`` for a match wholly inside one segment (today's semantics);
    otherwise the match spans ``segment_id`` (first) through ``end_segment_id`` (last).
    ``match_start`` is the local offset into the first segment's effective text; ``match_end``
    is the local offset into the last segment's effective text.
    """

    model_config = ConfigDict(frozen=True)

    segment_id: int
    end_segment_id: int | None
    crossed_segment_ids: tuple[int, ...]
    match_start: int
    match_end: int


class _SegmentSpan(BaseModel):
    model_config = ConfigDict(frozen=True)

    start: int  # inclusive offset into the assembled text
    end: int  # exclusive offset into the assembled text
    segment_id: int


class TranscriptTextIndex:
    """Assembled transcript text plus an offset→segment index.

    Build once per transcript from segments ordered by ``sequence_number``; call
    :meth:`resolve_span` to map a match's character offsets back to its segment(s).
    """

    def __init__(self, text: str, spans: list[_SegmentSpan]) -> None:
        self.text = text
        self._spans = spans
        self._starts = [s.start for s in spans]

    @classmethod
    def from_segments(cls, segments: Sequence[SegmentInput]) -> TranscriptTextIndex:
        spans: list[_SegmentSpan] = []
        parts: list[str] = []
        offset = 0
        for i, seg in enumerate(segments):
            if i > 0:
                offset += len(SEGMENT_SEPARATOR)
            body = seg.effective
            spans.append(
                _SegmentSpan(
                    start=offset, end=offset + len(body), segment_id=seg.segment_id
                )
            )
            parts.append(body)
            offset += len(body)
        return cls(SEGMENT_SEPARATOR.join(parts), spans)

    def _index_at(self, pos: int) -> int:
        """Return the span index whose [start, end) contains ``pos``.

        A position landing in a separator gap is attributed to the following segment (the
        next real character), which is the correct behavior for a match's inclusive start;
        for an exclusive end the caller passes ``match_end - 1`` so it, too, lands on a real
        character of the last crossed segment.
        """
        # rightmost span whose start <= pos
        i = bisect.bisect_right(self._starts, pos) - 1
        if i < 0:
            return 0
        if pos < self._spans[i].end:
            return i
        # pos is in the separator gap after span i -> attribute to the next segment
        return min(i + 1, len(self._spans) - 1)

    def resolve_span(self, match_start: int, match_end: int) -> SpanAnchor:
        """Map an assembled-text ``[match_start, match_end)`` slice to a :class:`SpanAnchor`.

        ``match_end`` is exclusive. The first segment is the one containing ``match_start``;
        the last is the one containing ``match_end - 1``. ``end_segment_id`` is ``None`` when
        both are the same segment (single-segment mention).
        """
        if match_end <= match_start:
            raise ValueError(f"empty or inverted span: [{match_start}, {match_end})")
        first_i = self._index_at(match_start)
        last_i = self._index_at(match_end - 1)
        first = self._spans[first_i]
        last = self._spans[last_i]
        crossed = tuple(self._spans[j].segment_id for j in range(first_i, last_i + 1))
        local_start = match_start - first.start
        local_end = match_end - last.start
        return SpanAnchor(
            segment_id=first.segment_id,
            end_segment_id=(None if last_i == first_i else last.segment_id),
            crossed_segment_ids=crossed,
            # clamp: a start attributed across a separator gap maps to the segment's start,
            # and an end never exceeds the last segment's effective length.
            match_start=max(0, local_start),
            match_end=min(local_end, last.end - last.start),
        )
