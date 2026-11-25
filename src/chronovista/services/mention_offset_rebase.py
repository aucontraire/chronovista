"""Move a segment's mention offsets through an edit of its text (#426).

A correction changes a segment's effective text. Every transcript mention stores
character offsets into that text, so an edit before a mention moves it, and an edit
over a mention can remove the text it recorded. :class:`TextEdit` diffs the old and
new text once and maps offsets through the diff. The diff only proposes a position:
whether a mention still reads at it is decided by
:meth:`TranscriptTextIndex.mention_reads`, the one rule every reader of stored
offsets uses.
"""

from __future__ import annotations

from difflib import SequenceMatcher

from chronovista.services.transcript_text_index import TranscriptTextIndex


def _word_char(text: str, index: int) -> bool:
    return 0 <= index < len(text) and (text[index].isalnum() or text[index] == "_")


def word_bounded(text: str, start: int, end: int) -> bool:
    """Whether ``text[start:end]`` starts and ends at word boundaries.

    A name the scanner matched is a whole word sequence: "Quux" inside "Quuxley" is
    not that name. Used only to notice an edit that glues a name to a longer word.
    """
    return not _word_char(text, start - 1) and not _word_char(text, end)


class TextEdit:
    """The edit from ``old_text`` to ``new_text``, for mapping offsets."""

    def __init__(self, old_text: str, new_text: str) -> None:
        self.old_text = old_text
        self.new_text = new_text
        matcher = SequenceMatcher(None, old_text, new_text, autojunk=False)
        opcodes = matcher.get_opcodes()
        self._opcodes = [(i1, i2, j1, j2) for _tag, i1, i2, j1, j2 in opcodes]
        self._changes = [
            (j1, j2) for tag, _i1, _i2, j1, j2 in opcodes if tag != "equal"
        ]

    def touches(self, start: int, end: int) -> bool:
        """Whether ``[start, end)`` of the new text contains or meets an edit.

        A deletion leaves no new characters, so it counts when it falls strictly
        inside the span.
        """
        for j1, j2 in self._changes:
            if j2 > j1 and start < j2 and j1 < end:
                return True
            if j2 == j1 and start < j1 < end:
                return True
        return False

    def map_start(self, pos: int) -> int | None:
        """Where an inclusive start at ``pos`` lands.

        Exact inside unedited text; inside an edited region, the same distance into
        its replacement (clamped), which the caller then checks against the text.
        Insertions have no old characters, so a start just after one lands after it.
        """
        for i1, i2, j1, j2 in self._opcodes:
            if i1 <= pos < i2:
                return j1 + min(pos - i1, j2 - j1)
        return None

    def map_end(self, pos: int) -> int | None:
        """Where an exclusive end at ``pos`` lands (the character before it decides)."""
        for i1, i2, j1, j2 in self._opcodes:
            if i1 < pos <= i2:
                return j1 + min(pos - i1, j2 - j1)
        return None

    def map_region(self, match_start: int, match_end: int) -> tuple[int, int] | None:
        """Where ``[match_start, match_end)`` of the old text lies in the new text.

        For a span the edit rewrote: the stretch of new text that replaced it, to look
        for what the span became. ``None`` when either end falls outside the text.
        """
        start = self.map_start(match_start)
        end = self.map_end(match_end)
        if start is None or end is None:
            return None
        return start, max(start, end)

    def rebase(
        self, *, match_start: int, match_end: int, mention_text: str
    ) -> tuple[int, int] | None:
        """A single-segment mention's offsets in the new text, or ``None`` when the
        edit changed its words (or glued them to a longer word).

        Call only for a mention that reads correctly in the old text.
        """
        start = self.map_start(match_start)
        if start is None:
            return None
        end = start + (match_end - match_start)
        if not TranscriptTextIndex.of([(0, self.new_text)]).mention_reads(
            segment_id=0,
            end_segment_id=None,
            match_start=start,
            match_end=end,
            mention_text=mention_text,
        ):
            return None
        if word_bounded(self.old_text, match_start, match_end) and not word_bounded(
            self.new_text, start, end
        ):
            return None
        return start, end
