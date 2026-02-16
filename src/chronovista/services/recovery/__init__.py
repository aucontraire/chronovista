"""
Wayback Machine video recovery services.

This package provides functionality to recover metadata for deleted YouTube videos
using the Internet Archive's Wayback Machine CDX API and archived page snapshots.

The recovery process includes:
- CDX API integration with rate limiting
- HTML parsing for video metadata extraction
- Optional Selenium fallback for pre-2017 archived pages
- Result caching and deduplication

Modules
-------
cdx_client
    CDX API client with rate limiting and caching
page_parser
    HTML/JSON parsing for video metadata extraction
recovery_service
    Main recovery orchestration service

Selenium Support
---------------
Selenium WebDriver is an optional dependency used only as a fallback for
pre-2017 archived pages that require JavaScript rendering. If selenium
is not installed, the recovery service will skip JavaScript rendering
and rely on static HTML parsing only.
"""

# Try to import selenium to check availability
try:
    import selenium.webdriver  # type: ignore[import-not-found]  # noqa: F401
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False

from chronovista.services.recovery.cdx_client import CDXClient, RateLimiter
from chronovista.services.recovery.models import (
    CdxCacheEntry,
    CdxSnapshot,
    RecoveredVideoData,
    RecoveryResult,
)
from chronovista.services.recovery.orchestrator import recover_video
from chronovista.services.recovery.page_parser import PageParser

__all__ = [
    "SELENIUM_AVAILABLE",
    "CdxSnapshot",
    "RecoveredVideoData",
    "RecoveryResult",
    "CdxCacheEntry",
    "CDXClient",
    "RateLimiter",
    "PageParser",
    "recover_video",
]
