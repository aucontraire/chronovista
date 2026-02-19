"""
Pytest fixtures for recovery service unit tests.

This module provides shared fixtures for testing the Wayback Machine
video recovery functionality, including:
- Factory functions for CdxSnapshot, RecoveredVideoData, RecoveryResult, CdxCacheEntry
- Mock CDX API responses
- Sample archived page HTML
- Mock Selenium WebDriver instances
- Test data builders for recovery models

These factories return dictionaries with realistic defaults that can be unpacked
into model constructors once the models are implemented at
chronovista.services.recovery.models.
"""

from __future__ import annotations

import itertools
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest

# Mark all tests in this module as async by default
pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _clean_test_cache():
    """Clean /tmp/test_cache before each test to prevent cache cross-contamination."""
    cache_dir = Path("/tmp/test_cache")
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
    yield


# Counters for generating unique IDs
_video_id_counter = itertools.count(1)
_snapshot_counter = itertools.count(1)


def make_cdx_snapshot(**overrides: Any) -> dict[str, Any]:
    """
    Create a CdxSnapshot dictionary with realistic defaults.

    A CDX snapshot represents a single Wayback Machine capture point.
    All fields match the CDX API response format after filtering for
    valid HTML pages (mimetype=text/html, statuscode=200, length>5000).

    Parameters
    ----------
    **overrides : Any
        Override any default field values.

    Returns
    -------
    dict[str, Any]
        Dictionary that can be unpacked into CdxSnapshot constructor.

    Examples
    --------
    >>> snapshot = make_cdx_snapshot(timestamp="20220106075526")
    >>> snapshot = make_cdx_snapshot(
    ...     timestamp="20180101120000",
    ...     original="https://www.youtube.com/watch?v=customId123"
    ... )
    """
    # Generate unique 14-digit timestamp (format: YYYYMMDDhhmmss)
    snapshot_num = next(_snapshot_counter)
    # Use incremental timestamps starting from 2020-01-01
    base_timestamp = 20200101000000
    timestamp = str(base_timestamp + snapshot_num * 10000)  # Increment by ~1 hour

    defaults = {
        "timestamp": timestamp,
        "original": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "mimetype": "text/html",
        "statuscode": 200,
        "digest": f"ABCDEFGHIJ{snapshot_num:010d}",  # Realistic hash-like string
        "length": 50000 + snapshot_num * 1000,  # > 5000 threshold
    }

    return {**defaults, **overrides}


def make_recovered_video_data(**overrides: Any) -> dict[str, Any]:
    """
    Create a RecoveredVideoData dictionary with realistic defaults.

    Represents metadata extracted from an archived YouTube page.
    All fields are optional except snapshot_timestamp.

    Parameters
    ----------
    **overrides : Any
        Override any default field values.

    Returns
    -------
    dict[str, Any]
        Dictionary that can be unpacked into RecoveredVideoData constructor.

    Examples
    --------
    >>> data = make_recovered_video_data(title="My Deleted Video")
    >>> data = make_recovered_video_data(
    ...     title="Concert Recording",
    ...     channel_name_hint="MusicChannel",
    ...     view_count=1_000_000
    ... )
    """
    snapshot_num = next(_snapshot_counter)
    timestamp = str(20220101000000 + snapshot_num * 10000)

    defaults = {
        "title": "Recovered Video Title",
        "description": "This is a recovered video description from Wayback Machine.",
        "channel_name_hint": "Recovered Channel",
        "channel_id": f"UC{uuid4().hex[:22]}",  # Valid ChannelId format
        "view_count": 10000,
        "like_count": 500,
        "upload_date": datetime(2021, 6, 15, 12, 0, 0, tzinfo=timezone.utc),
        "thumbnail_url": f"https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
        "tags": ["music", "entertainment", "viral"],
        "category_id": "10",  # Music category
        "snapshot_timestamp": timestamp,
    }

    return {**defaults, **overrides}


def make_recovery_result(
    success: bool = True, **overrides: Any
) -> dict[str, Any]:
    """
    Create a RecoveryResult dictionary with realistic defaults.

    Represents the outcome of a video recovery attempt, including
    success/failure status, fields recovered, and diagnostic information.

    Parameters
    ----------
    success : bool
        Whether the recovery succeeded. Determines which fields are populated.
        Default is True (successful recovery).
    **overrides : Any
        Override any default field values.

    Returns
    -------
    dict[str, Any]
        Dictionary that can be unpacked into RecoveryResult constructor.

    Examples
    --------
    >>> result = make_recovery_result(success=True)
    >>> result = make_recovery_result(
    ...     success=False,
    ...     failure_reason="No snapshots found in CDX API"
    ... )
    >>> result = make_recovery_result(
    ...     success=True,
    ...     fields_recovered=["title", "description", "channel_id"],
    ...     snapshots_tried=3
    ... )
    """
    video_num = next(_video_id_counter)
    video_id = f"{uuid4().hex[:11]}"  # Valid VideoId format (11 chars)

    if success:
        # Successful recovery defaults
        defaults = {
            "video_id": video_id,
            "success": True,
            "snapshot_used": str(20220106075526 + video_num * 10000),
            "fields_recovered": [
                "title",
                "description",
                "channel_id",
                "view_count",
                "upload_date",
            ],
            "fields_skipped": ["like_count", "comment_count"],
            "snapshots_available": 5,
            "snapshots_tried": 2,
            "failure_reason": None,
            "duration_seconds": 2.5,
            "channel_recovery_candidates": [f"UC{uuid4().hex[:22]}"],
        }
    else:
        # Failed recovery defaults
        defaults = {
            "video_id": video_id,
            "success": False,
            "snapshot_used": None,
            "fields_recovered": [],
            "fields_skipped": [],
            "snapshots_available": 3,
            "snapshots_tried": 3,
            "failure_reason": "All snapshots failed to extract metadata",
            "duration_seconds": 5.0,
            "channel_recovery_candidates": [],
        }

    return {**defaults, **overrides}


def make_cdx_cache_entry(**overrides: Any) -> dict[str, Any]:
    """
    Create a CdxCacheEntry dictionary with realistic defaults.

    Represents a cached CDX API response for a specific video ID,
    including the raw snapshot list and fetch timestamp.

    Parameters
    ----------
    **overrides : Any
        Override any default field values.

    Returns
    -------
    dict[str, Any]
        Dictionary that can be unpacked into CdxCacheEntry constructor.

    Examples
    --------
    >>> entry = make_cdx_cache_entry(video_id="dQw4w9WgXcQ")
    >>> entry = make_cdx_cache_entry(
    ...     video_id="customId123",
    ...     snapshots=[make_cdx_snapshot(), make_cdx_snapshot()],
    ...     raw_count=50
    ... )
    """
    video_id = f"{uuid4().hex[:11]}"  # Valid VideoId format

    # Generate 3 sample snapshots by default
    default_snapshots = [
        make_cdx_snapshot(timestamp="20200106075526"),
        make_cdx_snapshot(timestamp="20210315102030"),
        make_cdx_snapshot(timestamp="20220620183045"),
    ]

    defaults = {
        "video_id": video_id,
        "fetched_at": datetime.now(timezone.utc),
        "snapshots": default_snapshots,
        "raw_count": 25,  # Total snapshots before filtering
    }

    return {**defaults, **overrides}


def make_recovered_channel_data(**overrides: Any) -> dict[str, Any]:
    """
    Create a RecoveredChannelData dictionary with realistic defaults.

    Represents metadata extracted from an archived YouTube channel page.
    All fields are optional except snapshot_timestamp.

    Parameters
    ----------
    **overrides : Any
        Override any default field values.

    Returns
    -------
    dict[str, Any]
        Dictionary that can be unpacked into RecoveredChannelData constructor.

    Examples
    --------
    >>> data = make_recovered_channel_data(title="Tech Channel")
    >>> data = make_recovered_channel_data(
    ...     title="Gaming Channel",
    ...     subscriber_count=50000,
    ...     country="GB"
    ... )
    """
    snapshot_num = next(_snapshot_counter)
    timestamp = str(20230101000000 + snapshot_num * 10000)

    defaults = {
        "title": "Recovered Channel Title",
        "description": "This is a recovered channel description from Wayback Machine.",
        "subscriber_count": 100000,
        "video_count": 250,
        "thumbnail_url": "https://yt3.googleusercontent.com/channel/sample/avatar.jpg",
        "country": "US",
        "default_language": "en",
        "snapshot_timestamp": timestamp,
    }

    return {**defaults, **overrides}


def make_channel_recovery_result(
    success: bool = True, **overrides: Any
) -> dict[str, Any]:
    """
    Create a ChannelRecoveryResult dictionary with realistic defaults.

    Represents the outcome of a channel recovery attempt, including
    success/failure status, fields recovered, and diagnostic information.

    Parameters
    ----------
    success : bool
        Whether the recovery succeeded. Determines which fields are populated.
        Default is True (successful recovery).
    **overrides : Any
        Override any default field values.

    Returns
    -------
    dict[str, Any]
        Dictionary that can be unpacked into ChannelRecoveryResult constructor.

    Examples
    --------
    >>> result = make_channel_recovery_result(success=True)
    >>> result = make_channel_recovery_result(
    ...     success=False,
    ...     failure_reason="No snapshots found in CDX API"
    ... )
    >>> result = make_channel_recovery_result(
    ...     success=True,
    ...     fields_recovered=["title", "description", "subscriber_count"],
    ...     snapshots_tried=2
    ... )
    """
    channel_id = f"UC{uuid4().hex[:22]}"  # Valid ChannelId format

    if success:
        # Successful recovery defaults
        defaults = {
            "channel_id": channel_id,
            "success": True,
            "snapshot_used": "20230615120000",
            "fields_recovered": [
                "title",
                "description",
                "subscriber_count",
                "video_count",
            ],
            "fields_skipped": ["country", "default_language"],
            "snapshots_available": 5,
            "snapshots_tried": 1,
            "failure_reason": None,
            "duration_seconds": 2.5,
        }
    else:
        # Failed recovery defaults
        defaults = {
            "channel_id": channel_id,
            "success": False,
            "snapshot_used": None,
            "fields_recovered": [],
            "fields_skipped": [],
            "snapshots_available": 2,
            "snapshots_tried": 2,
            "failure_reason": "All snapshots failed to extract metadata",
            "duration_seconds": 4.0,
        }

    return {**defaults, **overrides}


# ============================================================================
# Pytest Fixtures
# ============================================================================


@pytest.fixture
def cdx_snapshot_factory():
    """
    Fixture that returns the make_cdx_snapshot factory function.

    Returns
    -------
    Callable
        Function that creates CdxSnapshot dictionaries.

    Examples
    --------
    >>> def test_snapshot_creation(cdx_snapshot_factory):
    ...     snapshot = cdx_snapshot_factory(timestamp="20220101120000")
    ...     assert snapshot["mimetype"] == "text/html"
    """
    return make_cdx_snapshot


@pytest.fixture
def recovered_video_data_factory():
    """
    Fixture that returns the make_recovered_video_data factory function.

    Returns
    -------
    Callable
        Function that creates RecoveredVideoData dictionaries.

    Examples
    --------
    >>> def test_recovery_data(recovered_video_data_factory):
    ...     data = recovered_video_data_factory(title="My Video")
    ...     assert data["title"] == "My Video"
    """
    return make_recovered_video_data


@pytest.fixture
def recovery_result_factory():
    """
    Fixture that returns the make_recovery_result factory function.

    Returns
    -------
    Callable
        Function that creates RecoveryResult dictionaries.

    Examples
    --------
    >>> def test_success_result(recovery_result_factory):
    ...     result = recovery_result_factory(success=True)
    ...     assert result["success"] is True
    ...     assert len(result["fields_recovered"]) > 0
    >>>
    >>> def test_failure_result(recovery_result_factory):
    ...     result = recovery_result_factory(success=False)
    ...     assert result["success"] is False
    ...     assert result["failure_reason"] is not None
    """
    return make_recovery_result


@pytest.fixture
def cdx_cache_entry_factory():
    """
    Fixture that returns the make_cdx_cache_entry factory function.

    Returns
    -------
    Callable
        Function that creates CdxCacheEntry dictionaries.

    Examples
    --------
    >>> def test_cache_entry(cdx_cache_entry_factory):
    ...     entry = cdx_cache_entry_factory(video_id="abc123xyz45")
    ...     assert len(entry["snapshots"]) == 3  # Default count
    ...     assert entry["raw_count"] == 25
    """
    return make_cdx_cache_entry


@pytest.fixture
def recovered_channel_data_factory():
    """
    Fixture that returns the make_recovered_channel_data factory function.

    Returns
    -------
    Callable
        Function that creates RecoveredChannelData dictionaries.

    Examples
    --------
    >>> def test_channel_recovery_data(recovered_channel_data_factory):
    ...     data = recovered_channel_data_factory(title="Tech Channel")
    ...     assert data["title"] == "Tech Channel"
    ...     assert data["country"] == "US"
    """
    return make_recovered_channel_data


@pytest.fixture
def channel_recovery_result_factory():
    """
    Fixture that returns the make_channel_recovery_result factory function.

    Returns
    -------
    Callable
        Function that creates ChannelRecoveryResult dictionaries.

    Examples
    --------
    >>> def test_success_result(channel_recovery_result_factory):
    ...     result = channel_recovery_result_factory(success=True)
    ...     assert result["success"] is True
    ...     assert len(result["fields_recovered"]) > 0
    >>>
    >>> def test_failure_result(channel_recovery_result_factory):
    ...     result = channel_recovery_result_factory(success=False)
    ...     assert result["success"] is False
    ...     assert result["failure_reason"] is not None
    """
    return make_channel_recovery_result
