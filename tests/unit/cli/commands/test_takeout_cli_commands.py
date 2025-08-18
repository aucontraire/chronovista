"""
Tests for CLI command entry points in takeout.py.

Comprehensive test coverage for the main Typer CLI command functions:
- peek_data
- analyze_takeout
- analyze_relationships
- inspect_file

These tests focus on the actual CLI command entry points that weren't covered
in the existing test_takeout.py file.
"""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest
import typer

from chronovista.models.takeout import (
    DateRange,
    PlaylistAnalysis,
    TakeoutAnalysis,
    TakeoutSubscription,
    ViewingPatterns,
)
from tests.factories.takeout_data_factory import create_takeout_data
from tests.factories.takeout_playlist_factory import create_takeout_playlist
from tests.factories.takeout_playlist_item_factory import create_takeout_playlist_item
from tests.factories.takeout_watch_entry_factory import create_takeout_watch_entry

# Note: Most tests are sync since they test CLI command entry points directly


class TestPeekDataCommand:
    """Tests for the peek_data CLI command entry point."""

    @pytest.fixture
    def sample_takeout_data(self):
        """Create sample takeout data for testing."""
        return create_takeout_data(
            takeout_path=Path("test/takeout"),
            watch_history=[
                create_takeout_watch_entry(
                    title="Test Video",
                    title_url="https://youtube.com/watch?v=test123",
                    channel_name="Test Channel",
                    channel_url="https://youtube.com/channel/UCtest",
                    raw_time="2023-01-01T10:00:00Z",
                )
            ],
            playlists=[
                create_takeout_playlist(
                    name="Test Playlist",
                    file_path=Path("test.csv"),
                    videos=[
                        create_takeout_playlist_item(
                            video_id="test123", raw_timestamp="2023-01-01T10:00:00Z"
                        )
                    ],
                )
            ],
            subscriptions=[
                TakeoutSubscription(
                    channel_id="UCtest",
                    channel_title="Test Channel",
                    channel_url="https://youtube.com/channel/UCtest",
                )
            ],
        )

    @patch("chronovista.cli.commands.takeout.TakeoutService")
    @patch("chronovista.cli.commands.takeout.console")
    def test_peek_data_playlists_success(
        self, mock_console, mock_takeout_service_class, sample_takeout_data
    ):
        """Test peek_data command with playlists data type."""
        from chronovista.cli.commands.takeout import peek_data

        # Setup mock
        mock_service = AsyncMock()
        mock_service.parse_playlists.return_value = sample_takeout_data.playlists
        mock_takeout_service_class.return_value = mock_service

        # Call function
        peek_data(
            data_type="playlists",
            filter_name=None,
            takeout_path=Path("test/takeout"),
            limit=20,
            recent=False,
            oldest=False,
            all_items=False,
            topic_filter=None,
        )

        # Verify TakeoutService was created correctly
        mock_takeout_service_class.assert_called_once_with(Path("test/takeout"))

        # Verify console output was called
        mock_console.print.assert_called()

    @patch("chronovista.cli.commands.takeout.TakeoutService")
    @patch("chronovista.cli.commands.takeout.console")
    def test_peek_data_history_with_filter(
        self, mock_console, mock_takeout_service_class, sample_takeout_data
    ):
        """Test peek_data command with history data type and channel filter."""
        from chronovista.cli.commands.takeout import peek_data

        # Setup mock
        mock_service = AsyncMock()
        mock_service.parse_watch_history.return_value = (
            sample_takeout_data.watch_history
        )
        mock_takeout_service_class.return_value = mock_service

        # Call function
        peek_data(
            data_type="history",
            filter_name="Test Channel",
            takeout_path=Path("test/takeout"),
            limit=10,
            recent=True,
            oldest=False,
            all_items=False,
            topic_filter=None,
        )

        # Verify TakeoutService was created correctly
        mock_takeout_service_class.assert_called_once_with(Path("test/takeout"))

        # Verify console output was called
        mock_console.print.assert_called()

    @patch("chronovista.cli.commands.takeout.TakeoutService")
    @patch("chronovista.cli.commands.takeout.console")
    def test_peek_data_subscriptions_all_items(
        self, mock_console, mock_takeout_service_class, sample_takeout_data
    ):
        """Test peek_data command with subscriptions and all items flag."""
        from chronovista.cli.commands.takeout import peek_data

        # Setup mock
        mock_service = AsyncMock()
        mock_service.parse_subscriptions.return_value = (
            sample_takeout_data.subscriptions
        )
        mock_takeout_service_class.return_value = mock_service

        # Call function
        peek_data(
            data_type="subscriptions",
            filter_name=None,
            takeout_path=Path("test/takeout"),
            limit=20,
            recent=False,
            oldest=False,
            all_items=True,
            topic_filter=None,
        )

        # Verify TakeoutService was created correctly
        mock_takeout_service_class.assert_called_once_with(Path("test/takeout"))

        # Verify console output was called
        mock_console.print.assert_called()

    @patch("chronovista.cli.commands.takeout.TakeoutService")
    @patch("chronovista.cli.commands.takeout.console")
    def test_peek_data_invalid_data_type(
        self, mock_console, mock_takeout_service_class
    ):
        """Test peek_data command with invalid data type."""
        from chronovista.cli.commands.takeout import peek_data

        # Setup mock
        mock_service = AsyncMock()
        mock_takeout_service_class.return_value = mock_service

        # Call function - should exit with error
        with pytest.raises(typer.Exit) as exc_info:
            peek_data(
                data_type="invalid_type",
                filter_name=None,
                takeout_path=Path("test/takeout"),
                limit=20,
                recent=False,
                oldest=False,
                all_items=False,
                topic_filter=None,
            )

        # Verify exit code
        assert exc_info.value.exit_code == 1

        # Verify error message was printed
        mock_console.print.assert_any_call("❌ Unknown data type: invalid_type")

    @patch("chronovista.cli.commands.takeout.TakeoutService")
    @patch("chronovista.cli.commands.takeout.console")
    def test_peek_data_recent_and_oldest_flags(
        self, mock_console, mock_takeout_service_class
    ):
        """Test peek_data command with both recent and oldest flags (should error)."""
        from chronovista.cli.commands.takeout import peek_data

        # Setup mock
        mock_service = AsyncMock()
        mock_takeout_service_class.return_value = mock_service

        # Call function - should exit with error
        with pytest.raises(typer.Exit) as exc_info:
            peek_data(
                data_type="playlists",
                filter_name=None,
                takeout_path=Path("test/takeout"),
                limit=20,
                recent=True,
                oldest=True,
                all_items=False,
                topic_filter=None,
            )

        # Verify exit code
        assert exc_info.value.exit_code == 1

        # Verify error message was printed
        mock_console.print.assert_any_call(
            "❌ Cannot use both --recent and --oldest flags"
        )

    @patch("chronovista.cli.commands.takeout.TakeoutService")
    @patch("chronovista.cli.commands.takeout.console")
    def test_peek_data_takeout_parsing_error(
        self, mock_console, mock_takeout_service_class
    ):
        """Test peek_data command with TakeoutParsingError."""
        from chronovista.cli.commands.takeout import peek_data
        from chronovista.services.takeout_service import TakeoutParsingError

        # Setup mock to raise error
        mock_takeout_service_class.side_effect = TakeoutParsingError(
            "Test parsing error"
        )

        # Call function - should exit with error
        with pytest.raises(typer.Exit) as exc_info:
            peek_data(
                data_type="playlists",
                filter_name=None,
                takeout_path=Path("test/takeout"),
                limit=20,
                recent=False,
                oldest=False,
                all_items=False,
            )

        # Verify exit code
        assert exc_info.value.exit_code == 1

        # Verify error messages were printed
        mock_console.print.assert_any_call(
            "❌ Error parsing Takeout data: Test parsing error"
        )
        mock_console.print.assert_any_call("\n💡 Make sure:")

    @patch("chronovista.cli.commands.takeout.TakeoutService")
    @patch("chronovista.cli.commands.takeout.console")
    def test_peek_data_comments_data_type(
        self, mock_console, mock_takeout_service_class
    ):
        """Test peek_data command with comments data type."""
        from chronovista.cli.commands.takeout import peek_data

        # Setup mock
        mock_service = AsyncMock()
        mock_takeout_service_class.return_value = mock_service

        # Call function
        peek_data(
            data_type="comments",
            filter_name=None,
            takeout_path=Path("test/takeout"),
            limit=20,
            recent=False,
            oldest=False,
            all_items=False,
            topic_filter=None,
        )

        # Verify TakeoutService was created correctly
        mock_takeout_service_class.assert_called_once_with(Path("test/takeout"))

        # Verify console output was called
        mock_console.print.assert_called()

    @patch("chronovista.cli.commands.takeout.TakeoutService")
    @patch("chronovista.cli.commands.takeout.console")
    def test_peek_data_live_chats_data_type(
        self, mock_console, mock_takeout_service_class
    ):
        """Test peek_data command with live chats data type."""
        from chronovista.cli.commands.takeout import peek_data

        # Setup mock
        mock_service = AsyncMock()
        mock_takeout_service_class.return_value = mock_service

        # Call function
        peek_data(
            data_type="chats",
            filter_name=None,
            takeout_path=Path("test/takeout"),
            limit=20,
            recent=False,
            oldest=False,
            all_items=False,
            topic_filter=None,
        )

        # Verify TakeoutService was created correctly
        mock_takeout_service_class.assert_called_once_with(Path("test/takeout"))

        # Verify console output was called
        mock_console.print.assert_called()


class TestAnalyzeComprehensiveCommand:
    """Tests for the analyze_comprehensive CLI command entry point."""

    @pytest.fixture
    def sample_analysis_data(self):
        """Create sample analysis data for testing."""
        return TakeoutAnalysis(
            total_videos_watched=100,
            unique_channels=25,
            playlist_count=5,
            subscription_count=50,
            date_range=DateRange(
                start_date=datetime(2022, 1, 1, tzinfo=timezone.utc),
                end_date=datetime(2023, 12, 31, tzinfo=timezone.utc),
                total_days=730,
            ),
            data_completeness=0.8,
            viewing_patterns=ViewingPatterns(
                peak_viewing_hours=[20, 21, 22],
                peak_viewing_days=["Saturday", "Sunday"],
                viewing_frequency=2.5,
                top_channels=[],
                channel_diversity=0.75,
                playlist_usage=0.3,
                subscription_engagement=0.6,
            ),
            playlist_analysis=PlaylistAnalysis(),
            top_channels=[],
            content_gaps=[],
            high_priority_videos=[],
            content_diversity_score=0.8,
            analysis_version="1.0",
        )

    @patch("chronovista.cli.commands.takeout.TakeoutService")
    @patch("chronovista.cli.commands.takeout.console")
    def test_analyze_comprehensive_success(
        self, mock_console, mock_takeout_service_class, sample_analysis_data
    ):
        """Test analyze_takeout command successful execution."""
        from chronovista.cli.commands.takeout import analyze_comprehensive

        # Setup mock
        mock_service = AsyncMock()
        mock_service.generate_comprehensive_analysis.return_value = sample_analysis_data
        mock_takeout_service_class.return_value = mock_service

        # Call function
        analyze_comprehensive(
            takeout_path=Path("test/takeout"),
            save_report=False,
            by_topic=False,
            topic_filter=None,
        )

        # Verify TakeoutService was created correctly
        mock_takeout_service_class.assert_called_once_with(Path("test/takeout"))

        # Verify analysis was called
        mock_service.generate_comprehensive_analysis.assert_called_once()

        # Verify console output was called
        mock_console.print.assert_called()

    @patch("chronovista.cli.commands.takeout.TakeoutService")
    @patch("chronovista.cli.commands.takeout.console")
    @patch("builtins.open", new_callable=mock_open)
    def test_analyze_comprehensive_save_report(
        self,
        mock_file_open,
        mock_console,
        mock_takeout_service_class,
        sample_analysis_data,
    ):
        """Test analyze_takeout command with JSON export."""
        from chronovista.cli.commands.takeout import analyze_comprehensive

        # Setup mock
        mock_service = AsyncMock()
        mock_service.generate_comprehensive_analysis.return_value = sample_analysis_data
        mock_takeout_service_class.return_value = mock_service

        # Call function
        analyze_comprehensive(
            takeout_path=Path("test/takeout"),
            save_report=True,
            by_topic=False,
            topic_filter=None,
        )

        # Verify TakeoutService was created correctly
        mock_takeout_service_class.assert_called_once_with(Path("test/takeout"))

        # Verify analysis was called
        mock_service.generate_comprehensive_analysis.assert_called_once()

        # Verify file was opened for writing
        mock_file_open.assert_called()

        # Verify console output was called
        mock_console.print.assert_called()

    @patch("chronovista.cli.commands.takeout.TakeoutService")
    @patch("chronovista.cli.commands.takeout.console")
    def test_analyze_comprehensive_parsing_error(
        self, mock_console, mock_takeout_service_class
    ):
        """Test analyze_takeout command with TakeoutParsingError."""
        from chronovista.cli.commands.takeout import analyze_comprehensive
        from chronovista.services.takeout_service import TakeoutParsingError

        # Setup mock to raise error
        mock_takeout_service_class.side_effect = TakeoutParsingError(
            "Test parsing error"
        )

        # Call function - should exit with error
        with pytest.raises(typer.Exit) as exc_info:
            analyze_comprehensive(
                takeout_path=Path("test/takeout"),
                save_report=False,
                by_topic=False,
                topic_filter=None,
            )

        # Verify exit code
        assert exc_info.value.exit_code == 1

        # Verify error message was printed
        mock_console.print.assert_any_call("❌ Analysis failed: Test parsing error")

    @patch("chronovista.cli.commands.takeout.TakeoutService")
    @patch("chronovista.cli.commands.takeout.console")
    def test_analyze_comprehensive_generic_exception(
        self, mock_console, mock_takeout_service_class
    ):
        """Test analyze_takeout command with generic exception."""
        from chronovista.cli.commands.takeout import analyze_comprehensive

        # Setup mock to raise error
        mock_takeout_service_class.side_effect = Exception("Generic error")

        # Call function - should exit with error
        with pytest.raises(typer.Exit) as exc_info:
            analyze_comprehensive(
                takeout_path=Path("test/takeout"),
                save_report=False,
                by_topic=False,
                topic_filter=None,
            )

        # Verify exit code
        assert exc_info.value.exit_code == 1

        # Verify error message was printed
        mock_console.print.assert_any_call("❌ Analysis failed: Generic error")


class TestAnalyzeRelationshipsCommand:
    """Tests for the analyze_relationships CLI command entry point."""

    @pytest.fixture
    def sample_takeout_data_with_relationships(self):
        """Create sample takeout data with relationships for testing."""
        return create_takeout_data(
            takeout_path=Path("test/takeout"),
            watch_history=[
                create_takeout_watch_entry(
                    title="Video 1",
                    title_url="https://youtube.com/watch?v=test123",
                    channel_name="Channel A",
                    channel_url="https://youtube.com/channel/UCA",
                    raw_time="2023-01-01T10:00:00Z",
                ),
                create_takeout_watch_entry(
                    title="Video 2",
                    title_url="https://youtube.com/watch?v=test456",
                    channel_name="Channel B",
                    channel_url="https://youtube.com/channel/UCB",
                    raw_time="2023-01-02T11:00:00Z",
                ),
            ],
            playlists=[
                create_takeout_playlist(
                    name="Playlist A",
                    file_path=Path("playlist_a.csv"),
                    videos=[
                        create_takeout_playlist_item(
                            video_id="test123", raw_timestamp="2023-01-01T10:00:00Z"
                        ),
                        create_takeout_playlist_item(
                            video_id="test456", raw_timestamp="2023-01-02T11:00:00Z"
                        ),
                    ],
                ),
                create_takeout_playlist(
                    name="Playlist B",
                    file_path=Path("playlist_b.csv"),
                    videos=[
                        create_takeout_playlist_item(
                            video_id="test123", raw_timestamp="2023-01-01T10:00:00Z"
                        )
                    ],
                ),
            ],
            subscriptions=[
                TakeoutSubscription(
                    channel_id="UCA",
                    channel_title="Channel A",
                    channel_url="https://youtube.com/channel/UCA",
                )
            ],
        )

    @patch("chronovista.cli.commands.takeout.TakeoutService")
    @patch("chronovista.cli.commands.takeout.console")
    def test_analyze_relationships_playlist_overlap(
        self,
        mock_console,
        mock_takeout_service_class,
        sample_takeout_data_with_relationships,
    ):
        """Test analyze_relationships command with playlist overlap analysis."""
        from chronovista.cli.commands.takeout import analyze_relationships

        # Setup mock
        mock_service = AsyncMock()
        mock_service.parse_all.return_value = sample_takeout_data_with_relationships
        mock_service.analyze_playlist_overlap.return_value = {
            "Playlist A": {"Playlist B": 1}
        }
        mock_takeout_service_class.return_value = mock_service

        # Call function
        analyze_relationships(
            relationship_type="playlist-overlap", takeout_path=Path("test/takeout")
        )

        # Verify TakeoutService was created correctly
        mock_takeout_service_class.assert_called_once_with(Path("test/takeout"))

        # Verify analysis was called
        mock_service.analyze_playlist_overlap.assert_called_once()

        # Verify console output was called
        mock_console.print.assert_called()

    @patch("chronovista.cli.commands.takeout._analyze_channel_clusters")
    @patch("chronovista.cli.commands.takeout.TakeoutService")
    @patch("chronovista.cli.commands.takeout.console")
    def test_analyze_relationships_channel_clusters(
        self,
        mock_console,
        mock_takeout_service_class,
        mock_analyze_channel_clusters,
        sample_takeout_data_with_relationships,
    ):
        """Test analyze_relationships command with channel clusters analysis."""
        from chronovista.cli.commands.takeout import analyze_relationships

        # Setup mocks
        mock_service = AsyncMock()
        mock_takeout_service_class.return_value = mock_service
        mock_analyze_channel_clusters.return_value = None  # async function returns None

        # Call function
        analyze_relationships(
            relationship_type="channel-clusters", takeout_path=Path("test/takeout")
        )

        # Verify TakeoutService was created correctly
        mock_takeout_service_class.assert_called_once_with(Path("test/takeout"))

        # Verify the helper function was called
        mock_analyze_channel_clusters.assert_called_once()

    @patch("chronovista.cli.commands.takeout._analyze_temporal_patterns")
    @patch("chronovista.cli.commands.takeout.TakeoutService")
    @patch("chronovista.cli.commands.takeout.console")
    def test_analyze_relationships_temporal_patterns(
        self,
        mock_console,
        mock_takeout_service_class,
        mock_analyze_temporal_patterns,
        sample_takeout_data_with_relationships,
    ):
        """Test analyze_relationships command with temporal patterns analysis."""
        from chronovista.cli.commands.takeout import analyze_relationships

        # Setup mocks
        mock_service = AsyncMock()
        mock_takeout_service_class.return_value = mock_service
        mock_analyze_temporal_patterns.return_value = (
            None  # async function returns None
        )

        # Call function
        analyze_relationships(
            relationship_type="temporal-patterns", takeout_path=Path("test/takeout")
        )

        # Verify TakeoutService was created correctly
        mock_takeout_service_class.assert_called_once_with(Path("test/takeout"))

        # Verify the helper function was called
        mock_analyze_temporal_patterns.assert_called_once()

    @patch("chronovista.cli.commands.takeout.TakeoutService")
    @patch("chronovista.cli.commands.takeout.console")
    def test_analyze_relationships_invalid_analysis_type(
        self, mock_console, mock_takeout_service_class
    ):
        """Test analyze_relationships command with invalid analysis type."""
        from chronovista.cli.commands.takeout import analyze_relationships

        # Setup mock
        mock_service = AsyncMock()
        mock_takeout_service_class.return_value = mock_service

        # Call function - should exit with error
        with pytest.raises(typer.Exit) as exc_info:
            analyze_relationships(
                relationship_type="invalid-type", takeout_path=Path("test/takeout")
            )

        # Verify exit code
        assert exc_info.value.exit_code == 1

        # Verify error message was printed
        mock_console.print.assert_any_call("❌ Unknown relationship type: invalid-type")

    @patch("chronovista.cli.commands.takeout.TakeoutService")
    @patch("chronovista.cli.commands.takeout.console")
    def test_analyze_relationships_parsing_error(
        self, mock_console, mock_takeout_service_class
    ):
        """Test analyze_relationships command with TakeoutParsingError."""
        from chronovista.cli.commands.takeout import analyze_relationships
        from chronovista.services.takeout_service import TakeoutParsingError

        # Setup mock to raise error
        mock_takeout_service_class.side_effect = TakeoutParsingError(
            "Test parsing error"
        )

        # Call function - should exit with error
        with pytest.raises(typer.Exit) as exc_info:
            analyze_relationships(
                relationship_type="playlist-overlap", takeout_path=Path("test/takeout")
            )

        # Verify exit code
        assert exc_info.value.exit_code == 1

        # Verify error message was printed
        mock_console.print.assert_any_call(
            "❌ Error parsing Takeout data: Test parsing error"
        )


class TestInspectFileCommand:
    """Tests for the inspect_file CLI command entry point."""

    @patch("chronovista.cli.commands.takeout.Path.exists")
    @patch("chronovista.cli.commands.takeout.console")
    def test_inspect_file_nonexistent_file(self, mock_console, mock_exists):
        """Test inspect_file command with non-existent file."""
        from chronovista.cli.commands.takeout import inspect_file

        # Setup mock
        mock_exists.return_value = False

        # Call function - should exit with error
        with pytest.raises(typer.Exit) as exc_info:
            inspect_file(Path("nonexistent.csv"))

        # Verify exit code
        assert exc_info.value.exit_code == 1

        # Verify error message was printed
        mock_console.print.assert_any_call("❌ File not found: nonexistent.csv")

    @patch("chronovista.cli.commands.takeout.Path.exists")
    @patch("chronovista.cli.commands.takeout._inspect_csv_file")
    @patch("asyncio.run")
    @patch("chronovista.cli.commands.takeout.console")
    def test_inspect_file_csv_success(
        self, mock_console, mock_asyncio_run, mock_inspect_csv, mock_exists
    ):
        """Test inspect_file command with CSV file."""
        from chronovista.cli.commands.takeout import inspect_file

        # Setup mocks
        mock_exists.return_value = True
        mock_inspect_csv.return_value = None  # async function returns None

        # Mock asyncio.run to execute the async function immediately
        def run_mock(coro):
            import asyncio

            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        mock_asyncio_run.side_effect = run_mock

        # Call function
        inspect_file(Path("test.csv"))

        # Verify asyncio.run was called
        mock_asyncio_run.assert_called_once()
        # Verify _inspect_csv_file was called
        mock_inspect_csv.assert_called_once()

    @patch("chronovista.cli.commands.takeout.Path.exists")
    @patch("chronovista.cli.commands.takeout._inspect_json_file")
    @patch("asyncio.run")
    @patch("chronovista.cli.commands.takeout.console")
    def test_inspect_file_json_success(
        self, mock_console, mock_asyncio_run, mock_inspect_json, mock_exists
    ):
        """Test inspect_file command with JSON file."""
        from chronovista.cli.commands.takeout import inspect_file

        # Setup mocks
        mock_exists.return_value = True
        mock_inspect_json.return_value = None  # async function returns None

        # Mock asyncio.run to execute the async function immediately
        def run_mock(coro):
            import asyncio

            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()

        mock_asyncio_run.side_effect = run_mock

        # Call function
        inspect_file(Path("test.json"))

        # Verify asyncio.run was called
        mock_asyncio_run.assert_called_once()
        # Verify _inspect_json_file was called
        mock_inspect_json.assert_called_once()

    @patch("chronovista.cli.commands.takeout.Path.exists")
    @patch("chronovista.cli.commands.takeout.console")
    def test_inspect_file_unsupported_extension(self, mock_console, mock_exists):
        """Test inspect_file command with unsupported file extension."""
        from chronovista.cli.commands.takeout import inspect_file

        # Setup mock
        mock_exists.return_value = True

        # Call function - should exit with error
        with pytest.raises(typer.Exit) as exc_info:
            inspect_file(Path("test.txt"))

        # Verify exit code
        assert exc_info.value.exit_code == 1

        # Verify error message was printed
        mock_console.print.assert_any_call("❌ Unsupported file type: .txt")

    @patch("chronovista.cli.commands.takeout.Path.exists")
    @patch("chronovista.cli.commands.takeout._inspect_csv_file")
    @patch("chronovista.cli.commands.takeout.console")
    def test_inspect_file_inspection_exception(
        self, mock_console, mock_inspect_csv, mock_exists
    ):
        """Test inspect_file command with inspection exception."""
        from chronovista.cli.commands.takeout import inspect_file

        # Setup mocks
        mock_exists.return_value = True
        mock_inspect_csv.side_effect = Exception("Inspection error")

        # Call function - should exit with error
        with pytest.raises(typer.Exit) as exc_info:
            inspect_file(Path("test.csv"))

        # Verify exit code
        assert exc_info.value.exit_code == 1

        # Verify error message was printed
        mock_console.print.assert_any_call("❌ Error inspecting file: Inspection error")
