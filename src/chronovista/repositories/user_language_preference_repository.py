"""
User language preference repository.

Provides data access layer for user language preferences with full CRUD
operations and specialized queries for language management.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

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
