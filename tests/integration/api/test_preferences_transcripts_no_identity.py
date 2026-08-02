"""API no-identity contract (Feature 060, T034 / FR-020a).

When no canonical identity is established, the preferences/transcripts endpoints
resolve via ``require_local_identity`` and return 409 — and MUST NOT mint an
identity as a side effect of the request.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from chronovista.api.deps import require_local_identity
from chronovista.api.main import app
from chronovista.db.models import AppIdentity as AppIdentityDB

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


async def _app_identity_count(session_factory) -> int:
    async with session_factory() as session:
        return (
            await session.execute(select(func.count()).select_from(AppIdentityDB))
        ).scalar_one()


async def test_preferences_no_identity_returns_409_and_mints_nothing(
    async_client: AsyncClient,
    integration_session_factory,
) -> None:
    # Use the REAL require_local_identity (remove the conftest test override) so
    # the empty app_identities table drives the no-identity path.
    app.dependency_overrides.pop(require_local_identity, None)

    before = await _app_identity_count(integration_session_factory)

    with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
        mock_oauth.is_authenticated.return_value = True
        response = await async_client.get("/api/v1/preferences/languages")

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "IDENTITY_NOT_ESTABLISHED"

    # The read request must not have established an identity (FR-020a).
    after = await _app_identity_count(integration_session_factory)
    assert after == before == 0


async def test_preferences_with_identity_returns_200(
    async_client: AsyncClient,
) -> None:
    # The conftest default override supplies a canonical identity; the endpoint
    # resolves it and reads normally (reader works via the resolver, not a
    # hardcoded default_user — so a re-key never orphans it).
    with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
        mock_oauth.is_authenticated.return_value = True
        response = await async_client.get("/api/v1/preferences/languages")

    assert response.status_code == 200
    assert "data" in response.json()


async def test_transcript_download_no_identity_returns_409_and_mints_nothing(
    async_client: AsyncClient,
    integration_session_factory,
) -> None:
    # The transcript-download endpoint also gates on require_local_identity, so an
    # unestablished identity must 409 before any download/DB work — and never mint.
    app.dependency_overrides.pop(require_local_identity, None)

    before = await _app_identity_count(integration_session_factory)

    with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
        mock_oauth.is_authenticated.return_value = True
        response = await async_client.post(
            "/api/v1/videos/dQw4w9WgXcQ/transcript/download"
        )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "IDENTITY_NOT_ESTABLISHED"

    after = await _app_identity_count(integration_session_factory)
    assert after == before == 0
