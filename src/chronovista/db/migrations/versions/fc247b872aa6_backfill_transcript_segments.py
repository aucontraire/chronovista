"""backfill_transcript_segments

Revision ID: fc247b872aa6
Revises: 45339d47269e
Create Date: 2026-01-28 16:34:44.547913

This data migration extracts segment data from the raw_transcript_data JSONB
column and populates the transcript_segments table. It is designed to be
idempotent per FR-MIG-01.

WARNING: This migration processes existing data and may take several minutes
depending on the number of transcripts. Progress logging is provided.

Functional Requirements Implemented:
- FR-MIG-01: Migration is idempotent - safe to run multiple times
- FR-MIG-02: Each transcript backfill deletes existing segments before inserting
- FR-MIG-03: Migration commits after each transcript (not batch commit)
- FR-MIG-04: Migration logs progress and failures with video_id
- FR-MIG-05: Failed transcripts are logged but do not stop migration
- FR-MIG-06: Migration reports summary: total, succeeded, failed, skipped
- FR-MIG-15-19: Malformed data handling - skip with logging, continue

Related Tasks: T026-T029 (Feature 008: Transcript Segment Table - Phase 2)
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.orm import Session

# revision identifiers, used by Alembic.
revision = "fc247b872aa6"
down_revision = "45339d47269e"
branch_labels = None
depends_on = None

# Configure logging
logger = logging.getLogger("alembic.runtime.migration")


def upgrade() -> None:
    """Backfill transcript_segments from raw_transcript_data.

    This migration:
    1. Queries all video_transcripts with raw_transcript_data IS NOT NULL
    2. For each transcript, deletes existing segments (idempotent per FR-MIG-01)
    3. Extracts snippets from JSONB and creates segment rows
    4. Updates segment_count on the transcript
    5. Commits after each transcript (per FR-MIG-03)
    6. Reports summary at end (per FR-MIG-06)

    Malformed data is logged and skipped, not failed (per FR-MIG-05).
    """
    bind = op.get_bind()
    session = Session(bind=bind)

    # Statistics for FR-MIG-06
    total = 0
    succeeded = 0
    failed = 0
    skipped = 0

    try:
        logger.info("Starting transcript segment backfill migration")

        # Get all transcripts with raw data
        transcripts = session.execute(
            text("""
                SELECT video_id, language_code, raw_transcript_data
                FROM video_transcripts
                WHERE raw_transcript_data IS NOT NULL
            """)
        ).fetchall()

        total = len(transcripts)
        logger.info(f"Found {total} transcripts with raw_transcript_data")

        if total == 0:
            logger.info("No transcripts to process, migration complete")
            return

        # Process each transcript (FR-MIG-03: commit after each)
        for idx, (video_id, language_code, raw_data) in enumerate(transcripts, 1):
            try:
                # Progress logging (FR-MIG-04)
                if idx % 10 == 0 or idx == total:
                    logger.info(f"Processing transcript {idx}/{total}: {video_id}/{language_code}")

                # FR-MIG-02: Delete existing segments (idempotent)
                session.execute(
                    text("""
                        DELETE FROM transcript_segments
                        WHERE video_id = :video_id
                        AND language_code = :language_code
                    """),
                    {"video_id": video_id, "language_code": language_code},
                )

                # Extract snippets with validation (FR-MIG-15-19)
                snippets = raw_data.get("snippets", [])

                # FR-MIG-15: Skip if snippets is not a list
                if not isinstance(snippets, list):
                    logger.warning(
                        f"Skipping {video_id}/{language_code}: "
                        "snippets is not a list"
                    )
                    skipped += 1
                    session.commit()
                    continue

                # FR-MIG-16: Handle empty snippets array
                if not snippets:
                    # Empty snippets array - valid but no segments to create
                    session.execute(
                        text("""
                            UPDATE video_transcripts
                            SET segment_count = 0
                            WHERE video_id = :video_id
                            AND language_code = :language_code
                        """),
                        {"video_id": video_id, "language_code": language_code},
                    )
                    session.commit()
                    succeeded += 1
                    continue

                # Create segments with malformed data handling
                segment_count = 0
                snippet_errors = 0

                for seq, snippet in enumerate(snippets):
                    try:
                        # FR-MIG-17: Validate required fields exist
                        text_content = snippet.get("text")
                        start = snippet.get("start")
                        duration = snippet.get("duration")

                        if text_content is None or start is None or duration is None:
                            logger.warning(
                                f"Skipping snippet {seq} in {video_id}/{language_code}: "
                                "missing required field (text/start/duration)"
                            )
                            snippet_errors += 1
                            continue

                        # FR-MIG-18: Type conversion with error handling
                        start_time = float(start)
                        duration_val = float(duration)
                        end_time = start_time + duration_val

                        # Insert segment (has_correction defaults to FALSE per schema)
                        session.execute(
                            text("""
                                INSERT INTO transcript_segments
                                (video_id, language_code, text, start_time,
                                 duration, end_time, sequence_number, has_correction)
                                VALUES (:video_id, :language_code, :text,
                                        :start_time, :duration, :end_time, :seq, FALSE)
                            """),
                            {
                                "video_id": video_id,
                                "language_code": language_code,
                                "text": text_content,
                                "start_time": start_time,
                                "duration": duration_val,
                                "end_time": end_time,
                                "seq": seq,
                            },
                        )
                        segment_count += 1

                    except (TypeError, ValueError) as e:
                        # FR-MIG-19: Skip malformed snippet, continue processing
                        logger.warning(
                            f"Skipping snippet {seq} in {video_id}/{language_code}: "
                            f"type conversion error: {e}"
                        )
                        snippet_errors += 1
                        continue

                # Update segment_count on transcript
                session.execute(
                    text("""
                        UPDATE video_transcripts
                        SET segment_count = :count
                        WHERE video_id = :video_id
                        AND language_code = :language_code
                    """),
                    {
                        "count": segment_count,
                        "video_id": video_id,
                        "language_code": language_code,
                    },
                )

                # FR-MIG-03: Commit after each transcript
                session.commit()
                succeeded += 1

                if snippet_errors > 0:
                    logger.info(
                        f"Processed {video_id}/{language_code}: "
                        f"{segment_count} segments created, "
                        f"{snippet_errors} snippets skipped"
                    )

            except Exception as e:
                # FR-MIG-05: Log failure but continue processing
                logger.error(
                    f"Failed to process {video_id}/{language_code}: {e}",
                    exc_info=True,
                )
                session.rollback()
                failed += 1

        # FR-MIG-06: Report summary
        logger.info(
            f"Backfill migration complete: "
            f"{succeeded} succeeded, {failed} failed, {skipped} skipped "
            f"(out of {total} total transcripts)"
        )

    finally:
        session.close()


def downgrade() -> None:
    """Remove all segments (they can be regenerated from raw_transcript_data).

    WARNING: This deletes all segment data. The data can be recovered by
    running the upgrade migration again.

    This operation:
    1. Deletes all rows from transcript_segments table
    2. Sets segment_count = NULL on all video_transcripts
    3. Reports number of segments deleted
    """
    bind = op.get_bind()
    session = Session(bind=bind)

    try:
        logger.info("Starting transcript segment backfill rollback")

        # Delete all segments
        result = session.execute(text("DELETE FROM transcript_segments"))
        deleted_count = result.rowcount if hasattr(result, 'rowcount') else 0
        logger.info(f"Deleted {deleted_count} segments")

        # Reset segment_count to NULL
        session.execute(
            text("UPDATE video_transcripts SET segment_count = NULL")
        )
        logger.info("Reset segment_count to NULL on all transcripts")

        session.commit()
        logger.info("Rollback complete")

    except Exception as e:
        logger.error(f"Rollback failed: {e}", exc_info=True)
        session.rollback()
        raise

    finally:
        session.close()
