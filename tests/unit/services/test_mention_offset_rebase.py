"""Tests for moving a mention's offsets through a segment edit (#426).

``TextEdit`` only proposes where a single-segment mention lands; whether it still
reads there is decided by ``TranscriptTextIndex.mention_reads`` (tested in
``test_transcript_text_index.py``). Cross-segment mentions are not rebased by this
module. Placeholder names only.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from chronovista.services.mention_offset_rebase import TextEdit, word_bounded

NAME = "Zeta Quux"


def _whole(old: str, new: str, mention: str = NAME) -> tuple[int, int] | None:
    start = old.index(mention)
    return TextEdit(old, new).rebase(
        match_start=start,
        match_end=start + len(mention),
        mention_text=mention,
    )


class TestRebase:
    def test_an_insertion_before_the_mention_moves_it(self) -> None:
        old, new = f"we saw {NAME} here", f"we all saw {NAME} here"
        assert _whole(old, new) == (11, 20)
        assert new[11:20] == NAME

    def test_a_deletion_before_the_mention_moves_it(self) -> None:
        old, new = f"so we saw {NAME} here", f"we saw {NAME} here"
        assert _whole(old, new) == (7, 16)

    def test_an_edit_after_the_mention_leaves_it(self) -> None:
        old, new = f"we saw {NAME} here", f"we saw {NAME} there today"
        assert _whole(old, new) == (7, 16)

    def test_an_insertion_right_before_the_mention_moves_it(self) -> None:
        old, new = f"{NAME} spoke", f"Dr {NAME} spoke"
        assert _whole(old, new) == (3, 12)

    def test_an_edit_that_replaces_the_mentions_text_removes_it(self) -> None:
        old, new = "we saw Zeta Quuks here", f"we saw {NAME} here"
        assert _whole(old, new, mention="Zeta Quuks") is None

    def test_an_edit_inside_the_mention_that_keeps_its_text_keeps_it(self) -> None:
        # A case-only fix to the first letter still reads as the mention.
        old, new = "we saw zeta Quux here", f"we saw {NAME} here"
        assert _whole(old, new, mention="zeta Quux") == (7, 16)

    def test_each_occurrence_keeps_its_own_position(self) -> None:
        old = f"{NAME} met {NAME}"
        new = f"then {NAME} met {NAME}"
        second = old.rindex(NAME)
        assert TextEdit(old, new).rebase(
            match_start=second, match_end=second + len(NAME), mention_text=NAME
        ) == (new.rindex(NAME), new.rindex(NAME) + len(NAME))

    def test_an_identical_text_is_a_no_op(self) -> None:
        text = f"we saw {NAME} here"
        assert _whole(text, text) == (7, 16)

    def test_a_start_past_the_old_text_is_dropped(self) -> None:
        assert (
            TextEdit("short", "short text").rebase(
                match_start=40, match_end=49, mention_text=NAME
            )
            is None
        )

    def test_a_name_glued_to_a_longer_word_is_dropped(self) -> None:
        """'Zeta Quux' -> 'Zeta Quuxley': the first nine characters still read as the
        name, but it is no longer the whole word, so it is not that name.

        Mutation: remove the ``word_bounded`` comparison at the end of ``rebase``.
        """
        old, new = f"we saw {NAME} here", f"we saw {NAME}ley here"
        assert _whole(old, new) is None

    def test_a_name_that_was_already_inside_a_word_is_not_dropped_for_it(self) -> None:
        """A row recorded inside a longer word before the edit (a legacy row) is not
        newly glued by an unrelated edit, so the boundary rule does not fire."""
        old, new = f"we saw {NAME}ley here", f"we all saw {NAME}ley here"
        assert _whole(old, new) == (11, 20)

    def test_the_casefold_of_the_slice_decides_not_its_length(self) -> None:
        """The slice 'STRASSE' reads as 'Straße' (casefold-equal, different length);
        the rebase carries the stored length, so an edit far away keeps the row."""
        old = "we saw Zeta STRASSE here"
        assert TextEdit(old, "so " + old).rebase(
            match_start=7, match_end=19, mention_text="Zeta Straße"
        ) == (10, 22)


class TestMapping:
    """The mapping primitives the correction rebase composes."""

    def test_touches_is_true_only_for_a_span_that_meets_the_edit(self) -> None:
        edit = TextEdit("we saw Zeta Quux here", "we all saw Zeta Quux here")
        # The inserted "all " occupies [2, 6) of the new text.
        assert edit.touches(0, 5) is True
        assert edit.touches(4, 6) is True
        assert edit.touches(11, 20) is False, "wholly after the insertion"
        assert edit.touches(0, 2) is False, "wholly before it"

    def test_a_deletion_touches_only_a_span_it_falls_strictly_inside(self) -> None:
        edit = TextEdit("we saw Zeta Quux here", "we Zeta Quux here")
        assert edit.touches(0, 10) is True
        assert edit.touches(0, 3) is True
        assert edit.touches(2, 3) is False, "the deletion is at the span's start"
        assert edit.touches(3, 4) is False

    def test_map_start_and_end_follow_unedited_text_exactly(self) -> None:
        edit = TextEdit("we saw Zeta Quux here", "we all saw Zeta Quux here")
        assert edit.map_start(7) == 11
        assert edit.map_end(16) == 20
        assert edit.map_start(0) == 0
        assert edit.map_region(7, 16) == (11, 20)

    def test_a_position_past_the_old_text_has_no_image(self) -> None:
        edit = TextEdit("we saw Zeta Quux here", "we all saw Zeta Quux here")
        assert edit.map_start(100) is None
        assert edit.map_end(0) is None, "an end of 0 has no character before it"
        assert edit.map_region(100, 110) is None

    def test_a_rewritten_span_maps_to_the_text_that_replaced_it(self) -> None:
        edit = TextEdit("we saw Zeta Quuks here", "we saw Zeta Quux here")
        assert edit.map_region(7, 17) == (7, 16)


class TestWordBounded:
    def test_a_whole_word_sequence_is_bounded(self) -> None:
        assert word_bounded("a Zeta b", 2, 6) is True
        assert word_bounded("Zeta", 0, 4) is True

    def test_a_neighbouring_letter_on_either_side_unbounds_it(self) -> None:
        assert word_bounded("aZeta b", 1, 5) is False
        assert word_bounded("a Zetab", 2, 6) is False

    def test_punctuation_and_whitespace_are_boundaries_but_underscore_is_not(
        self,
    ) -> None:
        assert word_bounded("(Zeta),", 1, 5) is True
        assert word_bounded("_Zeta", 1, 5) is False


_ALPHABET = "aAb _"


@st.composite
def _edited_mention(draw: st.DrawFn) -> tuple[str, str, int, int]:
    """An old text, a non-empty slice of it as the mention, and an edited new text."""
    old = draw(st.text(alphabet=_ALPHABET, min_size=1, max_size=24))
    start = draw(st.integers(min_value=0, max_value=len(old) - 1))
    end = draw(st.integers(min_value=start + 1, max_value=len(old)))
    cut_a = draw(st.integers(min_value=0, max_value=len(old)))
    cut_b = draw(st.integers(min_value=cut_a, max_value=len(old)))
    inserted = draw(st.text(alphabet=_ALPHABET, max_size=6))
    new = old[:cut_a] + inserted + old[cut_b:]
    return old, new, start, end


class TestRebaseProperties:
    @settings(deadline=None, max_examples=400)
    @given(case=_edited_mention())
    def test_whenever_it_returns_offsets_the_new_text_reads_as_the_mention(
        self, case: tuple[str, str, int, int]
    ) -> None:
        """For any text, mention slice and edit, a returned position reads as the
        mention in the new text, with the stored length, and a word-bounded mention
        stays word-bounded.

        Mutation: remove the ``mention_reads`` check from ``rebase`` (an edit that
        rewrote the mention's words would then return offsets over other text), or the
        ``word_bounded`` comparison.
        """
        old, new, start, end = case
        mention = old[start:end]

        result = TextEdit(old, new).rebase(
            match_start=start, match_end=end, mention_text=mention
        )

        if result is None:
            return
        new_start, new_end = result
        assert new_end - new_start == end - start
        assert new[new_start:new_end].casefold() == mention.casefold(), (old, new, case)
        if word_bounded(old, start, end):
            assert word_bounded(new, new_start, new_end), (old, new, case)

    @settings(deadline=None, max_examples=200)
    @given(
        old=st.text(alphabet=_ALPHABET, min_size=1, max_size=24),
        data=st.data(),
    )
    def test_an_identical_text_never_moves_or_drops_a_mention(
        self, old: str, data: st.DataObject
    ) -> None:
        """An edit that changes nothing leaves every slice exactly where it was.

        Mutation: skew ``map_start`` by one anywhere in an unedited region.
        """
        start = data.draw(st.integers(min_value=0, max_value=len(old) - 1))
        end = data.draw(st.integers(min_value=start + 1, max_value=len(old)))

        result = TextEdit(old, old).rebase(
            match_start=start, match_end=end, mention_text=old[start:end]
        )

        assert result == (start, end)
