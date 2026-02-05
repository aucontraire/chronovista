"""Integration tests for language preferences endpoints (US4)."""
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from chronovista.api.main import app
from chronovista.api.deps import get_db

pytestmark = pytest.mark.asyncio


async def get_mock_db() -> AsyncGenerator[AsyncMock, None]:
    """Mock database session dependency."""
    from unittest.mock import MagicMock

    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()
    mock_session.close = AsyncMock()

    # Mock execute method to return a properly structured result
    mock_result = AsyncMock()
    mock_scalars = MagicMock()  # Use MagicMock for synchronous method
    mock_scalars.all = MagicMock(return_value=[])
    mock_result.scalars = MagicMock(return_value=mock_scalars)
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_session.add = MagicMock()  # Use MagicMock for synchronous method

    yield mock_session


class TestGetLanguagePreferences:
    """Tests for GET /api/v1/preferences/languages endpoint."""

    async def test_get_preferences_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """Test that get preferences requires authentication."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.get("/api/v1/preferences/languages")
            assert response.status_code == 401
            data = response.json()
            # Auth errors still use old format (HTTPException detail dict)
            assert data["detail"]["code"] == "NOT_AUTHENTICATED"

    async def test_get_preferences_returns_list_structure(
        self, async_client: AsyncClient
    ) -> None:
        """Test get preferences returns correct list structure."""
        # Override dependencies
        app.dependency_overrides[get_db] = get_mock_db

        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True

                # Mock the repository to return empty list
                with patch("chronovista.api.routers.preferences.container") as mock_container:
                    mock_repo = AsyncMock()
                    mock_repo.get_user_preferences = AsyncMock(return_value=[])
                    mock_container.create_user_language_preference_repository.return_value = (
                        mock_repo
                    )

                    response = await async_client.get("/api/v1/preferences/languages")
                    assert response.status_code == 200
                    data = response.json()
                    assert "data" in data
                    assert isinstance(data["data"], list)
        finally:
            app.dependency_overrides.clear()

    async def test_get_preferences_empty_returns_empty_list(
        self, async_client: AsyncClient
    ) -> None:
        """Test empty preferences returns empty list (not error)."""
        # Override dependencies
        app.dependency_overrides[get_db] = get_mock_db

        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True

                # Mock the repository to return empty list
                with patch("chronovista.api.routers.preferences.container") as mock_container:
                    mock_repo = AsyncMock()
                    mock_repo.get_user_preferences = AsyncMock(return_value=[])
                    mock_container.create_user_language_preference_repository.return_value = (
                        mock_repo
                    )

                    response = await async_client.get("/api/v1/preferences/languages")
                    assert response.status_code == 200
                    data = response.json()
                    assert data["data"] == []
        finally:
            app.dependency_overrides.clear()

    async def test_get_preferences_item_structure(
        self, async_client: AsyncClient
    ) -> None:
        """Test preference item structure when data exists."""
        # Override dependencies
        app.dependency_overrides[get_db] = get_mock_db

        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True

                # Create a mock preference object
                from chronovista.models.enums import LanguageCode, LanguagePreferenceType

                mock_pref = AsyncMock()
                mock_pref.language_code = LanguageCode.ENGLISH
                mock_pref.preference_type = LanguagePreferenceType.FLUENT
                mock_pref.priority = 1
                mock_pref.learning_goal = None

                # Mock the repository to return one preference
                with patch(
                    "chronovista.api.routers.preferences.container"
                ) as mock_container:
                    mock_repo = AsyncMock()
                    mock_repo.get_user_preferences = AsyncMock(return_value=[mock_pref])
                    mock_container.create_user_language_preference_repository.return_value = (
                        mock_repo
                    )

                    response = await async_client.get("/api/v1/preferences/languages")
                    assert response.status_code == 200
                    data = response.json()
                    assert len(data["data"]) == 1
                    item = data["data"][0]
                    assert "language_code" in item
                    assert "preference_type" in item
                    assert "priority" in item
                    assert "learning_goal" in item
                    assert item["language_code"] == "en"
                    assert item["preference_type"] == "fluent"
                    assert item["priority"] == 1
        finally:
            app.dependency_overrides.clear()


class TestUpdateLanguagePreferences:
    """Tests for PUT /api/v1/preferences/languages endpoint."""

    async def test_update_preferences_requires_auth(
        self, async_client: AsyncClient
    ) -> None:
        """Test that update preferences requires authentication."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = False
            response = await async_client.put(
                "/api/v1/preferences/languages", json={"preferences": []}
            )
            assert response.status_code == 401
            data = response.json()
            # Auth errors still use old format (HTTPException detail dict)
            assert data["detail"]["code"] == "NOT_AUTHENTICATED"

    async def test_update_preferences_empty_list(
        self, async_client: AsyncClient
    ) -> None:
        """Test updating with empty list clears preferences."""
        # Override dependencies
        app.dependency_overrides[get_db] = get_mock_db

        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True

                # Mock repository operations
                with patch("chronovista.api.routers.preferences.container") as mock_container:
                    mock_repo = AsyncMock()
                    mock_repo.delete_all_user_preferences = AsyncMock()
                    mock_repo.save_preferences = AsyncMock()
                    mock_repo.get_user_preferences = AsyncMock(return_value=[])
                    mock_container.create_user_language_preference_repository.return_value = (
                        mock_repo
                    )

                    response = await async_client.put(
                        "/api/v1/preferences/languages", json={"preferences": []}
                    )
                    assert response.status_code == 200
                    data = response.json()
                    assert data["data"] == []

                    # Verify delete was called
                    mock_repo.delete_all_user_preferences.assert_called_once()
        finally:
            app.dependency_overrides.clear()

    async def test_update_preferences_invalid_language_code(
        self, async_client: AsyncClient
    ) -> None:
        """Test validation rejects invalid language codes."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.put(
                "/api/v1/preferences/languages",
                json={
                    "preferences": [
                        {"language_code": "invalid-code", "preference_type": "fluent"}
                    ]
                },
            )
            assert response.status_code == 400
            data = response.json()
            # RFC 7807 format: code is at top level
            assert data["code"] == "BAD_REQUEST"
            assert "invalid-code" in data["detail"]

    async def test_update_preferences_invalid_preference_type(
        self, async_client: AsyncClient
    ) -> None:
        """Test validation rejects invalid preference types."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.put(
                "/api/v1/preferences/languages",
                json={
                    "preferences": [
                        {"language_code": "en", "preference_type": "invalid_type"}
                    ]
                },
            )
            assert response.status_code == 400
            data = response.json()
            # RFC 7807 format: code is at top level
            assert data["code"] == "BAD_REQUEST"
            assert "invalid_type" in data["detail"]

    async def test_update_preferences_valid_types(
        self, async_client: AsyncClient
    ) -> None:
        """Test all valid preference types are accepted."""
        # Override dependencies
        app.dependency_overrides[get_db] = get_mock_db

        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True

                # Mock repository operations for each test
                valid_types = ["fluent", "learning", "curious", "exclude"]

                for pref_type in valid_types:
                    with patch("chronovista.api.routers.preferences.container") as mock_container:
                        # Create mock preference return value
                        from chronovista.models.enums import (
                            LanguageCode,
                            LanguagePreferenceType,
                        )

                        mock_pref = AsyncMock()
                        mock_pref.language_code = LanguageCode.ENGLISH
                        mock_pref.preference_type = LanguagePreferenceType(pref_type)
                        mock_pref.priority = 1
                        mock_pref.learning_goal = None

                        mock_repo = AsyncMock()
                        mock_repo.delete_all_user_preferences = AsyncMock()
                        mock_repo.save_preferences = AsyncMock()
                        mock_repo.get_user_preferences = AsyncMock(
                            return_value=[mock_pref]
                        )
                        mock_container.create_user_language_preference_repository.return_value = (
                            mock_repo
                        )

                        response = await async_client.put(
                            "/api/v1/preferences/languages",
                            json={
                                "preferences": [
                                    {
                                        "language_code": "en",
                                        "preference_type": pref_type,
                                    }
                                ]
                            },
                        )
                        assert (
                            response.status_code == 200
                        ), f"Failed for type {pref_type}"
                        data = response.json()
                        assert len(data["data"]) == 1
                        assert data["data"][0]["preference_type"] == pref_type
        finally:
            app.dependency_overrides.clear()

    async def test_update_preferences_auto_priority(
        self, async_client: AsyncClient
    ) -> None:
        """Test priority is auto-assigned when not provided."""
        # Override dependencies
        app.dependency_overrides[get_db] = get_mock_db

        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True

                # Mock repository operations
                with patch("chronovista.api.routers.preferences.container") as mock_container:
                    from chronovista.models.enums import (
                        LanguageCode,
                        LanguagePreferenceType,
                    )

                    # Create mock preferences with auto-assigned priorities
                    mock_pref1 = AsyncMock()
                    mock_pref1.language_code = LanguageCode.ENGLISH
                    mock_pref1.preference_type = LanguagePreferenceType.FLUENT
                    mock_pref1.priority = 1
                    mock_pref1.learning_goal = None

                    mock_pref2 = AsyncMock()
                    mock_pref2.language_code = LanguageCode.SPANISH
                    mock_pref2.preference_type = LanguagePreferenceType.FLUENT
                    mock_pref2.priority = 2
                    mock_pref2.learning_goal = None

                    mock_repo = AsyncMock()
                    mock_repo.delete_all_user_preferences = AsyncMock()
                    mock_repo.save_preferences = AsyncMock()
                    mock_repo.get_user_preferences = AsyncMock(
                        return_value=[mock_pref1, mock_pref2]
                    )
                    mock_container.create_user_language_preference_repository.return_value = (
                        mock_repo
                    )

                    response = await async_client.put(
                        "/api/v1/preferences/languages",
                        json={
                            "preferences": [
                                {"language_code": "en", "preference_type": "fluent"},
                                {"language_code": "es", "preference_type": "fluent"},
                            ]
                        },
                    )
                    assert response.status_code == 200
                    data = response.json()
                    assert len(data["data"]) == 2

                    # Verify priorities are assigned
                    priorities = [item["priority"] for item in data["data"]]
                    assert 1 in priorities
                    assert 2 in priorities
        finally:
            app.dependency_overrides.clear()

    async def test_update_preferences_with_learning_goal(
        self, async_client: AsyncClient
    ) -> None:
        """Test learning_goal field is accepted and stored."""
        # Override dependencies
        app.dependency_overrides[get_db] = get_mock_db

        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True

                # Mock repository operations
                with patch("chronovista.api.routers.preferences.container") as mock_container:
                    from chronovista.models.enums import (
                        LanguageCode,
                        LanguagePreferenceType,
                    )

                    # Create mock preference with learning goal
                    mock_pref = AsyncMock()
                    mock_pref.language_code = LanguageCode.SPANISH
                    mock_pref.preference_type = LanguagePreferenceType.LEARNING
                    mock_pref.priority = 1
                    mock_pref.learning_goal = "Conversational fluency"

                    mock_repo = AsyncMock()
                    mock_repo.delete_all_user_preferences = AsyncMock()
                    mock_repo.save_preferences = AsyncMock()
                    mock_repo.get_user_preferences = AsyncMock(return_value=[mock_pref])
                    mock_container.create_user_language_preference_repository.return_value = (
                        mock_repo
                    )

                    response = await async_client.put(
                        "/api/v1/preferences/languages",
                        json={
                            "preferences": [
                                {
                                    "language_code": "es",
                                    "preference_type": "learning",
                                    "learning_goal": "Conversational fluency",
                                }
                            ]
                        },
                    )
                    assert response.status_code == 200
                    data = response.json()
                    assert len(data["data"]) == 1
                    assert data["data"][0]["learning_goal"] == "Conversational fluency"
        finally:
            app.dependency_overrides.clear()

    async def test_update_preferences_duplicate_handling(
        self, async_client: AsyncClient
    ) -> None:
        """Test duplicate language codes (last one wins)."""
        # Override dependencies
        app.dependency_overrides[get_db] = get_mock_db

        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True

                # Mock repository operations
                with patch("chronovista.api.routers.preferences.container") as mock_container:
                    from chronovista.models.enums import (
                        LanguageCode,
                        LanguagePreferenceType,
                    )

                    # Create mock preference - only "learning" should be saved (last one)
                    mock_pref = AsyncMock()
                    mock_pref.language_code = LanguageCode.ENGLISH
                    mock_pref.preference_type = LanguagePreferenceType.LEARNING
                    mock_pref.priority = 1
                    mock_pref.learning_goal = None

                    mock_repo = AsyncMock()
                    mock_repo.delete_all_user_preferences = AsyncMock()
                    mock_repo.save_preferences = AsyncMock()
                    mock_repo.get_user_preferences = AsyncMock(return_value=[mock_pref])
                    mock_container.create_user_language_preference_repository.return_value = (
                        mock_repo
                    )

                    response = await async_client.put(
                        "/api/v1/preferences/languages",
                        json={
                            "preferences": [
                                {"language_code": "en", "preference_type": "fluent"},
                                {
                                    "language_code": "en",
                                    "preference_type": "learning",
                                },  # Duplicate
                            ]
                        },
                    )
                    assert response.status_code == 200
                    data = response.json()
                    # Should only have one preference (last one wins)
                    assert len(data["data"]) == 1
                    assert data["data"][0]["preference_type"] == "learning"
        finally:
            app.dependency_overrides.clear()

    async def test_update_preferences_multiple_types(
        self, async_client: AsyncClient
    ) -> None:
        """Test updating with multiple preference types."""
        # Override dependencies
        app.dependency_overrides[get_db] = get_mock_db

        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True

                # Mock repository operations
                with patch("chronovista.api.routers.preferences.container") as mock_container:
                    from chronovista.models.enums import (
                        LanguageCode,
                        LanguagePreferenceType,
                    )

                    # Create mock preferences
                    mock_pref1 = AsyncMock()
                    mock_pref1.language_code = LanguageCode.ENGLISH
                    mock_pref1.preference_type = LanguagePreferenceType.FLUENT
                    mock_pref1.priority = 1
                    mock_pref1.learning_goal = None

                    mock_pref2 = AsyncMock()
                    mock_pref2.language_code = LanguageCode.SPANISH
                    mock_pref2.preference_type = LanguagePreferenceType.LEARNING
                    mock_pref2.priority = 1
                    mock_pref2.learning_goal = "Travel conversations"

                    mock_pref3 = AsyncMock()
                    mock_pref3.language_code = LanguageCode.FRENCH
                    mock_pref3.preference_type = LanguagePreferenceType.CURIOUS
                    mock_pref3.priority = 1
                    mock_pref3.learning_goal = None

                    mock_repo = AsyncMock()
                    mock_repo.delete_all_user_preferences = AsyncMock()
                    mock_repo.save_preferences = AsyncMock()
                    mock_repo.get_user_preferences = AsyncMock(
                        return_value=[mock_pref1, mock_pref2, mock_pref3]
                    )
                    mock_container.create_user_language_preference_repository.return_value = (
                        mock_repo
                    )

                    response = await async_client.put(
                        "/api/v1/preferences/languages",
                        json={
                            "preferences": [
                                {"language_code": "en", "preference_type": "fluent"},
                                {
                                    "language_code": "es",
                                    "preference_type": "learning",
                                    "learning_goal": "Travel conversations",
                                },
                                {"language_code": "fr", "preference_type": "curious"},
                            ]
                        },
                    )
                    assert response.status_code == 200
                    data = response.json()
                    assert len(data["data"]) == 3

                    # Verify all preference types are present
                    pref_types = {item["preference_type"] for item in data["data"]}
                    assert pref_types == {"fluent", "learning", "curious"}
        finally:
            app.dependency_overrides.clear()

    async def test_update_preferences_with_explicit_priorities(
        self, async_client: AsyncClient
    ) -> None:
        """Test updating with explicit priority values."""
        # Override dependencies
        app.dependency_overrides[get_db] = get_mock_db

        try:
            with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
                mock_oauth.is_authenticated.return_value = True

                # Mock repository operations
                with patch("chronovista.api.routers.preferences.container") as mock_container:
                    from chronovista.models.enums import (
                        LanguageCode,
                        LanguagePreferenceType,
                    )

                    # Create mock preferences with explicit priorities
                    mock_pref1 = AsyncMock()
                    mock_pref1.language_code = LanguageCode.ENGLISH
                    mock_pref1.preference_type = LanguagePreferenceType.FLUENT
                    mock_pref1.priority = 2
                    mock_pref1.learning_goal = None

                    mock_pref2 = AsyncMock()
                    mock_pref2.language_code = LanguageCode.SPANISH
                    mock_pref2.preference_type = LanguagePreferenceType.FLUENT
                    mock_pref2.priority = 1
                    mock_pref2.learning_goal = None

                    mock_repo = AsyncMock()
                    mock_repo.delete_all_user_preferences = AsyncMock()
                    mock_repo.save_preferences = AsyncMock()
                    mock_repo.get_user_preferences = AsyncMock(
                        return_value=[mock_pref2, mock_pref1]
                    )  # Ordered by priority
                    mock_container.create_user_language_preference_repository.return_value = (
                        mock_repo
                    )

                    response = await async_client.put(
                        "/api/v1/preferences/languages",
                        json={
                            "preferences": [
                                {
                                    "language_code": "en",
                                    "preference_type": "fluent",
                                    "priority": 2,
                                },
                                {
                                    "language_code": "es",
                                    "preference_type": "fluent",
                                    "priority": 1,
                                },
                            ]
                        },
                    )
                    assert response.status_code == 200
                    data = response.json()
                    assert len(data["data"]) == 2

                    # Verify priorities are respected (Spanish has higher priority)
                    assert data["data"][0]["priority"] == 1
                    assert data["data"][0]["language_code"] == "es"
                    assert data["data"][1]["priority"] == 2
                    assert data["data"][1]["language_code"] == "en"
        finally:
            app.dependency_overrides.clear()

    async def test_update_preferences_invalid_priority(
        self, async_client: AsyncClient
    ) -> None:
        """Test validation rejects invalid priority values (< 1)."""
        with patch("chronovista.api.deps.youtube_oauth") as mock_oauth:
            mock_oauth.is_authenticated.return_value = True

            response = await async_client.put(
                "/api/v1/preferences/languages",
                json={
                    "preferences": [
                        {
                            "language_code": "en",
                            "preference_type": "fluent",
                            "priority": 0,  # Invalid: must be >= 1
                        }
                    ]
                },
            )
            # Pydantic validation should reject this
            assert response.status_code == 422
