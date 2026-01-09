"""
User language preference repository.

Provides data access layer for user language preferences with full CRUD
operations and specialized queries for language management.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import UserLanguagePreference as UserLanguagePreferenceDB
from ..models.enums import LanguagePreferenceType
from ..models.user_language_preference import (
    UserLanguagePreference,
    UserLanguagePreferenceCreate,
    UserLanguagePreferenceUpdate,
)
from ..models.youtube_types import UserId
from .base import BaseSQLAlchemyRepository


class UserLanguagePreferenceRepository(
    BaseSQLAlchemyRepository[
        UserLanguagePreferenceDB,
        UserLanguagePreferenceCreate,
        UserLanguagePreferenceUpdate,
        Tuple[str, str],
    ]
):
    """Repository for user language preferences with specialized operations."""

    def __init__(self) -> None:
        """Initialize repository with UserLanguagePreference model."""
        super().__init__(UserLanguagePreferenceDB)

    async def get(
        self, session: AsyncSession, id: Tuple[str, str]
    ) -> Optional[UserLanguagePreferenceDB]:
        """
        Get user language preference by composite primary key.

        Parameters
        ----------
        session : AsyncSession
            Database session
        id : Tuple[str, str]
            Composite key (user_id, language_code)

        Returns
        -------
        Optional[UserLanguagePreferenceDB]
            User language preference if found, None otherwise
        """
        user_id, language_code = id
        result = await session.execute(
            select(UserLanguagePreferenceDB).where(
                and_(
                    UserLanguagePreferenceDB.user_id == user_id,
                    UserLanguagePreferenceDB.language_code == language_code.lower(),
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_composite_key(
        self, session: AsyncSession, user_id: UserId, language_code: str
    ) -> Optional[UserLanguagePreferenceDB]:
        """
        Get user language preference by composite primary key (convenience method).

        Parameters
        ----------
        session : AsyncSession
            Database session
        user_id : UserId
            User identifier (validated)
        language_code : str
            BCP-47 language code

        Returns
        -------
        Optional[UserLanguagePreferenceDB]
            User language preference if found, None otherwise
        """
        return await self.get(session, (user_id, language_code))

    async def exists(self, session: AsyncSession, id: Tuple[str, str]) -> bool:
        """
        Check if user language preference exists.

        Parameters
        ----------
        session : AsyncSession
            Database session
        id : Tuple[str, str]
            Composite key (user_id, language_code)

        Returns
        -------
        bool
            True if preference exists, False otherwise
        """
        user_id, language_code = id
        result = await session.execute(
            select(UserLanguagePreferenceDB.user_id).where(
                and_(
                    UserLanguagePreferenceDB.user_id == user_id,
                    UserLanguagePreferenceDB.language_code == language_code.lower(),
                )
            )
        )
        return result.first() is not None

    async def exists_by_composite_key(
        self, session: AsyncSession, user_id: UserId, language_code: str
    ) -> bool:
        """
        Check if user language preference exists (convenience method).

        Parameters
        ----------
        session : AsyncSession
            Database session
        user_id : UserId
            User identifier (validated)
        language_code : str
            BCP-47 language code

        Returns
        -------
        bool
            True if preference exists, False otherwise
        """
        return await self.exists(session, (user_id, language_code))

    async def get_user_preferences(
        self, session: AsyncSession, user_id: UserId
    ) -> List[UserLanguagePreferenceDB]:
        """
        Get all language preferences for a user, ordered by priority.

        Parameters
        ----------
        session : AsyncSession
            Database session
        user_id : UserId
            User identifier (validated)

        Returns
        -------
        List[UserLanguagePreferenceDB]
            List of user language preferences ordered by priority
        """
        result = await session.execute(
            select(UserLanguagePreferenceDB)
            .where(UserLanguagePreferenceDB.user_id == user_id)
            .order_by(UserLanguagePreferenceDB.priority.asc())
        )
        return list(result.scalars().all())

    async def get_preferences_by_type(
        self,
        session: AsyncSession,
        user_id: UserId,
        preference_type: LanguagePreferenceType,
    ) -> List[UserLanguagePreferenceDB]:
        """
        Get user preferences filtered by type.

        Parameters
        ----------
        session : AsyncSession
            Database session
        user_id : UserId
            User identifier (validated)
        preference_type : LanguagePreferenceType
            Type of language preference to filter by

        Returns
        -------
        List[UserLanguagePreferenceDB]
            List of preferences of the specified type, ordered by priority
        """
        result = await session.execute(
            select(UserLanguagePreferenceDB)
            .where(
                and_(
                    UserLanguagePreferenceDB.user_id == user_id,
                    UserLanguagePreferenceDB.preference_type == preference_type.value,
                )
            )
            .order_by(UserLanguagePreferenceDB.priority.asc())
        )
        return list(result.scalars().all())

    async def get_auto_download_languages(
        self, session: AsyncSession, user_id: UserId
    ) -> List[str]:
        """
        Get language codes where auto-download is enabled.

        Parameters
        ----------
        session : AsyncSession
            Database session
        user_id : UserId
            User identifier (validated)

        Returns
        -------
        List[str]
            List of language codes with auto-download enabled
        """
        result = await session.execute(
            select(UserLanguagePreferenceDB.language_code)
            .where(
                and_(
                    UserLanguagePreferenceDB.user_id == user_id,
                    UserLanguagePreferenceDB.auto_download_transcripts == True,
                )
            )
            .order_by(UserLanguagePreferenceDB.priority.asc())
        )
        return [lang for lang in result.scalars().all()]

    async def save_preferences(
        self,
        session: AsyncSession,
        user_id: UserId,
        preferences: List[UserLanguagePreferenceCreate],
    ) -> List[UserLanguagePreferenceDB]:
        """
        Save multiple user language preferences.

        This method handles bulk insertion and updates existing preferences.

        Parameters
        ----------
        session : AsyncSession
            Database session
        user_id : UserId
            User identifier (validated)
        preferences : List[UserLanguagePreferenceCreate]
            List of preferences to save

        Returns
        -------
        List[UserLanguagePreferenceDB]
            List of saved preferences
        """
        saved_preferences = []

        for pref in preferences:
            # Check if preference already exists
            existing = await self.get_by_composite_key(
                session, user_id, pref.language_code
            )

            if existing:
                # Update existing preference
                updated = await self.update(
                    session,
                    db_obj=existing,
                    obj_in=UserLanguagePreferenceUpdate(
                        preference_type=pref.preference_type,
                        priority=pref.priority,
                        auto_download_transcripts=pref.auto_download_transcripts,
                        learning_goal=pref.learning_goal,
                    ),
                )
                saved_preferences.append(updated)
            else:
                # Create new preference
                created = await self.create(session, obj_in=pref)
                saved_preferences.append(created)

        return saved_preferences

    async def update_priority(
        self,
        session: AsyncSession,
        user_id: UserId,
        language_code: str,
        new_priority: int,
    ) -> Optional[UserLanguagePreferenceDB]:
        """
        Update the priority of a specific language preference.

        Parameters
        ----------
        session : AsyncSession
            Database session
        user_id : UserId
            User identifier (validated)
        language_code : str
            BCP-47 language code
        new_priority : int
            New priority value (1 = highest)

        Returns
        -------
        Optional[UserLanguagePreferenceDB]
            Updated preference if found, None otherwise
        """
        preference = await self.get_by_composite_key(session, user_id, language_code)
        if not preference:
            return None

        preference.priority = new_priority
        session.add(preference)
        await session.flush()
        await session.refresh(preference)
        return preference

    async def delete_user_preference(
        self, session: AsyncSession, user_id: UserId, language_code: str
    ) -> bool:
        """
        Delete a specific user language preference.

        Parameters
        ----------
        session : AsyncSession
            Database session
        user_id : UserId
            User identifier (validated)
        language_code : str
            BCP-47 language code

        Returns
        -------
        bool
            True if preference was deleted, False if not found
        """
        result = await session.execute(
            delete(UserLanguagePreferenceDB).where(
                and_(
                    UserLanguagePreferenceDB.user_id == user_id,
                    UserLanguagePreferenceDB.language_code == language_code.lower(),
                )
            )
        )
        return result.rowcount > 0

    async def delete_all_user_preferences(
        self, session: AsyncSession, user_id: UserId
    ) -> int:
        """
        Delete all language preferences for a user.

        Parameters
        ----------
        session : AsyncSession
            Database session
        user_id : UserId
            User identifier (validated)

        Returns
        -------
        int
            Number of preferences deleted
        """
        result = await session.execute(
            delete(UserLanguagePreferenceDB).where(
                UserLanguagePreferenceDB.user_id == user_id
            )
        )
        return result.rowcount

    async def get_language_statistics(
        self, session: AsyncSession, user_id: UserId
    ) -> dict[LanguagePreferenceType, int]:
        """
        Get statistics about user's language preferences by type.

        Parameters
        ----------
        session : AsyncSession
            Database session
        user_id : UserId
            User identifier (validated)

        Returns
        -------
        dict[LanguagePreferenceType, int]
            Count of preferences by type
        """
        from sqlalchemy import func

        result = await session.execute(
            select(
                UserLanguagePreferenceDB.preference_type,
                func.count(UserLanguagePreferenceDB.language_code).label("count"),
            )
            .where(UserLanguagePreferenceDB.user_id == user_id)
            .group_by(UserLanguagePreferenceDB.preference_type)
        )

        stats = {}
        for pref_type, count in result:
            # Convert string back to enum
            try:
                enum_type = LanguagePreferenceType(pref_type)
                stats[enum_type] = count
            except ValueError:
                # Skip invalid enum values
                continue

        return stats

    # Video Localization Integration Methods

    async def get_user_videos_with_preferred_localizations(
        self,
        session: AsyncSession,
        user_id: str,
        video_ids: List[str],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get videos with localizations in user's preferred languages.

        Parameters
        ----------
        session : AsyncSession
            Database session
        user_id : str
            User ID to get preferences for
        video_ids : List[str]
            List of video IDs to process

        Returns
        -------
        Dict[str, Dict[str, Any]]
            Mapping of video_id to video data with preferred localization
        """
        from .video_repository import VideoRepository

        if not video_ids:
            return {}

        # Get user's language preferences in priority order
        preferences = await self.get_user_preferences(session, user_id)

        # Build preferred languages list (fluent first, then learning, then curious)
        preferred_languages = []
        for pref in sorted(preferences, key=lambda x: x.priority or 999):
            if pref.preference_type in (
                LanguagePreferenceType.FLUENT,
                LanguagePreferenceType.LEARNING,
                LanguagePreferenceType.CURIOUS,
            ):
                preferred_languages.append(pref.language_code)

        if not preferred_languages:
            return {}

        # Get videos with preferred localizations
        video_repo = VideoRepository()
        return await video_repo.get_videos_with_preferred_localizations(
            session, video_ids, preferred_languages
        )

    async def get_recommended_localization_targets(
        self,
        session: AsyncSession,
        user_id: str,
        limit: int = 20,
    ) -> Dict[str, List[str]]:
        """
        Get recommended localization targets based on user preferences.

        Parameters
        ----------
        session : AsyncSession
            Database session
        user_id : str
            User ID to get recommendations for
        limit : int
            Maximum number of videos to check

        Returns
        -------
        Dict[str, List[str]]
            Mapping of video_id to list of recommended localization languages
        """
        from .video_repository import VideoRepository

        # Get user's learning and curious languages
        preferences = await self.get_user_preferences(session, user_id)

        learning_languages = [
            pref.language_code
            for pref in preferences
            if pref.preference_type == LanguagePreferenceType.LEARNING
        ]
        curious_languages = [
            pref.language_code
            for pref in preferences
            if pref.preference_type == LanguagePreferenceType.CURIOUS
        ]

        target_languages = learning_languages + curious_languages
        if not target_languages:
            return {}

        # Get videos missing localizations in target languages
        video_repo = VideoRepository()
        missing_localizations = await video_repo.get_videos_missing_localizations(
            session, target_languages, limit=limit
        )

        # Extract just the missing languages for each video
        return {
            video_id: data["missing_languages"]
            for video_id, data in missing_localizations.items()
        }

    async def get_user_localization_coverage(
        self,
        session: AsyncSession,
        user_id: str,
    ) -> Dict[str, Any]:
        """
        Get localization coverage for user's preferred languages.

        Parameters
        ----------
        session : AsyncSession
            Database session
        user_id : str
            User ID to analyze

        Returns
        -------
        Dict[str, Any]
            Localization coverage analysis for user's languages
        """
        from .video_localization_repository import VideoLocalizationRepository

        # Get user's language preferences
        preferences = await self.get_user_preferences(session, user_id)

        user_languages: Dict[str, Any] = {
            pref.language_code: pref.preference_type for pref in preferences
        }

        if not user_languages:
            return {
                "user_languages": {},
                "coverage": {},
                "total_videos": 0,
                "localized_videos": 0,
                "coverage_percentage": 0.0,
            }

        # Get overall language coverage
        localization_repo = VideoLocalizationRepository()
        language_coverage = await localization_repo.get_language_coverage(session)

        # Filter coverage for user's languages
        user_coverage = {
            lang: language_coverage.get(lang, 0) for lang in user_languages.keys()
        }

        # Calculate summary statistics
        total_videos_with_localizations = sum(language_coverage.values())
        user_localized_videos = sum(user_coverage.values())

        coverage_percentage = (
            (user_localized_videos / total_videos_with_localizations * 100)
            if total_videos_with_localizations > 0
            else 0.0
        )

        return {
            "user_languages": user_languages,
            "coverage": user_coverage,
            "total_videos_with_localizations": total_videos_with_localizations,
            "user_localized_videos": user_localized_videos,
            "coverage_percentage": coverage_percentage,
            "language_breakdown": {
                lang: {
                    "preference_type": user_languages[lang],
                    "video_count": user_coverage[lang],
                    "percentage_of_user_content": (
                        (user_coverage[lang] / user_localized_videos * 100)
                        if user_localized_videos > 0
                        else 0.0
                    ),
                }
                for lang in user_languages.keys()
            },
        }
