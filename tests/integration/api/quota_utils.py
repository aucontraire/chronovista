"""
Utility functions for handling YouTube API quota errors in integration tests.

This module provides helpers to detect and gracefully handle quota exceeded errors,
allowing tests to skip instead of fail when the daily quota limit is reached.
"""

from __future__ import annotations

import pytest
from googleapiclient.errors import HttpError


def is_quota_exceeded(error: Exception) -> bool:
    """
    Check if an error is a YouTube API quota exceeded error.

    Parameters
    ----------
    error : Exception
        The error to check

    Returns
    -------
    bool
        True if the error is a quota exceeded error, False otherwise

    Examples
    --------
    >>> try:
    ...     youtube_service.get_channel_details(channel_id)
    ... except HttpError as e:
    ...     if is_quota_exceeded(e):
    ...         pytest.skip("API quota exceeded")
    ...     raise
    """
    if isinstance(error, HttpError):
        return error.resp.status == 403 and "quotaExceeded" in str(error)
    return False


def skip_if_quota_exceeded(error: Exception) -> None:
    """
    Skip the current test if the error is a quota exceeded error, otherwise re-raise.

    This is a convenience function that combines quota checking and test skipping.

    Parameters
    ----------
    error : Exception
        The error to check

    Raises
    ------
    Exception
        Re-raises the error if it's not a quota exceeded error

    Examples
    --------
    >>> try:
    ...     youtube_service.get_channel_details(channel_id)
    ... except HttpError as e:
    ...     skip_if_quota_exceeded(e)
    ...     # Will only reach here if it's not a quota error
    ...     raise
    """
    if is_quota_exceeded(error):
        pytest.skip(
            "YouTube API quota exceeded. Quota resets at midnight Pacific Time. "
            "See https://developers.google.com/youtube/v3/getting-started#quota"
        )
