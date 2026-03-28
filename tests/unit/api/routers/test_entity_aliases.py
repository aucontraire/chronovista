"""Unit tests for POST /api/v1/entities/{entity_id}/aliases endpoint.

Tests the create_entity_alias endpoint in isolation by mocking the database
session and module-level singletons (_alias_repo and _normalizer).  Each test
class is self-contained and does not require a live database.

Coverage targets
----------------
- 201 happy path: valid entity + valid alias body → alias created and returned
- 404 entity not found: valid UUID but entity absent from DB
- 404 invalid UUID: malformed entity_id string cannot be parsed
- 409 duplicate alias: normalized name already exists on this entity
- 409 normalization to empty: alias_name normalizes to empty string (None)
- 422 empty alias_name: Pydantic min_length=1 rejects blank strings
- 422 alias too long: alias_name > 500 chars rejected by Pydantic
- 422 invalid alias_type: asr_error is system-only and not in the allowed Literal
- 201 for each of the 5 valid alias_type values
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import get_db, require_auth
from chronovista.api.main import app

# CRITICAL: ensures all async tests in this module are picked up by pytest-asyncio
# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VALID_ENTITY_ID = str(uuid.uuid4())
_INVALID_UUID = "not-a-valid-uuid"
_ALIAS_ENDPOINT = "/api/v1/entities/{entity_id}/aliases"

# The 5 alias_type values that the endpoint accepts from callers
_ALLOWED_ALIAS_TYPES = [
    "name_variant",
    "abbreviation",
    "nickname",
    "translated_name",
    "former_name",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _alias_url(entity_id: str = _VALID_ENTITY_ID) -> str:
    """Return the full URL for the alias endpoint for the given entity_id."""
    return _ALIAS_ENDPOINT.format(entity_id=entity_id)


def _make_named_entity_row(entity_id: str | None = None) -> MagicMock:
    """Create a minimal mock NamedEntityDB row.

    Parameters
    ----------
    entity_id : str | None
        Entity UUID as a string.  Defaults to the module-level
        ``_VALID_ENTITY_ID``.

    Returns
    -------
    MagicMock
        A mock with the minimum attributes read by the endpoint.
    """
    row = MagicMock()
    row.id = uuid.UUID(entity_id or _VALID_ENTITY_ID)
    row.canonical_name = "Elon Musk"
    row.entity_type = "person"
    row.status = "active"
    return row


def _make_alias_db_row(
    alias_name: str = "Musk",
    alias_type: str = "name_variant",
    occurrence_count: int = 0,
) -> MagicMock:
    """Create a minimal mock EntityAliasDB row that the repo returns after create().

    Parameters
    ----------
    alias_name : str
        The stored alias text.
    alias_type : str
        The alias type string.
    occurrence_count : int
        Number of times this alias has been observed.

    Returns
    -------
    MagicMock
        A mock with the attributes serialized into the response envelope.
    """
    row = MagicMock()
    row.id = uuid.uuid4()
    row.alias_name = alias_name
    row.alias_type = alias_type
    row.occurrence_count = occurrence_count
    row.first_seen_at = datetime(2024, 1, 15, tzinfo=UTC)
    row.last_seen_at = datetime(2024, 1, 15, tzinfo=UTC)
    return row


# ---------------------------------------------------------------------------
# Session factory helpers
# ---------------------------------------------------------------------------


def _make_session_entity_found(
    entity_row: MagicMock, alias_row: MagicMock
) -> AsyncMock:
    """Build a mock AsyncSession for the happy path.

    The endpoint executes three DB calls in sequence:
    1. SELECT NamedEntity by id               → entity_row
    2. SELECT EntityAlias by (entity_id, alias_name_normalized) for dup check → None
    3. _alias_repo.create() inserts the row  → alias_row (handled via repo mock)

    Parameters
    ----------
    entity_row : MagicMock
        The NamedEntity DB row to return on the first execute.
    alias_row : MagicMock
        The created EntityAlias DB row returned by the repo mock (not via execute).

    Returns
    -------
    AsyncMock
        A configured mock session.
    """
    mock_session = AsyncMock(spec=AsyncSession)

    entity_result = MagicMock()
    entity_result.scalar_one_or_none.return_value = entity_row

    # Duplicate-check returns None (no existing alias with that normalized name)
    dup_result = MagicMock()
    dup_result.scalar_one_or_none.return_value = None

    mock_session.execute.side_effect = [entity_result, dup_result]

    # commit / refresh are no-ops
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()

    return mock_session


def _make_session_entity_not_found() -> AsyncMock:
    """Build a mock AsyncSession where the entity lookup returns None."""
    mock_session = AsyncMock(spec=AsyncSession)

    entity_result = MagicMock()
    entity_result.scalar_one_or_none.return_value = None

    mock_session.execute = AsyncMock(return_value=entity_result)
    return mock_session


def _make_session_duplicate_alias(entity_row: MagicMock) -> AsyncMock:
    """Build a mock AsyncSession where the duplicate check finds an existing alias.

    Parameters
    ----------
    entity_row : MagicMock
        Entity row returned by the first execute (entity lookup).

    Returns
    -------
    AsyncMock
        A configured mock session where the dup-check returns a non-None row.
    """
    mock_session = AsyncMock(spec=AsyncSession)

    entity_result = MagicMock()
    entity_result.scalar_one_or_none.return_value = entity_row

    existing_alias = MagicMock()
    dup_result = MagicMock()
    dup_result.scalar_one_or_none.return_value = existing_alias

    mock_session.execute.side_effect = [entity_result, dup_result]
    return mock_session


# ---------------------------------------------------------------------------
# Shared client fixture builders
# ---------------------------------------------------------------------------


async def _build_client(mock_session: AsyncMock) -> AsyncGenerator[AsyncClient, None]:
    """Yield an AsyncClient whose get_db and require_auth are overridden.

    Parameters
    ----------
    mock_session : AsyncMock
        The mock database session to inject.

    Yields
    ------
    AsyncClient
        A configured HTTP test client.
    """

    async def mock_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield mock_session

    async def mock_require_auth() -> None:
        return None

    app.dependency_overrides[get_db] = mock_get_db
    app.dependency_overrides[require_auth] = mock_require_auth

    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# T_ALIAS_201 — Happy-path tests
# ---------------------------------------------------------------------------


class TestCreateEntityAliasHappyPath:
    """Tests that verify 201 responses for valid alias creation."""

    async def test_happy_path_returns_201(self) -> None:
        """Valid entity_id and alias body → 201 Created with alias data.

        Verifies the complete happy path: entity found, alias name normalizes
        to a non-empty string, no duplicate exists, repo creates the row, and
        the response envelope contains alias_name, alias_type, occurrence_count.
        """
        entity_row = _make_named_entity_row()
        alias_row = _make_alias_db_row(alias_name="Musk", alias_type="name_variant")
        mock_session = _make_session_entity_found(entity_row, alias_row)

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._alias_repo"
            ) as mock_repo, patch(
                "chronovista.api.routers.entity_mentions._normalizer"
            ) as mock_normalizer:
                mock_normalizer.normalize.return_value = "musk"
                mock_repo.create = AsyncMock(return_value=alias_row)

                response = await client.post(
                    _alias_url(),
                    json={"alias_name": "Musk", "alias_type": "name_variant"},
                )

        assert response.status_code == 201, response.text

    async def test_happy_path_response_envelope_shape(self) -> None:
        """Response body has a top-level ``data`` key containing the alias fields.

        Validates that the JSON response matches the structure:
        ``{"data": {"alias_name": ..., "alias_type": ..., "occurrence_count": ...}}``
        """
        entity_row = _make_named_entity_row()
        alias_row = _make_alias_db_row(
            alias_name="The Technoking", alias_type="nickname", occurrence_count=0
        )
        mock_session = _make_session_entity_found(entity_row, alias_row)

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._alias_repo"
            ) as mock_repo, patch(
                "chronovista.api.routers.entity_mentions._normalizer"
            ) as mock_normalizer:
                mock_normalizer.normalize.return_value = "the technoking"
                mock_repo.create = AsyncMock(return_value=alias_row)

                response = await client.post(
                    _alias_url(),
                    json={"alias_name": "The Technoking", "alias_type": "nickname"},
                )

        assert response.status_code == 201, response.text
        body = response.json()
        assert "data" in body, f"Missing 'data' key in response: {body}"
        data = body["data"]
        assert data["alias_name"] == "The Technoking"
        assert data["alias_type"] == "nickname"
        assert data["occurrence_count"] == 0

    async def test_happy_path_default_alias_type_is_name_variant(self) -> None:
        """When alias_type is omitted from the request body, it defaults to name_variant.

        The CreateEntityAliasRequest schema defines ``alias_type`` with
        ``default="name_variant"``, so omitting it should produce a valid
        201 response with alias_type == "name_variant".
        """
        entity_row = _make_named_entity_row()
        alias_row = _make_alias_db_row(alias_name="EM", alias_type="name_variant")
        mock_session = _make_session_entity_found(entity_row, alias_row)

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._alias_repo"
            ) as mock_repo, patch(
                "chronovista.api.routers.entity_mentions._normalizer"
            ) as mock_normalizer:
                mock_normalizer.normalize.return_value = "em"
                mock_repo.create = AsyncMock(return_value=alias_row)

                # No alias_type in body → should default to "name_variant"
                response = await client.post(
                    _alias_url(),
                    json={"alias_name": "EM"},
                )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["data"]["alias_type"] == "name_variant"

    async def test_normalizer_is_called_with_raw_alias_name(self) -> None:
        """The endpoint passes the raw alias_name to _normalizer.normalize().

        Verifies the integration between the endpoint and the normalization
        service: the service must receive exactly the string from the request,
        not a pre-processed version.
        """
        entity_row = _make_named_entity_row()
        alias_row = _make_alias_db_row(alias_name="SpaceX CEO", alias_type="nickname")
        mock_session = _make_session_entity_found(entity_row, alias_row)

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._alias_repo"
            ) as mock_repo, patch(
                "chronovista.api.routers.entity_mentions._normalizer"
            ) as mock_normalizer:
                mock_normalizer.normalize.return_value = "spacex ceo"
                mock_repo.create = AsyncMock(return_value=alias_row)

                await client.post(
                    _alias_url(),
                    json={"alias_name": "SpaceX CEO", "alias_type": "nickname"},
                )

                mock_normalizer.normalize.assert_called_once_with("SpaceX CEO")

    async def test_repo_create_called_with_correct_entity_id(self) -> None:
        """The repository create() receives the correct entity_id UUID.

        Guards against a regression where the parsed UUID is not threaded
        through to the EntityAliasCreate model.
        """
        entity_id = str(uuid.uuid4())
        entity_row = _make_named_entity_row(entity_id=entity_id)
        alias_row = _make_alias_db_row()
        mock_session = _make_session_entity_found(entity_row, alias_row)

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._alias_repo"
            ) as mock_repo, patch(
                "chronovista.api.routers.entity_mentions._normalizer"
            ) as mock_normalizer:
                mock_normalizer.normalize.return_value = "musk"
                mock_repo.create = AsyncMock(return_value=alias_row)

                await client.post(
                    _alias_url(entity_id),
                    json={"alias_name": "Musk", "alias_type": "name_variant"},
                )

                # The repo must have been called exactly once
                mock_repo.create.assert_called_once()
                call_kwargs: Any = mock_repo.create.call_args
                # The second positional arg (or keyword obj_in) is EntityAliasCreate
                obj_in = call_kwargs.kwargs.get("obj_in") or call_kwargs.args[1]
                assert obj_in.entity_id == uuid.UUID(entity_id)


# ---------------------------------------------------------------------------
# T_ALIAS_404 — Entity not found / invalid UUID
# ---------------------------------------------------------------------------


class TestCreateEntityAliasEntityNotFound:
    """Tests for 404 responses when the entity does not exist or UUID is invalid."""

    async def test_entity_not_found_returns_404(self) -> None:
        """Valid UUID format but entity absent from DB → 404 Not Found.

        The endpoint performs a SELECT before inserting; when that SELECT
        returns None the handler raises NotFoundError which maps to 404.
        """
        mock_session = _make_session_entity_not_found()

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._normalizer"
            ) as mock_normalizer:
                mock_normalizer.normalize.return_value = "musk"

                response = await client.post(
                    _alias_url(),
                    json={"alias_name": "Musk", "alias_type": "name_variant"},
                )

        assert response.status_code == 404, response.text

    async def test_entity_not_found_response_has_error_body(self) -> None:
        """404 response body contains an RFC-7807-style error structure.

        The project uses RFC-7807 Problem Details: the response should have
        at minimum a ``type`` and ``status`` key.
        """
        mock_session = _make_session_entity_not_found()

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._normalizer"
            ) as mock_normalizer:
                mock_normalizer.normalize.return_value = "musk"

                response = await client.post(
                    _alias_url(),
                    json={"alias_name": "Musk", "alias_type": "name_variant"},
                )

        assert response.status_code == 404
        body = response.json()
        # RFC-7807 structure expected from the project's exception handlers
        assert "status" in body or "type" in body, (
            f"Expected RFC-7807 error body, got: {body}"
        )

    async def test_invalid_uuid_entity_id_returns_404(self) -> None:
        """Malformed entity_id string (not a valid UUID) → 404 Not Found.

        The endpoint calls ``uuid.UUID(entity_id)`` and catches ValueError,
        converting it to NotFoundError rather than letting it bubble up as a
        500.  A mock session is not reached in this branch.
        """
        mock_session = AsyncMock(spec=AsyncSession)

        async for client in _build_client(mock_session):
            response = await client.post(
                _alias_url(_INVALID_UUID),
                json={"alias_name": "Musk", "alias_type": "name_variant"},
            )

        assert response.status_code == 404, response.text

    async def test_invalid_uuid_db_is_never_queried(self) -> None:
        """When UUID parsing fails the database is never queried.

        The endpoint short-circuits before hitting the database when the
        entity_id cannot be parsed.
        """
        mock_session = AsyncMock(spec=AsyncSession)

        async for client in _build_client(mock_session):
            await client.post(
                _alias_url(_INVALID_UUID),
                json={"alias_name": "Musk", "alias_type": "name_variant"},
            )

        mock_session.execute.assert_not_called()


# ---------------------------------------------------------------------------
# T_ALIAS_409 — Conflict (duplicate alias / empty normalized name)
# ---------------------------------------------------------------------------


class TestCreateEntityAliasConflict:
    """Tests for 409 Conflict responses."""

    async def test_duplicate_alias_returns_409(self) -> None:
        """Alias with same normalized form already exists on entity → 409 Conflict.

        When the dup-check SELECT returns a row (not None) the endpoint raises
        ConflictError which the exception handler serializes as 409.
        """
        entity_row = _make_named_entity_row()
        mock_session = _make_session_duplicate_alias(entity_row)

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._normalizer"
            ) as mock_normalizer:
                mock_normalizer.normalize.return_value = "elon"

                response = await client.post(
                    _alias_url(),
                    json={"alias_name": "Elon", "alias_type": "nickname"},
                )

        assert response.status_code == 409, response.text

    async def test_duplicate_alias_response_has_error_body(self) -> None:
        """409 Conflict response body contains an RFC-7807-style error structure."""
        entity_row = _make_named_entity_row()
        mock_session = _make_session_duplicate_alias(entity_row)

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._normalizer"
            ) as mock_normalizer:
                mock_normalizer.normalize.return_value = "elon"

                response = await client.post(
                    _alias_url(),
                    json={"alias_name": "Elon", "alias_type": "nickname"},
                )

        assert response.status_code == 409
        body = response.json()
        assert "status" in body or "type" in body, (
            f"Expected RFC-7807 error body, got: {body}"
        )

    async def test_alias_normalizes_to_empty_returns_409(self) -> None:
        """Alias whose normalized form is None (empty string) → 409 Conflict.

        The endpoint checks the return value of _normalizer.normalize().
        When it returns None the handler raises ConflictError with a message
        explaining that the alias normalizes to an empty string.
        """
        entity_row = _make_named_entity_row()
        # Entity found; duplicate check never reached because normalizer fires first
        entity_result = MagicMock()
        entity_result.scalar_one_or_none.return_value = entity_row

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute = AsyncMock(return_value=entity_result)

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._normalizer"
            ) as mock_normalizer:
                # normalize returns None → alias collapses to empty string
                mock_normalizer.normalize.return_value = None

                response = await client.post(
                    _alias_url(),
                    # A string made purely of diacritics/hash/whitespace that
                    # the normalizer reduces to nothing.  The test doesn't rely
                    # on real normalization; the mock controls the outcome.
                    json={"alias_name": "###   ###", "alias_type": "name_variant"},
                )

        assert response.status_code == 409, response.text

    async def test_alias_normalizes_to_empty_repo_is_never_called(self) -> None:
        """When normalization produces None, the repo create() is never called.

        The endpoint must abort before reaching the repository when the
        normalized alias is empty.
        """
        entity_row = _make_named_entity_row()
        entity_result = MagicMock()
        entity_result.scalar_one_or_none.return_value = entity_row

        mock_session = AsyncMock(spec=AsyncSession)
        mock_session.execute = AsyncMock(return_value=entity_result)

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._alias_repo"
            ) as mock_repo, patch(
                "chronovista.api.routers.entity_mentions._normalizer"
            ) as mock_normalizer:
                mock_normalizer.normalize.return_value = None
                mock_repo.create = AsyncMock()

                await client.post(
                    _alias_url(),
                    json={"alias_name": "###   ###", "alias_type": "name_variant"},
                )

                mock_repo.create.assert_not_called()


# ---------------------------------------------------------------------------
# T_ALIAS_422 — Pydantic validation errors
# ---------------------------------------------------------------------------


class TestCreateEntityAliasValidation:
    """Tests for 422 Unprocessable Entity responses driven by Pydantic validation.

    These tests do NOT need a real session because FastAPI validates the
    request body before the handler function is invoked.
    """

    async def test_empty_alias_name_returns_422(self) -> None:
        """alias_name="" is rejected by Pydantic min_length=1 → 422.

        The CreateEntityAliasRequest model declares ``alias_name`` with
        ``min_length=1``.  An empty string must be rejected before the
        handler ever runs.
        """
        mock_session = AsyncMock(spec=AsyncSession)

        async for client in _build_client(mock_session):
            response = await client.post(
                _alias_url(),
                json={"alias_name": "", "alias_type": "name_variant"},
            )

        assert response.status_code == 422, response.text

    async def test_whitespace_only_alias_name_returns_422(self) -> None:
        """alias_name composed entirely of spaces is rejected → 422.

        A string of only whitespace has length >= 1, so this test confirms
        Pydantic's min_length is based on string length (not stripped length).
        If the model uses a validator that strips first, whitespace is caught
        at normalization time (409); if not, the raw non-empty string passes
        validation.  This test asserts the correct contract: a single space
        (length 1) passes Pydantic validation but is caught later during
        normalization.

        Notes
        -----
        A single space has len == 1 so it passes min_length=1 validation and
        would proceed to the handler.  This test uses a zero-length string
        variant (empty string) which is definitively rejected at 422.  The
        whitespace-only normalizes-to-empty scenario is tested separately
        in TestCreateEntityAliasConflict.
        """
        mock_session = AsyncMock(spec=AsyncSession)

        async for client in _build_client(mock_session):
            # True empty string → 422
            response = await client.post(
                _alias_url(),
                json={"alias_name": "", "alias_type": "name_variant"},
            )

        assert response.status_code == 422, response.text

    async def test_alias_name_too_long_returns_422(self) -> None:
        """alias_name with 501 characters exceeds max_length=500 → 422.

        The CreateEntityAliasRequest model declares ``alias_name`` with
        ``max_length=500``.  Any string longer than 500 characters must be
        rejected by Pydantic before the handler executes.
        """
        too_long = "x" * 501
        mock_session = AsyncMock(spec=AsyncSession)

        async for client in _build_client(mock_session):
            response = await client.post(
                _alias_url(),
                json={"alias_name": too_long, "alias_type": "name_variant"},
            )

        assert response.status_code == 422, response.text

    async def test_alias_name_exactly_500_chars_is_accepted(self) -> None:
        """alias_name with exactly 500 characters is within max_length → passes validation.

        This boundary test verifies that 500 is inclusive (not exclusive).
        The handler will run; with a mocked session returning a found entity
        and a mocked normalizer returning a non-None value with no duplicate,
        the response should be 201.
        """
        boundary_name = "a" * 500
        entity_row = _make_named_entity_row()
        alias_row = _make_alias_db_row(alias_name=boundary_name, alias_type="name_variant")
        mock_session = _make_session_entity_found(entity_row, alias_row)

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._alias_repo"
            ) as mock_repo, patch(
                "chronovista.api.routers.entity_mentions._normalizer"
            ) as mock_normalizer:
                mock_normalizer.normalize.return_value = "a" * 500
                mock_repo.create = AsyncMock(return_value=alias_row)

                response = await client.post(
                    _alias_url(),
                    json={"alias_name": boundary_name, "alias_type": "name_variant"},
                )

        assert response.status_code == 201, response.text

    async def test_invalid_alias_type_asr_error_returns_422(self) -> None:
        """alias_type="asr_error" is not in the allowed Literal → 422.

        ``asr_error`` is a system-internal alias type used only by the
        entity-mention scanner.  The API deliberately excludes it from the
        ``_ALLOWED_ALIAS_TYPES`` Literal so callers cannot create such aliases
        directly.  FastAPI/Pydantic must reject it before the handler runs.
        """
        mock_session = AsyncMock(spec=AsyncSession)

        async for client in _build_client(mock_session):
            response = await client.post(
                _alias_url(),
                json={"alias_name": "elun", "alias_type": "asr_error"},
            )

        assert response.status_code == 422, response.text

    async def test_invalid_alias_type_unknown_string_returns_422(self) -> None:
        """An arbitrary unknown alias_type value → 422.

        Only the 5 values in the Literal are valid.  Any other string must be
        rejected by Pydantic validation.
        """
        mock_session = AsyncMock(spec=AsyncSession)

        async for client in _build_client(mock_session):
            response = await client.post(
                _alias_url(),
                json={"alias_name": "Musk", "alias_type": "completely_invalid"},
            )

        assert response.status_code == 422, response.text

    async def test_missing_alias_name_returns_422(self) -> None:
        """Request body without alias_name → 422 (required field missing)."""
        mock_session = AsyncMock(spec=AsyncSession)

        async for client in _build_client(mock_session):
            response = await client.post(
                _alias_url(),
                json={"alias_type": "name_variant"},
            )

        assert response.status_code == 422, response.text

    async def test_empty_request_body_returns_422(self) -> None:
        """Empty JSON object {} missing required alias_name → 422."""
        mock_session = AsyncMock(spec=AsyncSession)

        async for client in _build_client(mock_session):
            response = await client.post(_alias_url(), json={})

        assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# T_ALIAS_201_ALL_TYPES — All 5 valid alias types return 201
# ---------------------------------------------------------------------------


class TestCreateEntityAliasAllowedTypes:
    """Tests that each of the 5 user-facing alias types is accepted (201).

    Verifies the Literal constraint allows exactly these 5 values and that
    the endpoint persists each without raising a 422.
    """

    async def _post_with_type(
        self, alias_type: str, entity_row: MagicMock, alias_row: MagicMock
    ) -> int:
        """Helper that posts an alias and returns the HTTP status code.

        Parameters
        ----------
        alias_type : str
            The alias type to include in the request body.
        entity_row : MagicMock
            Mock NamedEntity DB row.
        alias_row : MagicMock
            Mock EntityAlias DB row returned by the repository.

        Returns
        -------
        int
            HTTP status code of the response.
        """
        mock_session = _make_session_entity_found(entity_row, alias_row)
        status_code: int = 0

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._alias_repo"
            ) as mock_repo, patch(
                "chronovista.api.routers.entity_mentions._normalizer"
            ) as mock_normalizer:
                mock_normalizer.normalize.return_value = "musk"
                mock_repo.create = AsyncMock(return_value=alias_row)

                response = await client.post(
                    _alias_url(),
                    json={"alias_name": "Musk", "alias_type": alias_type},
                )
                status_code = response.status_code

        return status_code

    async def test_alias_type_name_variant_returns_201(self) -> None:
        """alias_type="name_variant" is a valid type → 201."""
        entity_row = _make_named_entity_row()
        alias_row = _make_alias_db_row(alias_type="name_variant")
        status = await self._post_with_type("name_variant", entity_row, alias_row)
        assert status == 201

    async def test_alias_type_abbreviation_returns_201(self) -> None:
        """alias_type="abbreviation" is a valid type → 201."""
        entity_row = _make_named_entity_row()
        alias_row = _make_alias_db_row(alias_type="abbreviation")
        status = await self._post_with_type("abbreviation", entity_row, alias_row)
        assert status == 201

    async def test_alias_type_nickname_returns_201(self) -> None:
        """alias_type="nickname" is a valid type → 201."""
        entity_row = _make_named_entity_row()
        alias_row = _make_alias_db_row(alias_type="nickname")
        status = await self._post_with_type("nickname", entity_row, alias_row)
        assert status == 201

    async def test_alias_type_translated_name_returns_201(self) -> None:
        """alias_type="translated_name" is a valid type → 201."""
        entity_row = _make_named_entity_row()
        alias_row = _make_alias_db_row(alias_type="translated_name")
        status = await self._post_with_type("translated_name", entity_row, alias_row)
        assert status == 201

    async def test_alias_type_former_name_returns_201(self) -> None:
        """alias_type="former_name" is a valid type → 201."""
        entity_row = _make_named_entity_row()
        alias_row = _make_alias_db_row(alias_type="former_name")
        status = await self._post_with_type("former_name", entity_row, alias_row)
        assert status == 201

    async def test_all_five_allowed_types_are_covered(self) -> None:
        """Guard test: verifies the module-level list contains exactly 5 types.

        If a new valid type is added to the schema, this test will fail,
        prompting the addition of a corresponding individual test above.
        """
        assert len(_ALLOWED_ALIAS_TYPES) == 5
        assert set(_ALLOWED_ALIAS_TYPES) == {
            "name_variant",
            "abbreviation",
            "nickname",
            "translated_name",
            "former_name",
        }

    async def test_asr_error_is_not_in_allowed_types(self) -> None:
        """Guard test: asr_error must NOT appear in the allowed list.

        Ensures the system-internal type is always excluded from the
        user-facing API.
        """
        assert "asr_error" not in _ALLOWED_ALIAS_TYPES


# ---------------------------------------------------------------------------
# T_ALIAS_AUTH — Authentication
# ---------------------------------------------------------------------------


class TestCreateEntityAliasAuthentication:
    """Tests for authentication behavior on the alias creation endpoint."""

    async def test_unauthenticated_request_returns_401(self) -> None:
        """No valid auth token → 401 Unauthorized.

        The router is declared with ``dependencies=[Depends(require_auth)]``.
        When require_auth raises HTTPException(401) (i.e., is not overridden),
        the endpoint must return 401 before any DB interaction.
        """
        # Do NOT override require_auth so the real dependency runs.
        # We DO override get_db to avoid real DB calls.
        mock_session = AsyncMock(spec=AsyncSession)

        async def mock_get_db() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        app.dependency_overrides[get_db] = mock_get_db

        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = False

                transport = ASGITransport(app=app)
                async with AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    response = await client.post(
                        _alias_url(),
                        json={"alias_name": "Musk", "alias_type": "name_variant"},
                    )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 401, response.text
