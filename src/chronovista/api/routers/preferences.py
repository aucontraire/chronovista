"""Language preferences endpoints."""

from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.api.deps import get_db, require_auth
from chronovista.api.schemas.preferences import (
    LanguagePreferenceItem,
    LanguagePreferencesResponse,
    LanguagePreferencesUpdateRequest,
    LanguagePreferenceUpdate,
)
from chronovista.container import container
from chronovista.exceptions import BadRequestError
from chronovista.models.enums import LanguageCode, LanguagePreferenceType
from chronovista.models.user_language_preference import UserLanguagePreferenceCreate


router = APIRouter(dependencies=[Depends(require_auth)])

# Default user_id for single-user app
DEFAULT_USER_ID = "default_user"


def validate_language_code(code: str) -> bool:
    """Validate language code against LanguageCode enum."""
    try:
        LanguageCode(code)
        return True
    except ValueError:
        return False


def validate_preference_type(pref_type: str) -> bool:
    """Validate preference type against LanguagePreferenceType enum."""
    try:
        LanguagePreferenceType(pref_type)
        return True
    except ValueError:
        return False


@router.get("/preferences/languages", response_model=LanguagePreferencesResponse)
async def get_language_preferences(
    session: AsyncSession = Depends(get_db),
) -> LanguagePreferencesResponse:
    """
    Get current language preferences.

    Returns list of language preferences ordered by priority.
    Empty list if no preferences configured.
    """
    repo = container.create_user_language_preference_repository()
    prefs = await repo.get_user_preferences(session, DEFAULT_USER_ID)

    items = [
        LanguagePreferenceItem(
            language_code=p.language_code,
            preference_type=p.preference_type,
            priority=p.priority,
            learning_goal=p.learning_goal,
        )
        for p in prefs
    ]

    return LanguagePreferencesResponse(data=items)


@router.put("/preferences/languages", response_model=LanguagePreferencesResponse)
async def update_language_preferences(
    request: LanguagePreferencesUpdateRequest,
    session: AsyncSession = Depends(get_db),
) -> LanguagePreferencesResponse:
    """
    Update language preferences.

    Replaces all preferences with the provided list.
    Priority is auto-assigned if not provided.
    """
    # Validate all language codes
    invalid_codes = [
        p.language_code
        for p in request.preferences
        if not validate_language_code(p.language_code)
    ]
    if invalid_codes:
        raise BadRequestError(
            message=f"Invalid language codes: {', '.join(invalid_codes)}. "
            "See LanguageCode enum for valid codes.",
            details={"field": "language_code", "invalid_values": invalid_codes},
        )

    # Validate all preference types
    invalid_types = [
        p.preference_type
        for p in request.preferences
        if not validate_preference_type(p.preference_type)
    ]
    if invalid_types:
        raise BadRequestError(
            message=f"Invalid preference types: {', '.join(invalid_types)}. "
            "Valid types: fluent, learning, curious, exclude.",
            details={"field": "preference_type", "invalid_values": invalid_types},
        )

    # Handle duplicates - last occurrence wins
    seen: dict[str, LanguagePreferenceUpdate] = {}
    for pref in request.preferences:
        seen[pref.language_code] = pref
    unique_prefs = list(seen.values())

    # Auto-assign priorities if not provided
    # Group by preference type to assign priorities within each group
    by_type: dict[str, list[LanguagePreferenceUpdate]] = {}
    for pref in unique_prefs:
        if pref.preference_type not in by_type:
            by_type[pref.preference_type] = []
        by_type[pref.preference_type].append(pref)

    # Create preference objects with auto-assigned priorities
    creates: List[UserLanguagePreferenceCreate] = []
    for pref_type, prefs_in_type in by_type.items():
        # Sort by provided priority (None last), then by order
        prefs_in_type.sort(key=lambda p: (p.priority is None, p.priority or 0))

        for idx, pref in enumerate(prefs_in_type):
            priority = pref.priority if pref.priority is not None else idx + 1
            creates.append(
                UserLanguagePreferenceCreate(
                    user_id=DEFAULT_USER_ID,
                    language_code=LanguageCode(pref.language_code),
                    preference_type=LanguagePreferenceType(pref.preference_type),
                    priority=priority,
                    learning_goal=pref.learning_goal,
                    auto_download_transcripts=False,
                )
            )

    # Save preferences (replaces existing)
    repo = container.create_user_language_preference_repository()

    # Delete existing preferences
    await repo.delete_all_user_preferences(session, DEFAULT_USER_ID)

    # Create new preferences
    if creates:
        await repo.save_preferences(session, DEFAULT_USER_ID, creates)

    await session.commit()

    # Return updated preferences
    return await get_language_preferences(session)
