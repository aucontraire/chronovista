"""
CLI commands for transcript segment queries.

Provides commands for navigating video transcripts by timestamp:
- transcript segment: Get segment at specific timestamp
- transcript context: Get segments within time window
- transcript range: Get segments within time range
"""

from __future__ import annotations

from typing import Annotated, List, Optional

import typer
from rich.console import Console

from chronovista.config.database import db_manager
from chronovista.models.youtube_types import VideoId
from chronovista.repositories.transcript_segment_repository import (
    TranscriptSegmentRepository,
)
from chronovista.repositories.video_transcript_repository import (
    VideoTranscriptRepository,
)
from chronovista.services.segment_service import (
    OutputFormat,
    format_segment_human,
    format_segment_json,
    format_segment_srt,
    format_segments_human,
    format_segments_json,
    format_segments_srt,
    parse_timestamp,
)
from chronovista.cli.sync.base import run_sync_operation

# Initialize CLI app and console
transcript_app = typer.Typer(
    name="transcript",
    help="Query transcript segments by timestamp.",
    no_args_is_help=True,
)
console = Console()
err_console = Console(stderr=True)

# Exit codes
EXIT_SUCCESS = 0
EXIT_NO_TRANSCRIPT = 1
EXIT_INVALID_TIMESTAMP = 2
EXIT_NO_SEGMENT = 3
EXIT_INVALID_RANGE = 4

# Constants
DEFAULT_WINDOW = 30.0
MAX_WINDOW = 3600.0
DEFAULT_LANGUAGE = "en"
LARGE_SEGMENT_WARNING_THRESHOLD = 5000  # NFR-PERF-04


@transcript_app.command("segment")
def segment_command(
    video_id: Annotated[str, typer.Argument(help="YouTube video ID")],
    timestamp: Annotated[str, typer.Argument(help="Timestamp (e.g., 1:30 or 00:01:30)")],
    language: Annotated[str, typer.Option("--language", "-l", help="Language code")] = DEFAULT_LANGUAGE,
    format: Annotated[OutputFormat, typer.Option("--format", "-f", help="Output format")] = OutputFormat.HUMAN,
) -> None:
    """Get the transcript segment at a specific timestamp.

    Examples:
        chronovista transcript segment dQw4w9WgXcQ 1:30
        chronovista transcript segment dQw4w9WgXcQ 00:01:30 --format json
        chronovista transcript segment dQw4w9WgXcQ 90 --language es
    """
    # Parse timestamp
    try:
        time_seconds = parse_timestamp(timestamp)
    except ValueError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(EXIT_INVALID_TIMESTAMP)

    async def _query() -> int:
        """Query segment at timestamp."""
        # Get database session
        async for session in db_manager.get_session():
            # Check transcript exists
            transcript_repo = VideoTranscriptRepository()
            transcript = await transcript_repo.get_by_composite_key(
                session, VideoId(video_id), language
            )

            if not transcript:
                err_console.print(
                    f"[yellow]No transcript found for video {video_id} "
                    f"in language '{language}'.[/yellow]"
                )
                err_console.print(
                    "Run [bold]chronovista sync transcripts {video_id}[/bold] first."
                )
                return EXIT_NO_TRANSCRIPT

            # Warn for large transcripts (NFR-PERF-04)
            if transcript.segment_count and transcript.segment_count > LARGE_SEGMENT_WARNING_THRESHOLD:
                err_console.print(
                    f"[yellow]Note:[/yellow] This transcript has {transcript.segment_count:,} segments. "
                    "Consider using specific timestamp or range queries for better performance."
                )

            # Query segment
            segment_repo = TranscriptSegmentRepository()
            segment = await segment_repo.get_segment_at_time(
                session, VideoId(video_id), language, time_seconds
            )

            if not segment:
                err_console.print(
                    f"[yellow]No segment found at timestamp {timestamp}.[/yellow]"
                )
                return EXIT_NO_SEGMENT

            # Format output
            from chronovista.models.transcript_segment import TranscriptSegment as TSPydantic
            pydantic_segment = TSPydantic.model_validate(segment)

            if format == OutputFormat.HUMAN:
                console.print(format_segment_human(pydantic_segment))
            elif format == OutputFormat.JSON:
                console.print(format_segment_json(pydantic_segment))
            elif format == OutputFormat.SRT:
                console.print(format_segment_srt(pydantic_segment, sequence=1))

            return EXIT_SUCCESS

        # Fallback if session loop doesn't execute
        return EXIT_SUCCESS

    exit_code = run_sync_operation(_query, "Transcript Segment Query")
    if exit_code is not None:
        raise typer.Exit(exit_code)


@transcript_app.command("context")
def context_command(
    video_id: Annotated[str, typer.Argument(help="YouTube video ID")],
    timestamp: Annotated[str, typer.Argument(help="Center timestamp")],
    window: Annotated[float, typer.Option("--window", "-w", help="Window size in seconds")] = DEFAULT_WINDOW,
    language: Annotated[str, typer.Option("--language", "-l", help="Language code")] = DEFAULT_LANGUAGE,
    format: Annotated[OutputFormat, typer.Option("--format", "-f", help="Output format")] = OutputFormat.HUMAN,
) -> None:
    """Get transcript segments within a context window around a timestamp.

    Returns segments from (timestamp - window) to (timestamp + window).
    Default window is 30 seconds, maximum is 3600 seconds (1 hour).

    Examples:
        chronovista transcript context dQw4w9WgXcQ 5:00
        chronovista transcript context dQw4w9WgXcQ 5:00 --window 60
        chronovista transcript context dQw4w9WgXcQ 5:00 --format json
    """
    # Parse timestamp
    try:
        time_seconds = parse_timestamp(timestamp)
    except ValueError as e:
        err_console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(EXIT_INVALID_TIMESTAMP)

    # Clamp window size per FR-CTX-02/03
    actual_window = window
    if window > MAX_WINDOW:
        actual_window = MAX_WINDOW
        err_console.print(
            f"[yellow]Window clamped to {int(MAX_WINDOW)}s (1 hour maximum). "
            f"Use 'transcript range' for full extraction.[/yellow]"
        )

    async def _query() -> int:
        """Query context window around timestamp."""
        async for session in db_manager.get_session():
            # Check transcript exists
            transcript_repo = VideoTranscriptRepository()
            transcript = await transcript_repo.get_by_composite_key(
                session, VideoId(video_id), language
            )

            if not transcript:
                err_console.print(
                    f"[yellow]No transcript found for video {video_id} "
                    f"in language '{language}'.[/yellow]"
                )
                return EXIT_NO_TRANSCRIPT

            # Warn for large transcripts (NFR-PERF-04)
            if transcript.segment_count and transcript.segment_count > LARGE_SEGMENT_WARNING_THRESHOLD:
                err_console.print(
                    f"[yellow]Note:[/yellow] This transcript has {transcript.segment_count:,} segments. "
                    "Query results may take longer for large transcripts."
                )

            # Query segments
            segment_repo = TranscriptSegmentRepository()
            segments = await segment_repo.get_context_window(
                session, VideoId(video_id), language, time_seconds, actual_window
            )

            if not segments:
                err_console.print(
                    f"[yellow]No segments found in context window.[/yellow]"
                )
                return EXIT_SUCCESS  # Not an error, just empty result

            # Convert to Pydantic
            from chronovista.models.transcript_segment import TranscriptSegment as TSPydantic
            pydantic_segments = [TSPydantic.model_validate(s) for s in segments]

            # Format output
            title = f"Context around {timestamp} (±{int(actual_window)}s)"
            if format == OutputFormat.HUMAN:
                console.print(format_segments_human(pydantic_segments, title=title))
            elif format == OutputFormat.JSON:
                console.print(format_segments_json(
                    pydantic_segments, video_id=video_id, language_code=language
                ))
            elif format == OutputFormat.SRT:
                console.print(format_segments_srt(pydantic_segments))

            return EXIT_SUCCESS

        # Fallback if session loop doesn't execute
        return EXIT_SUCCESS

    exit_code = run_sync_operation(_query, "Transcript Context Query")
    if exit_code is not None:
        raise typer.Exit(exit_code)


@transcript_app.command("range")
def range_command(
    video_id: Annotated[str, typer.Argument(help="YouTube video ID")],
    start: Annotated[str, typer.Argument(help="Start timestamp")],
    end: Annotated[str, typer.Argument(help="End timestamp")],
    language: Annotated[str, typer.Option("--language", "-l", help="Language code")] = DEFAULT_LANGUAGE,
    format: Annotated[OutputFormat, typer.Option("--format", "-f", help="Output format")] = OutputFormat.HUMAN,
) -> None:
    """Get all transcript segments within a time range.

    Returns segments overlapping with the specified time range.
    Useful for extracting specific portions of a transcript.

    Examples:
        chronovista transcript range dQw4w9WgXcQ 5:00 10:00
        chronovista transcript range dQw4w9WgXcQ 5:00 10:00 --format srt
        chronovista transcript range dQw4w9WgXcQ 0:00 2:00:00 --format json
    """
    # Parse timestamps
    try:
        start_seconds = parse_timestamp(start)
    except ValueError as e:
        err_console.print(f"[red]Error:[/red] Invalid start timestamp: {e}")
        raise typer.Exit(EXIT_INVALID_TIMESTAMP)

    try:
        end_seconds = parse_timestamp(end)
    except ValueError as e:
        err_console.print(f"[red]Error:[/red] Invalid end timestamp: {e}")
        raise typer.Exit(EXIT_INVALID_TIMESTAMP)

    # Validate range
    if end_seconds <= start_seconds:
        err_console.print(
            f"[red]Error:[/red] End time ({end}) must be after start time ({start})."
        )
        raise typer.Exit(EXIT_INVALID_RANGE)

    async def _query() -> int:
        """Query segments in range."""
        async for session in db_manager.get_session():
            # Check transcript exists
            transcript_repo = VideoTranscriptRepository()
            transcript = await transcript_repo.get_by_composite_key(
                session, VideoId(video_id), language
            )

            if not transcript:
                err_console.print(
                    f"[yellow]No transcript found for video {video_id} "
                    f"in language '{language}'.[/yellow]"
                )
                return EXIT_NO_TRANSCRIPT

            # Warn for large transcripts (NFR-PERF-04)
            if transcript.segment_count and transcript.segment_count > LARGE_SEGMENT_WARNING_THRESHOLD:
                err_console.print(
                    f"[yellow]Note:[/yellow] This transcript has {transcript.segment_count:,} segments. "
                    "Large range queries may take longer to complete."
                )

            # Query segments
            segment_repo = TranscriptSegmentRepository()
            segments = await segment_repo.get_segments_in_range(
                session, VideoId(video_id), language, start_seconds, end_seconds
            )

            if not segments:
                err_console.print(
                    f"[yellow]No segments found in range {start} to {end}.[/yellow]"
                )
                return EXIT_SUCCESS

            # Convert to Pydantic
            from chronovista.models.transcript_segment import TranscriptSegment as TSPydantic
            pydantic_segments = [TSPydantic.model_validate(s) for s in segments]

            # Format output
            duration = end_seconds - start_seconds
            title = f"Segments from {start} to {end} ({duration:.1f}s)"
            if format == OutputFormat.HUMAN:
                console.print(format_segments_human(pydantic_segments, title=title))
            elif format == OutputFormat.JSON:
                console.print(format_segments_json(
                    pydantic_segments, video_id=video_id, language_code=language
                ))
            elif format == OutputFormat.SRT:
                console.print(format_segments_srt(pydantic_segments))

            return EXIT_SUCCESS

        # Fallback if session loop doesn't execute
        return EXIT_SUCCESS

    exit_code = run_sync_operation(_query, "Transcript Range Query")
    if exit_code is not None:
        raise typer.Exit(exit_code)


# Export app for registration
__all__ = ["transcript_app"]
