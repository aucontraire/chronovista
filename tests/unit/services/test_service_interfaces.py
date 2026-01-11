"""
Tests for service layer Abstract Base Classes (ABCs).

Tests verify:
1. ABCs cannot be instantiated directly (raises TypeError)
2. Concrete services properly implement their interfaces
3. ABCs define the expected abstract methods
"""

from typing import Any, FrozenSet

import pytest

from chronovista.services.interfaces import (
    TakeoutServiceInterface,
    TranscriptServiceInterface,
    YouTubeServiceInterface,
)
from chronovista.services.takeout_service import TakeoutService
from chronovista.services.transcript_service import TranscriptService
from chronovista.services.youtube_service import YouTubeService


class TestYouTubeServiceInterface:
    """Tests for YouTubeServiceInterface ABC."""

    def test_cannot_instantiate_abc_directly(self) -> None:
        """Verify YouTubeServiceInterface cannot be instantiated."""
        with pytest.raises(TypeError) as exc_info:
            YouTubeServiceInterface()  # type: ignore

        assert "abstract" in str(exc_info.value).lower()

    def test_concrete_class_is_instance_of_interface(self) -> None:
        """Verify YouTubeService is an instance of the interface."""
        assert issubclass(YouTubeService, YouTubeServiceInterface)

    def test_interface_has_expected_abstract_methods(self) -> None:
        """Verify YouTubeServiceInterface defines expected abstract methods."""
        abstract_methods: FrozenSet[str] = getattr(
            YouTubeServiceInterface, "__abstractmethods__", frozenset()
        )

        expected_methods = {
            "get_my_channel",
            "get_channel_details",
            "get_channel_videos",
            "get_video_details",
            "fetch_videos_batched",
            "get_video_captions",
            "download_caption",
            "get_video_categories",
            "get_my_playlists",
            "get_playlist_videos",
            "get_playlist_details",
            "fetch_playlists_batched",
            "get_my_watch_later_videos",
            "check_video_in_playlist",
            "get_user_playlists_for_video",
            "get_liked_videos",
            "get_subscription_channels",
            "search_my_videos",
            "check_credentials",
            "close",
        }

        assert expected_methods.issubset(abstract_methods), (
            f"Missing abstract methods: {expected_methods - abstract_methods}"
        )


class TestTranscriptServiceInterface:
    """Tests for TranscriptServiceInterface ABC."""

    def test_cannot_instantiate_abc_directly(self) -> None:
        """Verify TranscriptServiceInterface cannot be instantiated."""
        with pytest.raises(TypeError) as exc_info:
            TranscriptServiceInterface()  # type: ignore

        assert "abstract" in str(exc_info.value).lower()

    def test_concrete_class_is_instance_of_interface(self) -> None:
        """Verify TranscriptService is an instance of the interface."""
        assert issubclass(TranscriptService, TranscriptServiceInterface)

    def test_interface_has_expected_abstract_methods(self) -> None:
        """Verify TranscriptServiceInterface defines expected abstract methods."""
        abstract_methods: FrozenSet[str] = getattr(
            TranscriptServiceInterface, "__abstractmethods__", frozenset()
        )

        expected_methods = {
            "get_transcript",
            "get_available_languages",
            "batch_get_transcripts",
            "is_service_available",
        }

        assert expected_methods.issubset(abstract_methods), (
            f"Missing abstract methods: {expected_methods - abstract_methods}"
        )


class TestTakeoutServiceInterface:
    """Tests for TakeoutServiceInterface ABC."""

    def test_cannot_instantiate_abc_directly(self) -> None:
        """Verify TakeoutServiceInterface cannot be instantiated."""
        with pytest.raises(TypeError) as exc_info:
            TakeoutServiceInterface()  # type: ignore

        assert "abstract" in str(exc_info.value).lower()

    def test_concrete_class_is_subclass_of_interface(self) -> None:
        """Verify TakeoutService is a subclass of the interface."""
        assert issubclass(TakeoutService, TakeoutServiceInterface)

    def test_interface_has_expected_abstract_methods(self) -> None:
        """Verify TakeoutServiceInterface defines expected abstract methods."""
        abstract_methods: FrozenSet[str] = getattr(
            TakeoutServiceInterface, "__abstractmethods__", frozenset()
        )

        expected_methods = {
            "parse_all",
            "parse_watch_history",
            "parse_playlists",
            "parse_subscriptions",
            "analyze_viewing_patterns",
            "analyze_playlist_relationships",
            "find_content_gaps",
            "generate_comprehensive_analysis",
        }

        assert expected_methods.issubset(abstract_methods), (
            f"Missing abstract methods: {expected_methods - abstract_methods}"
        )


class TestPartialImplementation:
    """Tests verifying partial implementations fail correctly."""

    def test_partial_youtube_implementation_fails(self) -> None:
        """Verify partial implementation of YouTubeServiceInterface fails."""

        class PartialYouTubeService(YouTubeServiceInterface):
            """Partial implementation - missing most methods."""

            def check_credentials(self) -> bool:
                return True

        with pytest.raises(TypeError) as exc_info:
            PartialYouTubeService()  # type: ignore[abstract]

        # Should fail because not all abstract methods are implemented
        error_msg = str(exc_info.value)
        assert "abstract" in error_msg.lower()

    def test_partial_transcript_implementation_fails(self) -> None:
        """Verify partial implementation of TranscriptServiceInterface fails."""

        class PartialTranscriptService(TranscriptServiceInterface):
            """Partial implementation - only is_service_available."""

            def is_service_available(self) -> bool:
                return True

        with pytest.raises(TypeError) as exc_info:
            PartialTranscriptService()  # type: ignore[abstract]

        error_msg = str(exc_info.value)
        assert "abstract" in error_msg.lower()

    def test_partial_takeout_implementation_fails(self) -> None:
        """Verify partial implementation of TakeoutServiceInterface fails."""

        class PartialTakeoutService(TakeoutServiceInterface):
            """Partial implementation - only parse_all."""

            async def parse_all(self) -> Any:
                return None

        with pytest.raises(TypeError) as exc_info:
            PartialTakeoutService()  # type: ignore[abstract]

        error_msg = str(exc_info.value)
        assert "abstract" in error_msg.lower()
