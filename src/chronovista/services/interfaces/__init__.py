"""
Service interfaces (ABCs) for the chronovista application.

These abstract base classes define contracts for service implementations,
enabling dependency injection, testing with mocks, and swappable implementations.
"""

from .takeout_service_interface import TakeoutServiceInterface
from .transcript_service_interface import TranscriptServiceInterface
from .youtube_service_interface import YouTubeServiceInterface

__all__ = [
    "YouTubeServiceInterface",
    "TranscriptServiceInterface",
    "TakeoutServiceInterface",
]
