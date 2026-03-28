"""Integration tests for entity creation API endpoints (Feature 051).

Covers the three entity-creation and duplicate-detection endpoints:
  - POST /api/v1/entities/classify
  - POST /api/v1/entities
  - GET /api/v1/entities/check-duplicate

All tests require the integration database (chronovista_integration_test).
Each test class seeds its own data and cleans up after itself in FK-reverse
order to preserve isolation from other integration test files.

Auth: ``require_auth`` is bypassed by patching
``chronovista.api.deps.youtube_oauth`` so tests do not require real OAuth
credentials, following the pattern established in
``test_entity_mentions_api.py``.

Notes
-----
- Stable ID prefixes use ``ect_`` (Entity Creation Test) to avoid collisions.
- channel_id max 24 chars, video_id max 20 chars (PostgreSQL column limits).
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.db.models import (
    CanonicalTag as CanonicalTagDB,
)
from chronovista.db.models import (
    EntityAlias as EntityAliasDB,
)
from chronovista.db.models import (
    NamedEntity as NamedEntityDB,
)
from chronovista.db.models import (
    TagAlias as TagAliasDB,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import async_sessionmaker

# CRITICAL: Ensures all async tests in this module run with pytest-asyncio
# ---------------------------------------------------------------------------
# Stable test IDs — chosen to avoid collisions with all other test files.
# ---------------------------------------------------------------------------
_CHANNEL_ID = "UCect_creation_test01"  # 21 chars — within 24-char limit


# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def _classify_url() -> str:
    """Return the classify tag endpoint URL."""
    return "/api/v1/entities/classify"


def _create_entity_url() -> str:
    """Return the standalone entity creation endpoint URL."""
    return "/api/v1/entities"


def _check_duplicate_url(name: str, entity_type: str) -> str:
    """Return the duplicate check endpoint URL with query params."""
    return f"/api/v1/entities/check-duplicate?name={name}&type={entity_type}"


def _entity_detail_url(entity_id: str) -> str:
    """Return the entity detail endpoint URL."""
    return f"/api/v1/entities/{entity_id}"


# ---------------------------------------------------------------------------
# Shared helper: authenticated request context manager
# ---------------------------------------------------------------------------


def _authenticated():
    """Context manager that patches oauth to return is_authenticated=True."""
    mock = patch("chronovista.api.deps.youtube_oauth")
    return mock


# ---------------------------------------------------------------------------
# TestClassifyFlowEndToEnd
# ---------------------------------------------------------------------------


class TestClassifyFlowEndToEnd:
    """Integration tests for POST /api/v1/entities/classify."""

    @pytest.fixture
    async def seed_canonical_tag(
        self,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Seed a canonical tag with a tag alias for classify tests.

        Yields a dict with:
        - ``tag_id``: CanonicalTag UUID
        - ``canonical_form``: display form
        - ``normalized_form``: normalized form used in classify requests
        - ``tag_alias_raw``: raw form of the seeded TagAlias

        Cleanup removes all seeded rows in FK-reverse order.
        """
        tag_id = uuid.UUID(bytes=uuid7().bytes)
        canonical_form = "Ect Classify Person"
        normalized_form = "ect classify person"
        tag_alias_raw = "ECT Classify Person"

        async with integration_session_factory() as session:
            # Remove any leftover rows from previous runs
            await session.execute(
                delete(TagAliasDB).where(
                    TagAliasDB.normalized_form == normalized_form
                )
            )
            await session.execute(
                delete(CanonicalTagDB).where(
                    CanonicalTagDB.normalized_form == normalized_form
                )
            )
            await session.execute(
                delete(NamedEntityDB).where(
                    NamedEntityDB.canonical_name_normalized == normalized_form,
                    NamedEntityDB.entity_type == "person",
                )
            )
            await session.commit()

            # Seed the canonical tag
            tag = CanonicalTagDB(
                id=tag_id,
                canonical_form=canonical_form,
                normalized_form=normalized_form,
                alias_count=1,
                video_count=0,
                status="active",
            )
            session.add(tag)
            await session.commit()

            # Seed one tag alias linked to the canonical tag
            tag_alias = TagAliasDB(
                id=uuid.UUID(bytes=uuid7().bytes),
                raw_form=tag_alias_raw,
                normalized_form=normalized_form,
                canonical_tag_id=tag_id,
                creation_method="auto_normalize",
                occurrence_count=1,
            )
            session.add(tag_alias)
            await session.commit()

        yield {
            "tag_id": tag_id,
            "canonical_form": canonical_form,
            "normalized_form": normalized_form,
            "tag_alias_raw": tag_alias_raw,
        }

        # Cleanup — FK reverse: entity_aliases before named_entities, tag_aliases before canonical_tags
        async with integration_session_factory() as session:
            # Fetch entity linked to the tag (if any) and delete its aliases
            tag_row = (
                await session.execute(
                    select(CanonicalTagDB).where(
                        CanonicalTagDB.normalized_form == normalized_form
                    )
                )
            ).scalar_one_or_none()
            if tag_row is not None and tag_row.entity_id is not None:
                await session.execute(
                    delete(EntityAliasDB).where(
                        EntityAliasDB.entity_id == tag_row.entity_id
                    )
                )
            await session.execute(
                delete(NamedEntityDB).where(
                    NamedEntityDB.canonical_name_normalized == normalized_form,
                    NamedEntityDB.entity_type == "person",
                )
            )
            await session.execute(
                delete(TagAliasDB).where(
                    TagAliasDB.normalized_form == normalized_form
                )
            )
            await session.execute(
                delete(CanonicalTagDB).where(
                    CanonicalTagDB.normalized_form == normalized_form
                )
            )
            await session.commit()

    async def test_classify_flow_end_to_end(
        self,
        async_client: AsyncClient,
        seed_canonical_tag: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """POST /entities/classify returns 201 and correctly links entity to tag.

        Verifies:
        - 201 response with entity_id, canonical_name, entity_type.
        - NamedEntity row exists in DB with correct canonical_name and entity_type.
        - CanonicalTag.entity_id is set to the newly created entity.
        - At least one EntityAlias (the self-alias) is created for the entity.
        """
        normalized_form = seed_canonical_tag["normalized_form"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _classify_url(),
                json={
                    "normalized_form": normalized_form,
                    "entity_type": "person",
                },
            )

        assert response.status_code == 201, (
            f"Expected 201 but got {response.status_code}: {response.text}"
        )
        body = response.json()

        # Response must contain required fields
        assert "entity_id" in body, f"Missing entity_id in response: {body}"
        assert "canonical_name" in body, f"Missing canonical_name in response: {body}"
        assert "entity_type" in body, f"Missing entity_type in response: {body}"
        assert body["entity_type"] == "person", (
            f"Expected entity_type 'person', got: {body['entity_type']}"
        )
        assert body["entity_created"] is True, (
            f"Expected entity_created=True, got: {body.get('entity_created')}"
        )

        entity_id_str = body["entity_id"]
        assert entity_id_str is not None, "entity_id must not be None after classify"

        # Verify DB state: NamedEntity row must exist
        async with integration_session_factory() as session:
            entity_uuid = uuid.UUID(entity_id_str)
            db_entity = await session.get(NamedEntityDB, entity_uuid)
            assert db_entity is not None, (
                f"NamedEntity {entity_id_str} not found in DB after classify"
            )
            assert db_entity.entity_type == "person", (
                f"NamedEntity.entity_type mismatch: {db_entity.entity_type}"
            )
            # canonical_name should be title-cased (auto_case=True in endpoint)
            assert db_entity.canonical_name is not None
            assert db_entity.canonical_name_normalized == normalized_form, (
                f"Normalized name mismatch: {db_entity.canonical_name_normalized}"
            )

            # Verify CanonicalTag.entity_id is linked
            db_tag = await session.get(CanonicalTagDB, seed_canonical_tag["tag_id"])
            assert db_tag is not None, "CanonicalTag must still exist after classify"
            assert db_tag.entity_id == entity_uuid, (
                f"CanonicalTag.entity_id not linked: expected {entity_uuid}, "
                f"got {db_tag.entity_id}"
            )
            assert db_tag.entity_type == "person", (
                f"CanonicalTag.entity_type not set: {db_tag.entity_type}"
            )

            # Verify EntityAlias (self-alias) was created
            aliases_result = await session.execute(
                select(EntityAliasDB).where(
                    EntityAliasDB.entity_id == entity_uuid
                )
            )
            aliases = aliases_result.scalars().all()
            assert len(aliases) >= 1, (
                f"Expected at least 1 EntityAlias (self-alias), found {len(aliases)}"
            )
            alias_names_normalized = [a.alias_name_normalized for a in aliases]
            assert normalized_form in alias_names_normalized, (
                f"Self-alias with normalized_form='{normalized_form}' not found "
                f"in entity aliases: {alias_names_normalized}"
            )

    async def test_classify_returns_409_when_tag_already_classified(
        self,
        async_client: AsyncClient,
        seed_canonical_tag: dict[str, Any],
    ) -> None:
        """POST /entities/classify returns 409 on a second classify call for the same tag.

        The first call succeeds (201); the second call must return 409 because
        the tag is already classified and force is not set.
        """
        normalized_form = seed_canonical_tag["normalized_form"]

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            # First classify — should succeed
            first_response = await async_client.post(
                _classify_url(),
                json={
                    "normalized_form": normalized_form,
                    "entity_type": "person",
                },
            )
            assert first_response.status_code == 201, (
                f"First classify failed unexpectedly: {first_response.text}"
            )

            # Second classify — should conflict
            second_response = await async_client.post(
                _classify_url(),
                json={
                    "normalized_form": normalized_form,
                    "entity_type": "person",
                },
            )

        assert second_response.status_code == 409, (
            f"Expected 409 on duplicate classify but got "
            f"{second_response.status_code}: {second_response.text}"
        )

    async def test_classify_returns_404_for_unknown_tag(
        self,
        async_client: AsyncClient,
    ) -> None:
        """POST /entities/classify returns 404 when normalized_form does not exist."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _classify_url(),
                json={
                    "normalized_form": "ect nonexistent tag zzzz",
                    "entity_type": "person",
                },
            )

        assert response.status_code == 404, (
            f"Expected 404 for unknown tag, got {response.status_code}: {response.text}"
        )


# ---------------------------------------------------------------------------
# TestStandaloneCreationEndToEnd
# ---------------------------------------------------------------------------


class TestStandaloneCreationEndToEnd:
    """Integration tests for POST /api/v1/entities."""

    # Stable normalized forms used across fixtures/tests in this class
    _SNOWDEN_NORMALIZED = "edward snowden"

    @pytest.fixture(autouse=True)
    async def cleanup_snowden(
        self,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncGenerator[None, None]:
        """Remove any leftover Edward Snowden entity rows before and after each test."""
        normalized = self._SNOWDEN_NORMALIZED

        async def _wipe(session: AsyncSession) -> None:
            rows = (
                await session.execute(
                    select(NamedEntityDB).where(
                        NamedEntityDB.canonical_name_normalized == normalized,
                        NamedEntityDB.entity_type == "person",
                    )
                )
            ).scalars().all()
            for row in rows:
                await session.execute(
                    delete(EntityAliasDB).where(EntityAliasDB.entity_id == row.id)
                )
            await session.execute(
                delete(NamedEntityDB).where(
                    NamedEntityDB.canonical_name_normalized == normalized,
                    NamedEntityDB.entity_type == "person",
                )
            )
            await session.commit()

        async with integration_session_factory() as session:
            await _wipe(session)

        yield

        async with integration_session_factory() as session:
            await _wipe(session)

    async def test_standalone_creation_end_to_end(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """POST /entities creates an entity with title-cased name and aliases.

        Verifies:
        - 201 response.
        - canonical_name is title-cased ("Edward Snowden").
        - NamedEntity exists in DB with correct canonical_name and entity_type.
        - 3 EntityAlias rows exist: canonical name + 2 user-supplied aliases.
        """
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _create_entity_url(),
                json={
                    "name": "edward snowden",
                    "entity_type": "person",
                    "aliases": ["Ed Snowden", "Snowden"],
                },
            )

        assert response.status_code == 201, (
            f"Expected 201 but got {response.status_code}: {response.text}"
        )
        body = response.json()

        # Verify response shape
        assert "entity_id" in body, f"Missing entity_id in response: {body}"
        assert "canonical_name" in body, f"Missing canonical_name in response: {body}"
        assert "entity_type" in body, f"Missing entity_type in response: {body}"
        assert "alias_count" in body, f"Missing alias_count in response: {body}"

        # canonical_name must be title-cased
        assert body["canonical_name"] == "Edward Snowden", (
            f"Expected title-cased 'Edward Snowden', got: {body['canonical_name']}"
        )
        assert body["entity_type"] == "person", (
            f"Expected entity_type 'person', got: {body['entity_type']}"
        )

        entity_id_str = body["entity_id"]
        entity_uuid = uuid.UUID(entity_id_str)

        # Verify DB state
        async with integration_session_factory() as session:
            db_entity = await session.get(NamedEntityDB, entity_uuid)
            assert db_entity is not None, (
                f"NamedEntity {entity_id_str} not found in DB"
            )
            assert db_entity.canonical_name == "Edward Snowden", (
                f"DB canonical_name mismatch: {db_entity.canonical_name}"
            )
            assert db_entity.canonical_name_normalized == self._SNOWDEN_NORMALIZED, (
                f"DB canonical_name_normalized mismatch: "
                f"{db_entity.canonical_name_normalized}"
            )
            assert db_entity.entity_type == "person", (
                f"DB entity_type mismatch: {db_entity.entity_type}"
            )
            assert db_entity.status == "active", (
                f"DB status mismatch: {db_entity.status}"
            )

            # Verify alias count — canonical name + 2 user aliases = 3 aliases
            aliases_result = await session.execute(
                select(EntityAliasDB).where(
                    EntityAliasDB.entity_id == entity_uuid
                )
            )
            aliases = aliases_result.scalars().all()
            assert len(aliases) == 3, (
                f"Expected 3 aliases (canonical + 2 user), found {len(aliases)}: "
                f"{[a.alias_name for a in aliases]}"
            )

            alias_names = {a.alias_name for a in aliases}
            assert "Edward Snowden" in alias_names, (
                f"Canonical alias 'Edward Snowden' missing: {alias_names}"
            )
            assert "Ed Snowden" in alias_names, (
                f"User alias 'Ed Snowden' missing: {alias_names}"
            )
            assert "Snowden" in alias_names, (
                f"User alias 'Snowden' missing: {alias_names}"
            )

    async def test_standalone_creation_deduplicates_identical_aliases(
        self,
        async_client: AsyncClient,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """POST /entities de-duplicates aliases that normalize to the same form.

        When the aliases list contains a value whose normalized form equals
        the entity's own normalized form, it should be silently skipped so
        no unique-constraint error occurs.
        """
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _create_entity_url(),
                json={
                    "name": "edward snowden",
                    "entity_type": "person",
                    # "Edward Snowden" normalizes the same as the entity name
                    "aliases": ["Edward Snowden", "Ed Snowden"],
                },
            )

        assert response.status_code == 201, (
            f"Expected 201 but got {response.status_code}: {response.text}"
        )
        body = response.json()
        entity_uuid = uuid.UUID(body["entity_id"])

        async with integration_session_factory() as session:
            aliases_result = await session.execute(
                select(EntityAliasDB).where(
                    EntityAliasDB.entity_id == entity_uuid
                )
            )
            aliases = aliases_result.scalars().all()
            # canonical + "Ed Snowden" only — "Edward Snowden" duplicate skipped
            assert len(aliases) == 2, (
                f"Expected 2 aliases after dedup, found {len(aliases)}: "
                f"{[a.alias_name for a in aliases]}"
            )

    async def test_standalone_creation_rejects_invalid_entity_type(
        self,
        async_client: AsyncClient,
    ) -> None:
        """POST /entities returns 422 when entity_type is not a valid value."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _create_entity_url(),
                json={
                    "name": "Test Entity",
                    "entity_type": "invalid_type_xyz",
                },
            )

        # Pydantic validation rejects invalid entity_type with 422
        assert response.status_code == 422, (
            f"Expected 422 for invalid entity_type, got "
            f"{response.status_code}: {response.text}"
        )


# ---------------------------------------------------------------------------
# TestDuplicateDetection
# ---------------------------------------------------------------------------


class TestDuplicateDetection:
    """Integration tests for GET /api/v1/entities/check-duplicate."""

    _GARLAND_CANONICAL = "Garland Nixon"
    _GARLAND_NORMALIZED = "garland nixon"

    @pytest.fixture
    async def seed_garland_entity(
        self,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Seed a 'Garland Nixon' named entity for duplicate detection tests.

        Yields a dict with:
        - ``entity_id``: UUID of the seeded entity
        - ``canonical_name``: "Garland Nixon"
        - ``normalized_name``: "garland nixon"

        Cleanup removes the entity and its aliases.
        """
        entity_id = uuid.UUID(bytes=uuid7().bytes)
        canonical = self._GARLAND_CANONICAL
        normalized = self._GARLAND_NORMALIZED

        async with integration_session_factory() as session:
            # Remove any leftover from prior runs
            existing = (
                await session.execute(
                    select(NamedEntityDB).where(
                        NamedEntityDB.canonical_name_normalized == normalized,
                        NamedEntityDB.entity_type == "person",
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                await session.execute(
                    delete(EntityAliasDB).where(
                        EntityAliasDB.entity_id == existing.id
                    )
                )
                await session.execute(
                    delete(NamedEntityDB).where(NamedEntityDB.id == existing.id)
                )
                await session.commit()

            # Seed the entity
            entity = NamedEntityDB(
                id=entity_id,
                canonical_name=canonical,
                canonical_name_normalized=normalized,
                entity_type="person",
                status="active",
                discovery_method="user_created",
                confidence=1.0,
            )
            session.add(entity)
            await session.commit()

        yield {
            "entity_id": entity_id,
            "entity_id_str": str(entity_id),
            "canonical_name": canonical,
            "normalized_name": normalized,
        }

        # Cleanup
        async with integration_session_factory() as session:
            await session.execute(
                delete(EntityAliasDB).where(
                    EntityAliasDB.entity_id == entity_id
                )
            )
            await session.execute(
                delete(NamedEntityDB).where(NamedEntityDB.id == entity_id)
            )
            await session.commit()

    async def test_duplicate_detection_returns_correct_entity(
        self,
        async_client: AsyncClient,
        seed_garland_entity: dict[str, Any],
    ) -> None:
        """GET /entities/check-duplicate returns is_duplicate=True for existing entity.

        Sends the query with lower-case input ("garland nixon") to verify the
        endpoint normalizes before comparison.  Verifies:
        - is_duplicate: True
        - existing_entity has correct entity_id, canonical_name, and entity_type.
        """
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                _check_duplicate_url(
                    name="garland+nixon",
                    entity_type="person",
                )
            )

        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )
        body = response.json()

        assert body["is_duplicate"] is True, (
            f"Expected is_duplicate=True, got: {body.get('is_duplicate')}"
        )
        existing = body.get("existing_entity")
        assert existing is not None, (
            f"Expected existing_entity to be populated, got None. Body: {body}"
        )
        assert existing["entity_id"] == seed_garland_entity["entity_id_str"], (
            f"entity_id mismatch: expected {seed_garland_entity['entity_id_str']}, "
            f"got {existing['entity_id']}"
        )
        assert existing["canonical_name"] == self._GARLAND_CANONICAL, (
            f"canonical_name mismatch: {existing['canonical_name']}"
        )
        assert existing["entity_type"] == "person", (
            f"entity_type mismatch: {existing['entity_type']}"
        )

    async def test_duplicate_check_returns_false_for_unknown_entity(
        self,
        async_client: AsyncClient,
    ) -> None:
        """GET /entities/check-duplicate returns is_duplicate=False for unknown name."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.get(
                _check_duplicate_url(
                    name="zzz+nobody+ect+xyz",
                    entity_type="person",
                )
            )

        assert response.status_code == 200, (
            f"Expected 200 but got {response.status_code}: {response.text}"
        )
        body = response.json()
        assert body["is_duplicate"] is False, (
            f"Expected is_duplicate=False, got: {body.get('is_duplicate')}"
        )
        assert body.get("existing_entity") is None, (
            f"Expected existing_entity=None, got: {body.get('existing_entity')}"
        )


# ---------------------------------------------------------------------------
# Test409OnDuplicateCreation
# ---------------------------------------------------------------------------


class TestConflictOnDuplicateCreation:
    """Integration tests for 409 conflict behaviour on POST /api/v1/entities."""

    _GARLAND_CANONICAL = "Garland Nixon"
    _GARLAND_NORMALIZED = "garland nixon"

    @pytest.fixture
    async def seed_garland_for_conflict(
        self,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Seed a 'Garland Nixon' named entity for the 409 conflict test.

        Separate fixture (vs TestDuplicateDetection) to avoid cross-test
        state dependency.
        """
        entity_id = uuid.UUID(bytes=uuid7().bytes)
        canonical = self._GARLAND_CANONICAL
        normalized = self._GARLAND_NORMALIZED

        async with integration_session_factory() as session:
            # Remove any leftover from prior runs
            existing = (
                await session.execute(
                    select(NamedEntityDB).where(
                        NamedEntityDB.canonical_name_normalized == normalized,
                        NamedEntityDB.entity_type == "person",
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                await session.execute(
                    delete(EntityAliasDB).where(
                        EntityAliasDB.entity_id == existing.id
                    )
                )
                await session.execute(
                    delete(NamedEntityDB).where(NamedEntityDB.id == existing.id)
                )
                await session.commit()

            entity = NamedEntityDB(
                id=entity_id,
                canonical_name=canonical,
                canonical_name_normalized=normalized,
                entity_type="person",
                status="active",
                discovery_method="user_created",
                confidence=1.0,
            )
            session.add(entity)
            await session.commit()

        yield {
            "entity_id": entity_id,
            "entity_id_str": str(entity_id),
        }

        # Cleanup
        async with integration_session_factory() as session:
            await session.execute(
                delete(EntityAliasDB).where(
                    EntityAliasDB.entity_id == entity_id
                )
            )
            await session.execute(
                delete(NamedEntityDB).where(NamedEntityDB.id == entity_id)
            )
            await session.commit()

    async def test_409_on_duplicate_creation(
        self,
        async_client: AsyncClient,
        seed_garland_for_conflict: dict[str, Any],
    ) -> None:
        """POST /entities returns 409 when entity with same name+type already exists.

        Attempts to create another "Garland Nixon" (person) while one is
        already active in the DB; expects the endpoint to detect the
        duplicate and return 409 Conflict.
        """
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _create_entity_url(),
                json={
                    "name": "Garland Nixon",
                    "entity_type": "person",
                },
            )

        assert response.status_code == 409, (
            f"Expected 409 Conflict on duplicate entity creation, "
            f"got {response.status_code}: {response.text}"
        )

    async def test_same_name_different_type_is_allowed(
        self,
        async_client: AsyncClient,
        seed_garland_for_conflict: dict[str, Any],
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        """POST /entities allows same name when entity_type differs.

        'Garland Nixon' as 'organization' should not conflict with the
        seeded 'Garland Nixon' of type 'person'.
        """
        async with integration_session_factory() as session:
            # Pre-clean any existing 'garland nixon' of type 'organization'
            existing = (
                await session.execute(
                    select(NamedEntityDB).where(
                        NamedEntityDB.canonical_name_normalized
                        == self._GARLAND_NORMALIZED,
                        NamedEntityDB.entity_type == "organization",
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                await session.execute(
                    delete(EntityAliasDB).where(
                        EntityAliasDB.entity_id == existing.id
                    )
                )
                await session.execute(
                    delete(NamedEntityDB).where(NamedEntityDB.id == existing.id)
                )
                await session.commit()

        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True
            response = await async_client.post(
                _create_entity_url(),
                json={
                    "name": "Garland Nixon",
                    "entity_type": "organization",
                },
            )

        try:
            assert response.status_code == 201, (
                f"Expected 201 for different entity_type, "
                f"got {response.status_code}: {response.text}"
            )
        finally:
            # Cleanup the newly created organization entity
            async with integration_session_factory() as session:
                created = (
                    await session.execute(
                        select(NamedEntityDB).where(
                            NamedEntityDB.canonical_name_normalized
                            == self._GARLAND_NORMALIZED,
                            NamedEntityDB.entity_type == "organization",
                        )
                    )
                ).scalar_one_or_none()
                if created is not None:
                    await session.execute(
                        delete(EntityAliasDB).where(
                            EntityAliasDB.entity_id == created.id
                        )
                    )
                    await session.execute(
                        delete(NamedEntityDB).where(NamedEntityDB.id == created.id)
                    )
                    await session.commit()
