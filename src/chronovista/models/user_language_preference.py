"""
User language preference models.

Defines Pydantic models for user language preferences with validation
and serialization support.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import LanguageCode, LanguagePreferenceType
from .youtube_types import UserId


class UserLanguagePreferenceBase(BaseModel):
    """Base model for user language preferences."""

    user_id: UserId = Field(..., description="User identifier (validated)")
    language_code: Union[LanguageCode, str] = Field(
        ...,
        description="BCP-47 language code (e.g., 'en-US', 'it-IT'). Can be enum or string for regional variants.",
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

    # Note: User ID validation is now handled by UserId type

    @field_validator("language_code", mode="before")
    @classmethod
    def validate_language_code(cls, v: Any) -> Any:
        """Validate and normalize BCP-47 language code format.

        Accepts LanguageCode enum values and valid BCP-47 formatted strings.
        Regional variants not in the enum are preserved as strings.
        """
        from .transcript_source import resolve_language_code

        if v is None or v == "":
            raise ValueError("Language code cannot be empty")

        # If already a LanguageCode enum, return as-is
        if isinstance(v, LanguageCode):
            return v

        # Convert string to proper format
        if isinstance(v, str):
            # Check for whitespace-only
            if not v.strip():
                raise ValueError("Language code cannot be empty")

            # Basic BCP-47 validation
            parts = v.split("-")
            if len(parts) < 1 or len(parts) > 3:
                raise ValueError("Invalid BCP-47 language code format")

            # Language code should be 2-3 letters (not numbers)
            language = parts[0]
            if len(language) < 2 or len(language) > 3:
                raise ValueError("Language code must be 2-3 characters")
            if not language.isalpha():
                raise ValueError("Language code must contain only letters")

            # Region code (if present) should be 2-4 characters
            if len(parts) >= 2:
                region = parts[1]
                if len(region) < 1 or len(region) > 4:
                    raise ValueError("Region code must be 1-4 characters")

            # Use resolve_language_code to handle casing normalization
            return resolve_language_code(v)

        # For any other type, return as-is and let enum validation handle it
        return v

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
