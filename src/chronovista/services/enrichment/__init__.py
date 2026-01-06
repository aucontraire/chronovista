"""
Enrichment services for chronovista.

This package contains services for enriching video and channel metadata
with additional information from the YouTube Data API, including:

- Video metadata enrichment (tags, topics, categories)
- Advisory lock mechanism for concurrent execution prevention
- Video category enrichment
- Channel statistics enrichment
- Thumbnail management
- Content details enrichment
- Topic category seeding
- Video category seeding (multi-region API)

Services in this package are designed to work with the existing repository
layer and handle bulk operations efficiently.
"""

from __future__ import annotations

from chronovista.services.enrichment.enrichment_service import (
    EXIT_CODE_LOCK_FAILED,
    EnrichmentLock,
    EnrichmentService,
    EnrichmentStatus,
    LockAcquisitionError,
    LockInfo,
    PriorityTierEstimate,
)
from chronovista.services.enrichment.seeders import (
    CategorySeeder,
    CategorySeedResult,
    TopicSeeder,
    TopicSeedResult,
)

__all__: list[str] = [
    # Enrichment service and lock
    "EnrichmentLock",
    "EnrichmentService",
    "EnrichmentStatus",
    "EXIT_CODE_LOCK_FAILED",
    "LockAcquisitionError",
    "LockInfo",
    "PriorityTierEstimate",
    # Seeders
    "CategorySeeder",
    "CategorySeedResult",
    "TopicSeeder",
    "TopicSeedResult",
]
