"""API services package.

This package contains services used by the API layer for managing
application state, coordination, and business logic specific to
the REST API.
"""

from chronovista.api.services.sync_manager import SyncManager, sync_manager

__all__ = ["SyncManager", "sync_manager"]
