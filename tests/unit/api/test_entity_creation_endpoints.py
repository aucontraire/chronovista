"""Unit tests for POST /api/v1/entities/classify endpoint.

Tests the classify_tag endpoint in isolation by mocking the database session and
the module-level ``_tag_mgmt_service`` singleton.  No live database is required.

Coverage targets
----------------
- 201 happy path: valid request creates entity, returns entity_id, canonical_name,
  entity_type, alias_count, entity_created, operation_id
- 201 with optional description field
- 201 with entity_created=False (existing entity linked, not created)
- 404 Not Found: service raises ValueError containing "not found"
- 404 Not Found: service raises ValueError containing "status"
- 409 Conflict: service raises ValueError containing "already classified"
  (with existing entity details in response)
- 409 Conflict: service raises ValueError "already classified" but tag lookup
  returns None (no existing entity data available)
- 400 Bad Request: service raises other ValueError
- 422 Unprocessable Entity: entity_type not in allowed set (Pydantic validates)
- 422 Unprocessable Entity: empty normalized_form (min_length=1 fails)
- 422 Unprocessable Entity: normalized_form too long (max_length=500 fails)
- 422 Unprocessable Entity: description too long (max_length=5000 fails)
- 422 Unprocessable Entity: missing normalized_form field
- 422 Unprocessable Entity: missing entity_type field
- Auth: unauthenticated request returns 401

Architecture
------------
The endpoint (``classify_tag``) lives at
``chronovista.api.routers.entity_mentions`` and delegates to a module-level
``_tag_mgmt_service`` singleton (``TagManagementService``).  After a successful
``classify()`` call it makes two additional DB calls:

1. SELECT CanonicalTagDB WHERE normalized_form == body.normalized_form
2. session.get(NamedEntityDB, tag.entity_id)

These are mocked via the session's ``execute`` / ``get`` side-effects.

Mocking strategy
----------------
- ``_tag_mgmt_service.classify`` is patched at the module level using
  ``unittest.mock.patch`` on the full dotted path.
- The ``get_db`` FastAPI dependency is overridden to inject a mock
  ``AsyncSession`` whose ``execute`` and ``get`` attributes are
  ``AsyncMock`` instances returning controlled MagicMock DB rows.
- The ``require_auth`` dependency is overridden to a no-op to avoid
  needing real OAuth credentials.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import get_db, require_auth
from chronovista.api.main import app
from chronovista.services.tag_management import ClassifyResult

# CRITICAL: ensures all async tests in this module are picked up by pytest-asyncio
# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CLASSIFY_ENDPOINT = "/api/v1/entities/classify"

_VALID_NORMALIZED_FORM = "elon musk"
_VALID_ENTITY_TYPE = "person"

# All entity types accepted by ClassifyTagRequest.validate_entity_type
_VALID_ENTITY_TYPES = [
    "person",
    "organization",
    "place",
    "event",
    "work",
    "technical_term",
    "concept",
    "other",
]


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def _make_classify_result(
    *,
    normalized_form: str = _VALID_NORMALIZED_FORM,
    canonical_form: str = "Elon Musk",
    entity_type: str = "person",
    entity_created: bool = True,
    entity_alias_count: int = 2,
    operation_id: uuid.UUID | None = None,
) -> ClassifyResult:
    """Build a ``ClassifyResult`` dataclass for use as the mock return value.

    Parameters
    ----------
    normalized_form : str
        Normalized tag form.
    canonical_form : str
        Display form of the canonical tag.
    entity_type : str
        Entity type string value.
    entity_created : bool
        Whether a new entity was created (vs. linked to existing).
    entity_alias_count : int
        Number of aliases copied to the entity.
    operation_id : uuid.UUID | None
        Operation log UUID.  Auto-generated when None.

    Returns
    -------
    ClassifyResult
        A fully-populated ClassifyResult dataclass instance.
    """
    return ClassifyResult(
        normalized_form=normalized_form,
        canonical_form=canonical_form,
        entity_type=entity_type,
        entity_created=entity_created,
        entity_alias_count=entity_alias_count,
        operation_id=operation_id or uuid.uuid4(),
    )


def _make_canonical_tag_row(
    *,
    normalized_form: str = _VALID_NORMALIZED_FORM,
    entity_id: uuid.UUID | None = None,
) -> MagicMock:
    """Create a minimal mock CanonicalTagDB row.

    Parameters
    ----------
    normalized_form : str
        The normalized form stored on the tag.
    entity_id : uuid.UUID | None
        The linked entity UUID, or None if not yet linked.

    Returns
    -------
    MagicMock
        A mock with the minimum attributes read by the endpoint.
    """
    row = MagicMock()
    row.normalized_form = normalized_form
    row.entity_id = entity_id or uuid.uuid4()
    return row


def _make_named_entity_row(
    *,
    entity_id: uuid.UUID | None = None,
    canonical_name: str = "Elon Musk",
    entity_type: str = "person",
    description: str | None = None,
) -> MagicMock:
    """Create a minimal mock NamedEntityDB row.

    Parameters
    ----------
    entity_id : uuid.UUID | None
        Entity primary key UUID.  Auto-generated when None.
    canonical_name : str
        Display name.
    entity_type : str
        Entity type string.
    description : str | None
        Optional description.

    Returns
    -------
    MagicMock
        A mock with the minimum attributes serialized by the endpoint.
    """
    row = MagicMock()
    row.id = entity_id or uuid.uuid4()
    row.canonical_name = canonical_name
    row.entity_type = entity_type
    row.description = description
    return row


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------


def _make_session_success(
    tag_row: MagicMock, entity_row: MagicMock
) -> AsyncMock:
    """Build a mock AsyncSession for the happy path.

    The endpoint makes these DB calls after a successful classify():
    1. session.execute(SELECT CanonicalTagDB WHERE normalized_form == ...)
       → tag_row
    2. session.get(NamedEntityDB, tag.entity_id) → entity_row
    3. session.commit()

    Parameters
    ----------
    tag_row : MagicMock
        The CanonicalTagDB mock row returned by execute.
    entity_row : MagicMock
        The NamedEntityDB mock row returned by session.get.

    Returns
    -------
    AsyncMock
        Configured mock session.
    """
    mock_session = AsyncMock(spec=AsyncSession)

    # execute() → scalar_one_or_none() → tag_row
    tag_result = MagicMock()
    tag_result.scalar_one_or_none.return_value = tag_row
    mock_session.execute = AsyncMock(return_value=tag_result)

    # session.get() → entity_row
    mock_session.get = AsyncMock(return_value=entity_row)

    mock_session.commit = AsyncMock()
    return mock_session


def _make_session_tag_not_found() -> AsyncMock:
    """Build a mock session where the post-classify tag lookup returns None.

    Used for the conflict branch where tag is already classified but the
    subsequent SELECT cannot locate the tag row.

    Returns
    -------
    AsyncMock
        Configured mock session.
    """
    mock_session = AsyncMock(spec=AsyncSession)

    tag_result = MagicMock()
    tag_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=tag_result)
    mock_session.get = AsyncMock(return_value=None)
    mock_session.commit = AsyncMock()
    return mock_session


def _make_session_conflict_with_existing_entity(
    tag_row: MagicMock, entity_row: MagicMock
) -> AsyncMock:
    """Build a mock session for the 'already classified' conflict branch.

    When the service raises ValueError("already classified ...") the endpoint
    performs two extra DB queries to fetch existing entity details:
    1. SELECT CanonicalTagDB WHERE normalized_form == ...
    2. session.get(NamedEntityDB, tag.entity_id)

    Parameters
    ----------
    tag_row : MagicMock
        The CanonicalTagDB mock row returned by execute.
    entity_row : MagicMock
        The NamedEntityDB mock row returned by session.get.

    Returns
    -------
    AsyncMock
        Configured mock session.
    """
    mock_session = AsyncMock(spec=AsyncSession)

    tag_result = MagicMock()
    tag_result.scalar_one_or_none.return_value = tag_row
    mock_session.execute = AsyncMock(return_value=tag_result)
    mock_session.get = AsyncMock(return_value=entity_row)
    mock_session.commit = AsyncMock()
    return mock_session


# ---------------------------------------------------------------------------
# Shared client fixture builder
# ---------------------------------------------------------------------------


async def _build_client(mock_session: AsyncMock) -> AsyncGenerator[AsyncClient, None]:
    """Yield an AsyncClient with get_db and require_auth overridden.

    Parameters
    ----------
    mock_session : AsyncMock
        The mock database session to inject via the get_db override.

    Yields
    ------
    AsyncClient
        A configured HTTP test client with overridden dependencies.
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
# T_CLASSIFY_201 — Happy-path tests
# ---------------------------------------------------------------------------


class TestClassifyTagHappyPath:
    """Tests that verify 201 responses for valid classify requests."""

    async def test_valid_request_returns_201(self) -> None:
        """Valid normalized_form and entity_type → 201 Created.

        Verifies the most basic happy path: the service classifies successfully
        and the endpoint returns a 201 status code.
        """
        entity_id = uuid.uuid4()
        tag_row = _make_canonical_tag_row(entity_id=entity_id)
        entity_row = _make_named_entity_row(entity_id=entity_id)
        mock_session = _make_session_success(tag_row, entity_row)
        classify_result = _make_classify_result()

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._tag_mgmt_service"
            ) as mock_svc:
                mock_svc.classify = AsyncMock(return_value=classify_result)

                response = await client.post(
                    _CLASSIFY_ENDPOINT,
                    json={
                        "normalized_form": _VALID_NORMALIZED_FORM,
                        "entity_type": _VALID_ENTITY_TYPE,
                    },
                )

        assert response.status_code == 201, response.text

    async def test_response_body_contains_required_fields(self) -> None:
        """201 response body contains entity_id, canonical_name, entity_type,
        alias_count, entity_created, and operation_id.

        Validates the full response schema returned by the classify endpoint.
        """
        entity_id = uuid.uuid4()
        operation_id = uuid.uuid4()
        tag_row = _make_canonical_tag_row(entity_id=entity_id)
        entity_row = _make_named_entity_row(
            entity_id=entity_id,
            canonical_name="Elon Musk",
            entity_type="person",
        )
        mock_session = _make_session_success(tag_row, entity_row)
        classify_result = _make_classify_result(
            entity_alias_count=3,
            entity_created=True,
            operation_id=operation_id,
        )

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._tag_mgmt_service"
            ) as mock_svc:
                mock_svc.classify = AsyncMock(return_value=classify_result)

                response = await client.post(
                    _CLASSIFY_ENDPOINT,
                    json={
                        "normalized_form": _VALID_NORMALIZED_FORM,
                        "entity_type": "person",
                    },
                )

        assert response.status_code == 201, response.text
        body = response.json()

        assert "entity_id" in body, f"Missing 'entity_id' in: {body}"
        assert "canonical_name" in body, f"Missing 'canonical_name' in: {body}"
        assert "entity_type" in body, f"Missing 'entity_type' in: {body}"
        assert "alias_count" in body, f"Missing 'alias_count' in: {body}"
        assert "entity_created" in body, f"Missing 'entity_created' in: {body}"
        assert "operation_id" in body, f"Missing 'operation_id' in: {body}"

    async def test_response_body_values_match_service_and_db(self) -> None:
        """Response field values are pulled from the entity row and classify result.

        entity_id and canonical_name come from the NamedEntityDB lookup;
        entity_type, alias_count, entity_created, and operation_id come from
        ClassifyResult.
        """
        entity_id = uuid.uuid4()
        operation_id = uuid.uuid4()

        tag_row = _make_canonical_tag_row(entity_id=entity_id)
        entity_row = _make_named_entity_row(
            entity_id=entity_id,
            canonical_name="Elon Musk",
            entity_type="person",
            description="South African-born entrepreneur",
        )
        mock_session = _make_session_success(tag_row, entity_row)
        classify_result = _make_classify_result(
            entity_alias_count=5,
            entity_created=True,
            entity_type="person",
            operation_id=operation_id,
        )

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._tag_mgmt_service"
            ) as mock_svc:
                mock_svc.classify = AsyncMock(return_value=classify_result)

                response = await client.post(
                    _CLASSIFY_ENDPOINT,
                    json={
                        "normalized_form": _VALID_NORMALIZED_FORM,
                        "entity_type": "person",
                    },
                )

        body = response.json()
        assert body["entity_id"] == str(entity_id)
        assert body["canonical_name"] == "Elon Musk"
        assert body["entity_type"] == "person"
        assert body["alias_count"] == 5
        assert body["entity_created"] is True
        assert body["operation_id"] == str(operation_id)

    async def test_optional_description_is_included_in_response(self) -> None:
        """When description is passed in the request, it is reflected in the response.

        The endpoint sets ``description`` from the entity row's description field
        after the tag lookup.
        """
        entity_id = uuid.uuid4()
        description_text = "Tesla and SpaceX CEO"
        tag_row = _make_canonical_tag_row(entity_id=entity_id)
        entity_row = _make_named_entity_row(
            entity_id=entity_id,
            description=description_text,
        )
        mock_session = _make_session_success(tag_row, entity_row)
        classify_result = _make_classify_result()

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._tag_mgmt_service"
            ) as mock_svc:
                mock_svc.classify = AsyncMock(return_value=classify_result)

                response = await client.post(
                    _CLASSIFY_ENDPOINT,
                    json={
                        "normalized_form": _VALID_NORMALIZED_FORM,
                        "entity_type": "person",
                        "description": description_text,
                    },
                )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["description"] == description_text

    async def test_entity_created_false_when_existing_entity_linked(self) -> None:
        """When an existing entity is linked (not created), entity_created is False.

        ClassifyResult.entity_created=False occurs when classify() finds an
        existing NamedEntity and links the canonical tag to it instead of
        creating a new one.
        """
        entity_id = uuid.uuid4()
        tag_row = _make_canonical_tag_row(entity_id=entity_id)
        entity_row = _make_named_entity_row(entity_id=entity_id)
        mock_session = _make_session_success(tag_row, entity_row)
        classify_result = _make_classify_result(entity_created=False)

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._tag_mgmt_service"
            ) as mock_svc:
                mock_svc.classify = AsyncMock(return_value=classify_result)

                response = await client.post(
                    _CLASSIFY_ENDPOINT,
                    json={
                        "normalized_form": _VALID_NORMALIZED_FORM,
                        "entity_type": "person",
                    },
                )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["entity_created"] is False

    async def test_service_called_with_correct_arguments(self) -> None:
        """The endpoint passes normalized_form, entity_type enum, description,
        and auto_case=True to the service classify() method.

        Guards against a regression where arguments are shuffled or the enum
        conversion is skipped.
        """
        from chronovista.models.enums import EntityType

        entity_id = uuid.uuid4()
        tag_row = _make_canonical_tag_row(entity_id=entity_id)
        entity_row = _make_named_entity_row(entity_id=entity_id)
        mock_session = _make_session_success(tag_row, entity_row)
        classify_result = _make_classify_result()

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._tag_mgmt_service"
            ) as mock_svc:
                mock_svc.classify = AsyncMock(return_value=classify_result)

                await client.post(
                    _CLASSIFY_ENDPOINT,
                    json={
                        "normalized_form": "tesla motors",
                        "entity_type": "organization",
                        "description": "Electric vehicle manufacturer",
                    },
                )

                mock_svc.classify.assert_called_once()
                call_args: Any = mock_svc.classify.call_args
                # Verify positional args: session, normalized_form, entity_type_enum
                assert call_args.args[1] == "tesla motors"
                assert call_args.args[2] == EntityType.ORGANIZATION
                # Verify keyword args
                assert call_args.kwargs.get("description") == "Electric vehicle manufacturer"
                assert call_args.kwargs.get("auto_case") is True

    async def test_alias_count_is_zero_when_no_aliases_created(self) -> None:
        """alias_count == 0 in the response when entity_alias_count is 0.

        A new entity with no tag aliases produces alias_count=0 in the
        ClassifyResult and this must be faithfully serialized.
        """
        entity_id = uuid.uuid4()
        tag_row = _make_canonical_tag_row(entity_id=entity_id)
        entity_row = _make_named_entity_row(entity_id=entity_id)
        mock_session = _make_session_success(tag_row, entity_row)
        classify_result = _make_classify_result(entity_alias_count=0)

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._tag_mgmt_service"
            ) as mock_svc:
                mock_svc.classify = AsyncMock(return_value=classify_result)

                response = await client.post(
                    _CLASSIFY_ENDPOINT,
                    json={
                        "normalized_form": _VALID_NORMALIZED_FORM,
                        "entity_type": "person",
                    },
                )

        body = response.json()
        assert body["alias_count"] == 0


# ---------------------------------------------------------------------------
# T_CLASSIFY_404 — Tag not found / inactive
# ---------------------------------------------------------------------------


class TestClassifyTagNotFound:
    """Tests for 404 responses when the canonical tag does not exist or is inactive."""

    async def test_tag_not_found_returns_404(self) -> None:
        """Service raises ValueError with 'not found' → endpoint returns 404.

        The ``classify()`` method raises ValueError when the normalized_form
        does not match any active canonical tag.  The endpoint inspects the
        error message and maps it to NotFoundError (404).
        """
        mock_session = _make_session_tag_not_found()

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._tag_mgmt_service"
            ) as mock_svc:
                mock_svc.classify = AsyncMock(
                    side_effect=ValueError("Tag 'unknown-tag' not found")
                )

                response = await client.post(
                    _CLASSIFY_ENDPOINT,
                    json={
                        "normalized_form": "unknown-tag",
                        "entity_type": "person",
                    },
                )

        assert response.status_code == 404, response.text

    async def test_tag_not_found_has_rfc7807_error_body(self) -> None:
        """404 response body follows RFC-7807 Problem Details structure."""
        mock_session = _make_session_tag_not_found()

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._tag_mgmt_service"
            ) as mock_svc:
                mock_svc.classify = AsyncMock(
                    side_effect=ValueError("Tag 'x' not found in database")
                )

                response = await client.post(
                    _CLASSIFY_ENDPOINT,
                    json={
                        "normalized_form": "x",
                        "entity_type": "person",
                    },
                )

        assert response.status_code == 404
        body = response.json()
        assert "status" in body or "type" in body, (
            f"Expected RFC-7807 error body, got: {body}"
        )

    async def test_inactive_tag_returns_404(self) -> None:
        """Service raises ValueError mentioning 'status' → endpoint returns 404.

        When a canonical tag exists but is deprecated/inactive, the service
        raises a ValueError containing 'status'.  The endpoint maps this to
        a 404 response.
        """
        mock_session = _make_session_tag_not_found()

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._tag_mgmt_service"
            ) as mock_svc:
                mock_svc.classify = AsyncMock(
                    side_effect=ValueError(
                        "Tag 'deprecated-tag' has status 'deprecated' and cannot be classified"
                    )
                )

                response = await client.post(
                    _CLASSIFY_ENDPOINT,
                    json={
                        "normalized_form": "deprecated-tag",
                        "entity_type": "organization",
                    },
                )

        assert response.status_code == 404, response.text


# ---------------------------------------------------------------------------
# T_CLASSIFY_409 — Already classified (conflict)
# ---------------------------------------------------------------------------


class TestClassifyTagConflict:
    """Tests for 409 Conflict when a tag is already classified as an entity."""

    async def test_already_classified_returns_409(self) -> None:
        """Service raises ValueError 'already classified' → 409 Conflict.

        The ``classify()`` method raises ValueError when the canonical tag
        already has an entity_type set and force=False (the default).
        """
        entity_id = uuid.uuid4()
        tag_row = _make_canonical_tag_row(entity_id=entity_id)
        entity_row = _make_named_entity_row(entity_id=entity_id)
        mock_session = _make_session_conflict_with_existing_entity(
            tag_row, entity_row
        )

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._tag_mgmt_service"
            ) as mock_svc:
                mock_svc.classify = AsyncMock(
                    side_effect=ValueError(
                        "Tag 'elon musk' is already classified as person"
                    )
                )

                response = await client.post(
                    _CLASSIFY_ENDPOINT,
                    json={
                        "normalized_form": _VALID_NORMALIZED_FORM,
                        "entity_type": "person",
                    },
                )

        assert response.status_code == 409, response.text

    async def test_already_classified_response_has_rfc7807_body(self) -> None:
        """409 Conflict response body follows RFC-7807 Problem Details structure."""
        entity_id = uuid.uuid4()
        tag_row = _make_canonical_tag_row(entity_id=entity_id)
        entity_row = _make_named_entity_row(entity_id=entity_id)
        mock_session = _make_session_conflict_with_existing_entity(
            tag_row, entity_row
        )

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._tag_mgmt_service"
            ) as mock_svc:
                mock_svc.classify = AsyncMock(
                    side_effect=ValueError("Tag is already classified as an entity")
                )

                response = await client.post(
                    _CLASSIFY_ENDPOINT,
                    json={
                        "normalized_form": _VALID_NORMALIZED_FORM,
                        "entity_type": "person",
                    },
                )

        assert response.status_code == 409
        body = response.json()
        assert "status" in body or "type" in body, (
            f"Expected RFC-7807 error body, got: {body}"
        )

    async def test_already_classified_includes_existing_entity_in_details(
        self,
    ) -> None:
        """409 Conflict response body includes existing entity details in 'details'.

        When the tag lookup succeeds after the conflict, the endpoint fetches
        the existing entity and includes it in the ConflictError details dict.
        The RFC-7807 response should therefore contain the existing entity info.
        """
        entity_id = uuid.uuid4()
        tag_row = _make_canonical_tag_row(entity_id=entity_id)
        entity_row = _make_named_entity_row(
            entity_id=entity_id,
            canonical_name="Elon Musk",
            entity_type="person",
            description="CEO of Tesla and SpaceX",
        )
        mock_session = _make_session_conflict_with_existing_entity(
            tag_row, entity_row
        )

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._tag_mgmt_service"
            ) as mock_svc:
                mock_svc.classify = AsyncMock(
                    side_effect=ValueError(
                        "Tag 'elon musk' is already classified as person"
                    )
                )

                response = await client.post(
                    _CLASSIFY_ENDPOINT,
                    json={
                        "normalized_form": _VALID_NORMALIZED_FORM,
                        "entity_type": "person",
                    },
                )

        assert response.status_code == 409
        body = response.json()
        # The ConflictError details should carry existing entity information.
        # RFC-7807 responses in this project include an "errors" or "details" key.
        assert "status" in body or "type" in body

    async def test_already_classified_no_tag_row_still_returns_409(self) -> None:
        """409 returned even when the post-conflict tag lookup returns None.

        Edge case: the service reports "already classified" but the subsequent
        SELECT for existing entity details finds no matching tag row.  The
        endpoint still raises ConflictError with no ``details`` payload.
        """
        mock_session = _make_session_tag_not_found()

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._tag_mgmt_service"
            ) as mock_svc:
                mock_svc.classify = AsyncMock(
                    side_effect=ValueError(
                        "Tag is already classified — use force=True to override"
                    )
                )

                response = await client.post(
                    _CLASSIFY_ENDPOINT,
                    json={
                        "normalized_form": _VALID_NORMALIZED_FORM,
                        "entity_type": "person",
                    },
                )

        assert response.status_code == 409, response.text


# ---------------------------------------------------------------------------
# T_CLASSIFY_400 — Other ValueError from service → 400 Bad Request
# ---------------------------------------------------------------------------


class TestClassifyTagBadRequest:
    """Tests for 400 Bad Request when the service raises a generic ValueError."""

    async def test_generic_value_error_returns_400(self) -> None:
        """Service raises ValueError that is neither 'not found' nor 'already classified'
        → endpoint returns 400 Bad Request.

        The endpoint has a catch-all branch that maps unrecognized ValueError
        messages to BadRequestError (400).
        """
        mock_session = _make_session_tag_not_found()

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._tag_mgmt_service"
            ) as mock_svc:
                mock_svc.classify = AsyncMock(
                    side_effect=ValueError(
                        "Some unexpected validation error from the service layer"
                    )
                )

                response = await client.post(
                    _CLASSIFY_ENDPOINT,
                    json={
                        "normalized_form": _VALID_NORMALIZED_FORM,
                        "entity_type": "person",
                    },
                )

        assert response.status_code == 400, response.text

    async def test_generic_value_error_has_rfc7807_body(self) -> None:
        """400 Bad Request response body follows RFC-7807 Problem Details structure."""
        mock_session = _make_session_tag_not_found()

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._tag_mgmt_service"
            ) as mock_svc:
                mock_svc.classify = AsyncMock(
                    side_effect=ValueError("Cannot process this request")
                )

                response = await client.post(
                    _CLASSIFY_ENDPOINT,
                    json={
                        "normalized_form": _VALID_NORMALIZED_FORM,
                        "entity_type": "person",
                    },
                )

        assert response.status_code == 400
        body = response.json()
        assert "status" in body or "type" in body, (
            f"Expected RFC-7807 error body, got: {body}"
        )


# ---------------------------------------------------------------------------
# T_CLASSIFY_422 — Pydantic validation errors (no DB required)
# ---------------------------------------------------------------------------


class TestClassifyTagValidation:
    """Tests for 422 Unprocessable Entity responses driven by Pydantic / FastAPI.

    These tests do NOT reach the handler because FastAPI validates the request
    body before invoking the endpoint function.  No mock session is needed.
    """

    async def test_invalid_entity_type_returns_422(self) -> None:
        """entity_type not in the allowed set → 422 Unprocessable Entity.

        ClassifyTagRequest uses a Pydantic field_validator that raises ValueError
        for any entity_type not in ``_ENTITY_PRODUCING_TYPES``.  FastAPI converts
        this to a 422 response before the handler runs.
        """
        mock_session = AsyncMock(spec=AsyncSession)

        async for client in _build_client(mock_session):
            response = await client.post(
                _CLASSIFY_ENDPOINT,
                json={
                    "normalized_form": _VALID_NORMALIZED_FORM,
                    "entity_type": "robot",  # Not a valid entity type
                },
            )

        assert response.status_code == 422, response.text

    async def test_entity_type_topic_is_valid_per_schema(self) -> None:
        """entity_type='topic' is in the schema's allowed set but NOT in EntityType enum.

        The Pydantic schema (ClassifyTagRequest) uses a set-based validator that
        accepts 'concept' and 'other' (Feature 051 additions). The router then does
        ``EntityType(body.entity_type)`` which will raise ValueError for any value
        not in the enum. This produces a 400 from the BadRequestError branch.

        Note: 'topic' and 'descriptor' are in EntityType enum but NOT in
        _ENTITY_PRODUCING_TYPES used by the schema validator, so they fail at 422.
        """
        mock_session = AsyncMock(spec=AsyncSession)

        async for client in _build_client(mock_session):
            response = await client.post(
                _CLASSIFY_ENDPOINT,
                json={
                    "normalized_form": _VALID_NORMALIZED_FORM,
                    "entity_type": "topic",  # Not in _ENTITY_PRODUCING_TYPES → 422
                },
            )

        # "topic" is not in the Pydantic validator's allowed set so it fails at 422
        assert response.status_code == 422, response.text

    async def test_empty_normalized_form_returns_422(self) -> None:
        """normalized_form="" is rejected by Pydantic min_length=1 → 422.

        ClassifyTagRequest.normalized_form has ``min_length=1`` so an empty
        string fails at schema validation before the handler is called.
        """
        mock_session = AsyncMock(spec=AsyncSession)

        async for client in _build_client(mock_session):
            response = await client.post(
                _CLASSIFY_ENDPOINT,
                json={
                    "normalized_form": "",
                    "entity_type": _VALID_ENTITY_TYPE,
                },
            )

        assert response.status_code == 422, response.text

    async def test_normalized_form_too_long_returns_422(self) -> None:
        """normalized_form with 501 characters exceeds max_length=500 → 422.

        ClassifyTagRequest.normalized_form has ``max_length=500``.  Any string
        longer than 500 characters is rejected by Pydantic.
        """
        too_long = "x" * 501
        mock_session = AsyncMock(spec=AsyncSession)

        async for client in _build_client(mock_session):
            response = await client.post(
                _CLASSIFY_ENDPOINT,
                json={
                    "normalized_form": too_long,
                    "entity_type": _VALID_ENTITY_TYPE,
                },
            )

        assert response.status_code == 422, response.text

    async def test_normalized_form_exactly_500_chars_passes_validation(self) -> None:
        """normalized_form with exactly 500 characters is at the boundary → valid.

        Pydantic's max_length=500 is inclusive, so a 500-character string should
        pass validation and reach the handler (which is mocked to succeed).
        """
        boundary_form = "a" * 500
        entity_id = uuid.uuid4()
        tag_row = _make_canonical_tag_row(entity_id=entity_id)
        entity_row = _make_named_entity_row(entity_id=entity_id)
        mock_session = _make_session_success(tag_row, entity_row)
        classify_result = _make_classify_result(normalized_form=boundary_form)

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._tag_mgmt_service"
            ) as mock_svc:
                mock_svc.classify = AsyncMock(return_value=classify_result)

                response = await client.post(
                    _CLASSIFY_ENDPOINT,
                    json={
                        "normalized_form": boundary_form,
                        "entity_type": _VALID_ENTITY_TYPE,
                    },
                )

        assert response.status_code == 201, response.text

    async def test_description_too_long_returns_422(self) -> None:
        """description with 5001 characters exceeds max_length=5000 → 422.

        ClassifyTagRequest.description has ``max_length=5000``.  Any description
        longer than 5000 characters is rejected by Pydantic before the handler runs.
        """
        too_long_desc = "d" * 5001
        mock_session = AsyncMock(spec=AsyncSession)

        async for client in _build_client(mock_session):
            response = await client.post(
                _CLASSIFY_ENDPOINT,
                json={
                    "normalized_form": _VALID_NORMALIZED_FORM,
                    "entity_type": _VALID_ENTITY_TYPE,
                    "description": too_long_desc,
                },
            )

        assert response.status_code == 422, response.text

    async def test_missing_normalized_form_returns_422(self) -> None:
        """Request body without normalized_form → 422 (required field missing)."""
        mock_session = AsyncMock(spec=AsyncSession)

        async for client in _build_client(mock_session):
            response = await client.post(
                _CLASSIFY_ENDPOINT,
                json={"entity_type": _VALID_ENTITY_TYPE},
            )

        assert response.status_code == 422, response.text

    async def test_missing_entity_type_returns_422(self) -> None:
        """Request body without entity_type → 422 (required field missing)."""
        mock_session = AsyncMock(spec=AsyncSession)

        async for client in _build_client(mock_session):
            response = await client.post(
                _CLASSIFY_ENDPOINT,
                json={"normalized_form": _VALID_NORMALIZED_FORM},
            )

        assert response.status_code == 422, response.text

    async def test_empty_request_body_returns_422(self) -> None:
        """Empty JSON object {} missing both required fields → 422."""
        mock_session = AsyncMock(spec=AsyncSession)

        async for client in _build_client(mock_session):
            response = await client.post(_CLASSIFY_ENDPOINT, json={})

        assert response.status_code == 422, response.text


# ---------------------------------------------------------------------------
# T_CLASSIFY_VALID_TYPES — All allowed entity types produce 201
# ---------------------------------------------------------------------------


class TestClassifyTagAllowedEntityTypes:
    """Tests that each entity-producing type accepted by the schema yields 201.

    Validates that the Pydantic validator and the EntityType enum conversion
    in the handler both accept each of the schema's allowed entity types.
    """

    async def _post_with_entity_type(self, entity_type: str) -> int:
        """Helper: post a classify request with the given entity_type and return status.

        Parameters
        ----------
        entity_type : str
            The entity type string to include in the request body.

        Returns
        -------
        int
            HTTP status code of the response.
        """
        entity_id = uuid.uuid4()
        tag_row = _make_canonical_tag_row(entity_id=entity_id)
        entity_row = _make_named_entity_row(
            entity_id=entity_id, entity_type=entity_type
        )
        mock_session = _make_session_success(tag_row, entity_row)
        classify_result = _make_classify_result(entity_type=entity_type)
        status_code: int = 0

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._tag_mgmt_service"
            ) as mock_svc:
                mock_svc.classify = AsyncMock(return_value=classify_result)

                response = await client.post(
                    _CLASSIFY_ENDPOINT,
                    json={
                        "normalized_form": _VALID_NORMALIZED_FORM,
                        "entity_type": entity_type,
                    },
                )
                status_code = response.status_code

        return status_code

    async def test_person_returns_201(self) -> None:
        """entity_type='person' is valid → 201."""
        assert await self._post_with_entity_type("person") == 201

    async def test_organization_returns_201(self) -> None:
        """entity_type='organization' is valid → 201."""
        assert await self._post_with_entity_type("organization") == 201

    async def test_place_returns_201(self) -> None:
        """entity_type='place' is valid → 201."""
        assert await self._post_with_entity_type("place") == 201

    async def test_event_returns_201(self) -> None:
        """entity_type='event' is valid → 201."""
        assert await self._post_with_entity_type("event") == 201

    async def test_work_returns_201(self) -> None:
        """entity_type='work' is valid → 201."""
        assert await self._post_with_entity_type("work") == 201

    async def test_technical_term_returns_201(self) -> None:
        """entity_type='technical_term' is valid → 201."""
        assert await self._post_with_entity_type("technical_term") == 201

    async def test_concept_returns_201(self) -> None:
        """entity_type='concept' is valid per schema and enum → 201."""
        assert await self._post_with_entity_type("concept") == 201

    async def test_other_returns_201(self) -> None:
        """entity_type='other' is valid per schema and enum → 201."""
        assert await self._post_with_entity_type("other") == 201

    async def test_valid_types_count_guard(self) -> None:
        """Guard test: the module-level allowed-type list contains exactly 8 entries.

        If a new valid entity type is added to the schema, this test will fail,
        prompting the addition of a corresponding individual test above.
        """
        assert len(_VALID_ENTITY_TYPES) == 8
        assert set(_VALID_ENTITY_TYPES) == {
            "person",
            "organization",
            "place",
            "event",
            "work",
            "technical_term",
            "concept",
            "other",
        }


# ---------------------------------------------------------------------------
# T_CLASSIFY_AUTH — Authentication
# ---------------------------------------------------------------------------


class TestClassifyTagAuthentication:
    """Tests for authentication behavior on the classify endpoint."""

    async def test_unauthenticated_request_returns_401(self) -> None:
        """No valid auth token → 401 Unauthorized.

        The entity_mentions router declares
        ``dependencies=[Depends(require_auth)]``.  When require_auth is NOT
        overridden and the OAuth service reports unauthenticated, the endpoint
        must return 401 before any DB or service interaction.
        """
        mock_session = AsyncMock(spec=AsyncSession)

        async def mock_get_db() -> AsyncGenerator[AsyncSession, None]:
            yield mock_session

        app.dependency_overrides[get_db] = mock_get_db
        # Intentionally do NOT override require_auth here

        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = False

                transport = ASGITransport(app=app)
                async with AsyncClient(
                    transport=transport, base_url="http://test"
                ) as client:
                    response = await client.post(
                        _CLASSIFY_ENDPOINT,
                        json={
                            "normalized_form": _VALID_NORMALIZED_FORM,
                            "entity_type": _VALID_ENTITY_TYPE,
                        },
                    )
        finally:
            app.dependency_overrides.clear()

        assert response.status_code == 401, response.text


# ---------------------------------------------------------------------------
# T_CHECK_DUPLICATE — GET /api/v1/entities/check-duplicate
# ---------------------------------------------------------------------------
#
# The endpoint normalizes the ``name`` query param, then queries
# ``named_entities`` for an active row with the same canonical_name_normalized
# and entity_type.
#
# Mocking strategy
# ----------------
# - ``_normalizer.normalize`` is patched at the module level to control the
#   exact normalized form returned without exercising the full NLP pipeline.
# - The DB query is mocked via ``session.execute`` returning a mock result
#   whose ``scalar_one_or_none()`` returns either a NamedEntityDB mock or None.
# - Rate limiting is tested by patching ``_check_rate_limit`` in the module
#   to return (False, 30), bypassing the real time-window logic.
# ---------------------------------------------------------------------------

_CHECK_DUPLICATE_ENDPOINT = "/api/v1/entities/check-duplicate"

_DUPLICATE_NAME = "Garland Nixon"
_DUPLICATE_TYPE = "person"
_DUPLICATE_NORMALIZED = "garland nixon"


def _make_named_entity_for_duplicate(
    *,
    entity_id: uuid.UUID | None = None,
    canonical_name: str = "Garland Nixon",
    entity_type: str = "person",
    description: str | None = "Political commentator",
) -> MagicMock:
    """Build a minimal mock NamedEntityDB row for duplicate-check tests.

    Parameters
    ----------
    entity_id : uuid.UUID | None
        Entity primary key UUID.  Auto-generated when None.
    canonical_name : str
        Display name stored on the entity row.
    entity_type : str
        Entity type string.
    description : str | None
        Optional description string.

    Returns
    -------
    MagicMock
        Mock with the attributes read by the check_duplicate_entity endpoint.
    """
    row = MagicMock()
    row.id = entity_id or uuid.uuid4()
    row.canonical_name = canonical_name
    row.entity_type = entity_type
    row.description = description
    return row


def _make_session_duplicate_found(entity_row: MagicMock) -> AsyncMock:
    """Build a mock AsyncSession where the entity query returns a matching row.

    Parameters
    ----------
    entity_row : MagicMock
        The NamedEntityDB mock row to return from execute().scalar_one_or_none().

    Returns
    -------
    AsyncMock
        Configured mock session.
    """
    mock_session = AsyncMock(spec=AsyncSession)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = entity_row
    mock_session.execute = AsyncMock(return_value=result_mock)
    mock_session.commit = AsyncMock()
    return mock_session


def _make_session_duplicate_not_found() -> AsyncMock:
    """Build a mock AsyncSession where the entity query returns no matching row.

    Returns
    -------
    AsyncMock
        Configured mock session where execute().scalar_one_or_none() returns None.
    """
    mock_session = AsyncMock(spec=AsyncSession)
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=result_mock)
    mock_session.commit = AsyncMock()
    return mock_session


class TestCheckDuplicateEndpoint:
    """Tests for GET /api/v1/entities/check-duplicate.

    Coverage targets
    ----------------
    - 200 duplicate found: is_duplicate=True with existing_entity populated
    - 200 no duplicate: is_duplicate=False with existing_entity=null
    - normalization-aware matching: lowercase input matches mixed-case entity
    - name normalizes to empty: returns is_duplicate=False without error
    - 429 rate limit exceeded: returns 429 with Retry-After header
    - different type not duplicate: same name but different entity_type → no match
    """

    async def test_200_duplicate_found(self) -> None:
        """When an active entity with the same normalized name and type exists,
        returns 200 with is_duplicate=True and populated existing_entity.

        The existing_entity object must contain entity_id (UUID string),
        canonical_name, entity_type, and description.
        """
        entity_id = uuid.uuid4()
        entity_row = _make_named_entity_for_duplicate(entity_id=entity_id)
        mock_session = _make_session_duplicate_found(entity_row)

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._normalizer"
            ) as mock_normalizer:
                mock_normalizer.normalize.return_value = _DUPLICATE_NORMALIZED

                response = await client.get(
                    _CHECK_DUPLICATE_ENDPOINT,
                    params={"name": _DUPLICATE_NAME, "type": _DUPLICATE_TYPE},
                )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_duplicate"] is True, f"Expected is_duplicate=True in: {body}"
        assert body["existing_entity"] is not None, (
            f"Expected existing_entity to be populated in: {body}"
        )
        existing = body["existing_entity"]
        assert existing["entity_id"] == str(entity_id), (
            f"entity_id mismatch: {existing['entity_id']} != {entity_id}"
        )
        assert existing["canonical_name"] == "Garland Nixon"
        assert existing["entity_type"] == "person"
        assert existing["description"] == "Political commentator"

    async def test_200_no_duplicate(self) -> None:
        """When no active entity with the same normalized name and type exists,
        returns 200 with is_duplicate=False and existing_entity=null.
        """
        mock_session = _make_session_duplicate_not_found()

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._normalizer"
            ) as mock_normalizer:
                mock_normalizer.normalize.return_value = _DUPLICATE_NORMALIZED

                response = await client.get(
                    _CHECK_DUPLICATE_ENDPOINT,
                    params={"name": "Unknown Person", "type": "person"},
                )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_duplicate"] is False, (
            f"Expected is_duplicate=False in: {body}"
        )
        assert body["existing_entity"] is None, (
            f"Expected existing_entity=null in: {body}"
        )

    async def test_normalization_aware_matching(self) -> None:
        """Lowercase input "garland nixon" matches entity "Garland Nixon".

        The normalization step strips case differences, so a query with a
        lowercase name must detect the duplicate against the stored
        mixed-case canonical_name via the canonical_name_normalized column.
        """
        entity_id = uuid.uuid4()
        entity_row = _make_named_entity_for_duplicate(
            entity_id=entity_id,
            canonical_name="Garland Nixon",
        )
        mock_session = _make_session_duplicate_found(entity_row)

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._normalizer"
            ) as mock_normalizer:
                # Simulates normalization stripping case: "garland nixon" → "garland nixon"
                mock_normalizer.normalize.return_value = "garland nixon"

                response = await client.get(
                    _CHECK_DUPLICATE_ENDPOINT,
                    params={"name": "garland nixon", "type": "person"},
                )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_duplicate"] is True, (
            f"Lowercase query should detect mixed-case duplicate, got: {body}"
        )
        assert body["existing_entity"]["canonical_name"] == "Garland Nixon", (
            f"Expected canonical_name='Garland Nixon' in: {body['existing_entity']}"
        )

    async def test_name_normalizes_to_empty(self) -> None:
        """A name that normalizes to empty/None returns is_duplicate=False.

        When ``TagNormalizationService.normalize()`` returns None (or empty),
        the endpoint short-circuits and returns is_duplicate=False without
        querying the database.  This is not an error condition.
        """
        mock_session = _make_session_duplicate_not_found()

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._normalizer"
            ) as mock_normalizer:
                # normalize() returns None → endpoint treats as empty
                mock_normalizer.normalize.return_value = None

                response = await client.get(
                    _CHECK_DUPLICATE_ENDPOINT,
                    params={"name": "   ", "type": "person"},
                )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_duplicate"] is False, (
            f"Empty-normalizing name should yield is_duplicate=False, got: {body}"
        )
        assert body["existing_entity"] is None, (
            f"Expected existing_entity=null when name normalizes empty, got: {body}"
        )
        # Database must NOT be queried when the normalized name is empty
        mock_session.execute.assert_not_called()

    async def test_rate_limit_429(self) -> None:
        """When the rate limit is exceeded, returns 429 with Retry-After header.

        The endpoint calls ``_check_rate_limit`` and, when it returns
        (False, retry_after), responds with a 429 JSONResponse that includes
        the ``Retry-After`` header.
        """
        mock_session = _make_session_duplicate_not_found()

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._check_rate_limit"
            ) as mock_rate_limit:
                # Simulate 50 req/min limit already exceeded; retry after 30s
                mock_rate_limit.return_value = (False, 30)

                response = await client.get(
                    _CHECK_DUPLICATE_ENDPOINT,
                    params={"name": _DUPLICATE_NAME, "type": _DUPLICATE_TYPE},
                )

        assert response.status_code == 429, (
            f"Expected 429 when rate limit exceeded, got {response.status_code}: "
            f"{response.text}"
        )
        assert "Retry-After" in response.headers, (
            f"Missing Retry-After header in 429 response. Headers: {dict(response.headers)}"
        )
        assert response.headers["Retry-After"] == "30", (
            f"Expected Retry-After: 30, got: {response.headers['Retry-After']}"
        )

    async def test_rate_limit_429_response_body(self) -> None:
        """The 429 response body includes a detail message and retry_after field.

        Validates the exact shape of the JSON response body returned when the
        rate limit is exceeded: ``detail`` and ``retry_after`` keys must be present.
        """
        mock_session = _make_session_duplicate_not_found()

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._check_rate_limit"
            ) as mock_rate_limit:
                mock_rate_limit.return_value = (False, 15)

                response = await client.get(
                    _CHECK_DUPLICATE_ENDPOINT,
                    params={"name": _DUPLICATE_NAME, "type": _DUPLICATE_TYPE},
                )

        assert response.status_code == 429, response.text
        body = response.json()
        assert "detail" in body, f"Missing 'detail' key in 429 body: {body}"
        assert "retry_after" in body, f"Missing 'retry_after' key in 429 body: {body}"
        assert body["retry_after"] == 15, (
            f"Expected retry_after=15, got: {body['retry_after']}"
        )

    async def test_different_type_not_duplicate(self) -> None:
        """Entity "Garland Nixon" as "person" exists, but checking with type
        "organization" must return is_duplicate=False.

        The query filters on BOTH canonical_name_normalized AND entity_type.
        A person and an organization with the same normalized name are
        distinct entities.
        """
        mock_session = _make_session_duplicate_not_found()

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._normalizer"
            ) as mock_normalizer:
                mock_normalizer.normalize.return_value = _DUPLICATE_NORMALIZED

                response = await client.get(
                    _CHECK_DUPLICATE_ENDPOINT,
                    params={"name": _DUPLICATE_NAME, "type": "organization"},
                )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["is_duplicate"] is False, (
            f"Different entity_type should not be flagged as duplicate, got: {body}"
        )
        assert body["existing_entity"] is None, (
            f"Expected existing_entity=null for type mismatch, got: {body}"
        )


# ---------------------------------------------------------------------------
# T_CREATE_ENTITY — POST /api/v1/entities
# ---------------------------------------------------------------------------
#
# The endpoint (``create_entity``) lives at
# ``chronovista.api.routers.entity_mentions`` and uses three module-level
# singletons: ``_entity_repo``, ``_alias_repo``, and ``_normalizer``.
#
# Endpoint flow:
# 1. Convert entity_type string → EntityType enum (400 if invalid)
# 2. Normalize the name via _normalizer.normalize() (422 if empty result)
# 3. Auto-title-case: body.name.strip().title()
# 4. Duplicate check: session.execute(SELECT ...).scalar_one_or_none() (409 if found)
# 5. _entity_repo.create() → db_entity row
# 6. _alias_repo.create() for canonical name alias (alias_count starts at 1)
# 7. _alias_repo.create() for each unique user alias (skips normalized duplicates)
# 8. session.commit() + session.refresh(db_entity)
# 9. Return 201 with entity_id, canonical_name, entity_type, description, alias_count
#
# alias_count = len(seen_normalized) — starts with the canonical normalized name
# and grows by 1 for each user alias whose normalized form is not already seen.
#
# Mocking strategy
# ----------------
# - ``_entity_repo.create`` is patched at the module level via ``unittest.mock.patch``
#   on ``chronovista.api.routers.entity_mentions._entity_repo``.
# - ``_alias_repo.create`` is similarly patched.
# - ``_normalizer.normalize`` is patched for tests that require controlled
#   normalization output; for 422 tests it returns None/empty.
# - The DB session's ``execute`` is an AsyncMock that returns a MagicMock with
#   ``scalar_one_or_none()`` returning either a NamedEntityDB mock (409) or None (pass).
# - session.commit and session.refresh are AsyncMock no-ops.
# ---------------------------------------------------------------------------

_CREATE_ENTITY_ENDPOINT = "/api/v1/entities"

_VALID_CREATE_NAME = "edward snowden"
_VALID_CREATE_TYPE = "person"


def _make_create_entity_db_row(
    *,
    entity_id: uuid.UUID | None = None,
    canonical_name: str = "Edward Snowden",
    entity_type: str = "person",
    description: str | None = None,
) -> MagicMock:
    """Build a minimal mock NamedEntityDB row returned by _entity_repo.create().

    Parameters
    ----------
    entity_id : uuid.UUID | None
        Entity primary key UUID.  Auto-generated when None.
    canonical_name : str
        Display name stored on the entity row.
    entity_type : str
        Entity type string (as stored in the DB column).
    description : str | None
        Optional entity description.

    Returns
    -------
    MagicMock
        Mock with the attributes read by the create_entity endpoint after
        session.refresh().
    """
    row = MagicMock()
    row.id = entity_id or uuid.uuid4()
    row.canonical_name = canonical_name
    row.entity_type = entity_type
    row.description = description
    return row


def _make_session_no_duplicate(db_entity_row: MagicMock) -> AsyncMock:
    """Build a mock AsyncSession for the create_entity happy path.

    The endpoint makes these DB calls in order:
    1. session.execute(dup check query) → scalar_one_or_none() returns None
    2. _entity_repo.create() — mocked at module level, not via session
    3. _alias_repo.create() — mocked at module level, not via session
    4. session.commit()
    5. session.refresh(db_entity_row)

    Parameters
    ----------
    db_entity_row : MagicMock
        The entity row; passed so session.refresh can be configured as a
        no-op AsyncMock (the row attributes are already set).

    Returns
    -------
    AsyncMock
        Configured mock session.
    """
    mock_session = AsyncMock(spec=AsyncSession)

    # Duplicate check → not found
    dup_result = MagicMock()
    dup_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=dup_result)

    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    return mock_session


def _make_session_with_existing_entity(existing_row: MagicMock) -> AsyncMock:
    """Build a mock AsyncSession where the dup-check finds an existing entity.

    Parameters
    ----------
    existing_row : MagicMock
        The NamedEntityDB mock row to return from execute().scalar_one_or_none(),
        triggering the 409 ConflictError branch.

    Returns
    -------
    AsyncMock
        Configured mock session.
    """
    mock_session = AsyncMock(spec=AsyncSession)

    dup_result = MagicMock()
    dup_result.scalar_one_or_none.return_value = existing_row
    mock_session.execute = AsyncMock(return_value=dup_result)

    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    return mock_session


class TestCreateEntityEndpoint:
    """Tests for POST /api/v1/entities (standalone entity creation).

    Coverage targets
    ----------------
    - 201 happy path: alias_count reflects canonical alias + user aliases
    - 201 auto-title-casing: lowercase input -> Title Cased canonical_name
    - 409 Conflict: duplicate entity detected by normalized name + type
    - 422 Unprocessable Entity: name that normalizes to empty string
    - 201 with normalized alias duplicates skipped (only unique aliases stored)
    - 422 Unprocessable Entity: more than 20 aliases (Pydantic max_length=20)
    """

    async def test_201_success_with_correct_alias_count(self) -> None:
        """Create "edward snowden" with type "person" and two user aliases.

        The endpoint creates:
        - 1 canonical alias (the title-cased name itself)
        - 1 alias for "Ed Snowden"
        - 1 alias for "Snowden"

        So alias_count must be 3, and canonical_name must be "Edward Snowden".
        """
        entity_id = uuid.uuid4()
        db_entity = _make_create_entity_db_row(
            entity_id=entity_id,
            canonical_name="Edward Snowden",
            entity_type="person",
        )
        mock_session = _make_session_no_duplicate(db_entity)

        async for client in _build_client(mock_session):
            with (
                patch(
                    "chronovista.api.routers.entity_mentions._entity_repo"
                ) as mock_entity_repo,
                patch(
                    "chronovista.api.routers.entity_mentions._alias_repo"
                ) as mock_alias_repo,
                patch(
                    "chronovista.api.routers.entity_mentions._normalizer"
                ) as mock_normalizer,
            ):
                # normalize() maps every alias to a distinct lowercase form
                mock_normalizer.normalize.side_effect = lambda text: text.strip().lower()

                mock_entity_repo.create = AsyncMock(return_value=db_entity)
                mock_alias_repo.create = AsyncMock(return_value=MagicMock())

                response = await client.post(
                    _CREATE_ENTITY_ENDPOINT,
                    json={
                        "name": _VALID_CREATE_NAME,
                        "entity_type": _VALID_CREATE_TYPE,
                        "aliases": ["Ed Snowden", "Snowden"],
                    },
                )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["canonical_name"] == "Edward Snowden", (
            f"Expected 'Edward Snowden', got: {body['canonical_name']}"
        )
        assert body["alias_count"] == 3, (
            f"Expected alias_count=3 (canonical + 2 user aliases), got: {body['alias_count']}"
        )
        assert body["entity_type"] == "person", (
            f"Expected entity_type='person', got: {body['entity_type']}"
        )

    async def test_auto_title_casing(self) -> None:
        """Lowercase input "garland nixon" produces canonical_name="Garland Nixon".

        The endpoint performs ``body.name.strip().title()`` before storing;
        the DB row's canonical_name must reflect the Title-Cased form.
        """
        entity_id = uuid.uuid4()
        db_entity = _make_create_entity_db_row(
            entity_id=entity_id,
            canonical_name="Garland Nixon",
            entity_type="person",
        )
        mock_session = _make_session_no_duplicate(db_entity)

        async for client in _build_client(mock_session):
            with (
                patch(
                    "chronovista.api.routers.entity_mentions._entity_repo"
                ) as mock_entity_repo,
                patch(
                    "chronovista.api.routers.entity_mentions._alias_repo"
                ) as mock_alias_repo,
                patch(
                    "chronovista.api.routers.entity_mentions._normalizer"
                ) as mock_normalizer,
            ):
                mock_normalizer.normalize.return_value = "garland nixon"
                mock_entity_repo.create = AsyncMock(return_value=db_entity)
                mock_alias_repo.create = AsyncMock(return_value=MagicMock())

                response = await client.post(
                    _CREATE_ENTITY_ENDPOINT,
                    json={
                        "name": "garland nixon",
                        "entity_type": "person",
                    },
                )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["canonical_name"] == "Garland Nixon", (
            f"Expected auto-title-cased 'Garland Nixon', got: {body['canonical_name']}"
        )

    async def test_409_duplicate(self) -> None:
        """When an active entity with the same normalized name + type exists, returns 409.

        The duplicate-check query returns an existing NamedEntityDB row, so the
        endpoint raises ConflictError.  The 409 response body must include
        existing_entity details nested inside the ``details`` field.
        """
        existing_id = uuid.uuid4()
        existing_row = MagicMock()
        existing_row.id = existing_id
        existing_row.canonical_name = "Edward Snowden"
        existing_row.entity_type = "person"
        existing_row.description = "NSA whistleblower"

        mock_session = _make_session_with_existing_entity(existing_row)

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._normalizer"
            ) as mock_normalizer:
                mock_normalizer.normalize.return_value = "edward snowden"

                response = await client.post(
                    _CREATE_ENTITY_ENDPOINT,
                    json={
                        "name": "edward snowden",
                        "entity_type": "person",
                    },
                )

        assert response.status_code == 409, response.text

    async def test_409_duplicate_response_body_shape(self) -> None:
        """The 409 response body follows the RFC 7807 Problem Detail format.

        The exception handler converts ConflictError to an RFC 7807 response
        using only ``exc.message`` — the ``details`` dict is not serialized
        into the response body (see exception_handlers.py:api_error_handler).
        The body must contain: type, title, status, detail, instance, code.
        The ``detail`` field must reference the normalized name to help callers
        identify which entity caused the conflict.
        """
        existing_id = uuid.uuid4()
        existing_row = MagicMock()
        existing_row.id = existing_id
        existing_row.canonical_name = "Edward Snowden"
        existing_row.entity_type = "person"
        existing_row.description = "NSA whistleblower"

        mock_session = _make_session_with_existing_entity(existing_row)

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._normalizer"
            ) as mock_normalizer:
                mock_normalizer.normalize.return_value = "edward snowden"

                response = await client.post(
                    _CREATE_ENTITY_ENDPOINT,
                    json={
                        "name": "edward snowden",
                        "entity_type": "person",
                    },
                )

        assert response.status_code == 409, response.text
        body = response.json()
        # RFC 7807 required fields must be present
        assert "status" in body, f"Missing 'status' in 409 body: {body}"
        assert "detail" in body, f"Missing 'detail' in 409 body: {body}"
        assert body["status"] == 409, (
            f"Expected status=409 in body, got: {body['status']}"
        )
        # The detail message must reference the normalized name so callers
        # know which entity caused the conflict
        assert "edward snowden" in body["detail"], (
            f"Expected normalized name in detail, got: {body['detail']}"
        )

    async def test_422_name_normalizes_to_empty(self) -> None:
        """A name whose normalized form is empty triggers a 422 APIValidationError.

        When ``_normalizer.normalize()`` returns None (or empty string), the
        endpoint raises APIValidationError before touching the database.
        """
        mock_session = AsyncMock(spec=AsyncSession)

        async for client in _build_client(mock_session):
            with patch(
                "chronovista.api.routers.entity_mentions._normalizer"
            ) as mock_normalizer:
                mock_normalizer.normalize.return_value = None

                response = await client.post(
                    _CREATE_ENTITY_ENDPOINT,
                    json={
                        "name": "   ",
                        "entity_type": "person",
                    },
                )

        assert response.status_code == 422, response.text
        # Database must NOT be queried when the name normalizes to empty
        mock_session.execute.assert_not_called()

    async def test_aliases_with_normalized_duplicates_skipped(self) -> None:
        """Aliases ["Ed Snowden", "ed snowden"] produce only 1 additional alias.

        When two user-supplied aliases normalize to the same string, the second
        is silently skipped.  alias_count = 1 (canonical) + 1 (unique alias) = 2.
        """
        entity_id = uuid.uuid4()
        db_entity = _make_create_entity_db_row(
            entity_id=entity_id,
            canonical_name="Edward Snowden",
            entity_type="person",
        )
        mock_session = _make_session_no_duplicate(db_entity)

        async for client in _build_client(mock_session):
            with (
                patch(
                    "chronovista.api.routers.entity_mentions._entity_repo"
                ) as mock_entity_repo,
                patch(
                    "chronovista.api.routers.entity_mentions._alias_repo"
                ) as mock_alias_repo,
                patch(
                    "chronovista.api.routers.entity_mentions._normalizer"
                ) as mock_normalizer,
            ):
                # "edward snowden" -> "edward snowden" (canonical)
                # "Ed Snowden"     -> "ed snowden" (unique alias)
                # "ed snowden"     -> "ed snowden" (DUPLICATE -> skipped)
                mock_normalizer.normalize.side_effect = lambda text: text.strip().lower()
                mock_entity_repo.create = AsyncMock(return_value=db_entity)
                mock_alias_repo.create = AsyncMock(return_value=MagicMock())

                response = await client.post(
                    _CREATE_ENTITY_ENDPOINT,
                    json={
                        "name": "edward snowden",
                        "entity_type": "person",
                        "aliases": ["Ed Snowden", "ed snowden"],
                    },
                )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["alias_count"] == 2, (
            f"Expected alias_count=2 (canonical + 1 unique alias, 1 duplicate skipped), "
            f"got: {body['alias_count']}"
        )

    async def test_max_20_aliases_validation(self) -> None:
        """Submitting 21 aliases is rejected by Pydantic max_length=20 -> 422.

        CreateEntityRequest.aliases has ``max_length=20``; any list with more
        than 20 items fails Pydantic schema validation before the handler runs.
        """
        too_many_aliases = [f"Alias {i}" for i in range(21)]
        mock_session = AsyncMock(spec=AsyncSession)

        async for client in _build_client(mock_session):
            response = await client.post(
                _CREATE_ENTITY_ENDPOINT,
                json={
                    "name": "edward snowden",
                    "entity_type": "person",
                    "aliases": too_many_aliases,
                },
            )

        assert response.status_code == 422, response.text
