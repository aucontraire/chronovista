"""
User language preference models.

Defines Pydantic models for user language preferences with validation
and serialization support.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import LanguageCode, LanguagePreferenceType
from .youtube_types import UserId


class UserLanguagePreferenceBase(BaseModel):
    """Base model for user language preferences."""

    user_id: UserId = Field(..., description="User identifier (validated)")
    language_code: LanguageCode = Field(
        ...,
        description="BCP-47 language code (e.g., 'en-US', 'it-IT')",
    )
    preference_type: LanguagePreferenceType = Field(
        ..., description="Type of language preference"
    )
    priority: int = Field(
        ..., ge=1, description="Priority order for this language (1 = highest)"
    )
    auto_download_transcripts: bool = Field(
        default=False,
        description="Whether to automatically download transcripts in this language",
    )
    learning_goal: Optional[str] = Field(
        default=None, description="Optional learning goal description"
    )

    # Note: Language validation is now handled by LanguageCode enum
    # Note: User ID validation is now handled by UserId type

    model_config = ConfigDict(
        use_enum_values=True,
        validate_assignment=True,
    )


class UserLanguagePreferenceCreate(UserLanguagePreferenceBase):
    """Model for creating user language preferences."""

    pass


class UserLanguagePreferenceUpdate(BaseModel):
    """Model for updating user language preferences."""

    preference_type: Optional[LanguagePreferenceType] = None
    priority: Optional[int] = Field(None, ge=1)
    auto_download_transcripts: Optional[bool] = None
    learning_goal: Optional[str] = None

    model_config = ConfigDict(
        use_enum_values=True,
        validate_assignment=True,
    )


class UserLanguagePreference(UserLanguagePreferenceBase):
    """Full user language preference model with timestamps."""

    created_at: datetime = Field(..., description="When the preference was created")

    model_config = ConfigDict(
        from_attributes=True,  # Enable ORM mode for SQLAlchemy compatibility
        use_enum_values=True,
        validate_assignment=True,
    )
