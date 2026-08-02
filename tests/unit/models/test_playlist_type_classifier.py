"""Unit tests for classify_playlist_type (Feature 058).

Validates the single-source-of-truth classifier used by both the Takeout
seeder (US1) and the reclassify CLI (US2). Pure function — no DB, no async.
"""

from __future__ import annotations

import pytest

from chronovista.models.enums import PlaylistType, classify_playlist_type


class TestCanonicalIdentifierPrecedence:
    """Canonical YouTube system-playlist identifiers take precedence (FR-002)."""

    def test_wl_id_maps_to_watch_later(self) -> None:
        assert classify_playlist_type("WL", "anything") is PlaylistType.WATCH_LATER

    def test_hl_id_maps_to_history(self) -> None:
        assert classify_playlist_type("HL", "anything") is PlaylistType.HISTORY

    def test_ll_prefixed_id_maps_to_liked(self) -> None:
        # Liked-videos playlist is "LL" + channel suffix.
        assert classify_playlist_type("LLabc123def", "anything") is PlaylistType.LIKED

    def test_bare_ll_maps_to_liked(self) -> None:
        assert classify_playlist_type("LL", "anything") is PlaylistType.LIKED

    def test_id_precedence_beats_conflicting_name(self) -> None:
        # WL id wins even if the name says "History".
        assert classify_playlist_type("WL", "History") is PlaylistType.WATCH_LATER

    def test_regular_pl_id_falls_through_to_name(self) -> None:
        # PL-prefixed ids are not canonical system ids → decided by name.
        assert (
            classify_playlist_type("PLxyz", "Watch later") is PlaylistType.WATCH_LATER
        )


class TestNameMatching:
    """Case-insensitive, whitespace-trimmed English name matching (FR-002)."""

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("Watch later", PlaylistType.WATCH_LATER),
            ("History", PlaylistType.HISTORY),
            ("Liked videos", PlaylistType.LIKED),
            ("Favorites", PlaylistType.FAVORITES),
        ],
    )
    def test_known_system_names(self, name: str, expected: PlaylistType) -> None:
        assert classify_playlist_type(None, name) is expected

    @pytest.mark.parametrize(
        "name",
        ["watch later", "WATCH LATER", "  Watch later  ", "wAtCh LaTeR"],
    )
    def test_name_match_is_case_insensitive_and_trimmed(self, name: str) -> None:
        assert classify_playlist_type(None, name) is PlaylistType.WATCH_LATER


class TestRegularFallback:
    """Anything unmatched → regular; total function, no exceptions (FR-002)."""

    @pytest.mark.parametrize(
        "youtube_id,name",
        [
            (None, "My Cool Playlist"),
            ("PLabc", "AI"),
            (None, ""),
            (None, "   "),
            ("", "Random"),
        ],
    )
    def test_unmatched_is_regular(self, youtube_id: str | None, name: str) -> None:
        assert classify_playlist_type(youtube_id, name) is PlaylistType.REGULAR

    def test_none_name_is_regular(self) -> None:
        # Defensive: even a None name must not raise.
        assert classify_playlist_type(None, None) is PlaylistType.REGULAR  # type: ignore[arg-type]
