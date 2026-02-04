"""Language preferences API schemas."""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from chronovista.api.schemas.responses import ApiResponse


class LanguagePreferenceItem(BaseModel):
    """Single language preference."""

    model_config = ConfigDict(strict=True)

    language_code: str  # BCP-47 code
    preference_type: str  # "fluent", "learning", "curious", "exclude"
    priority: int  # 1 = highest priority
    learning_goal: Optional[str] = None  # Goal text for learning type


class LanguagePreferencesResponse(ApiResponse[List[LanguagePreferenceItem]]):
    """Response for language preferences endpoint."""

    pass


class LanguagePreferenceUpdate(BaseModel):
    """Update a single language preference."""

    model_config = ConfigDict(strict=True)

    language_code: str
    preference_type: str  # "fluent", "learning", "curious", "exclude"
    priority: Optional[int] = Field(None, ge=1)  # Auto-assigned if not provided
    learning_goal: Optional[str] = None


class LanguagePreferencesUpdateRequest(BaseModel):
    """Request to update language preferences."""

    model_config = ConfigDict(strict=True)

    preferences: List[LanguagePreferenceUpdate]
