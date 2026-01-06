"""
Video category models.

Defines Pydantic models for YouTube video categories with validation
and serialization support.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VideoCategoryBase(BaseModel):
    """Base model for video categories."""

    category_id: str = Field(
        ...,
        min_length=1,
        max_length=10,
        description="YouTube category ID (numeric string, 1-10 chars)",
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Human-readable category name",
    )
    assignable: bool = Field(
        default=True,
        description="Whether videos can be assigned to this category",
    )

    @field_validator("category_id")
    @classmethod
    def validate_category_id(cls, v: str) -> str:
        """Validate category ID is a numeric string."""
        if not v or not v.strip():
            raise ValueError("Category ID cannot be empty")

        category_id = v.strip()
        if len(category_id) < 1 or len(category_id) > 10:
            raise ValueError("Category ID must be between 1-10 characters")

        if not category_id.isdigit():
            raise ValueError("Category ID must be a numeric string")

        return category_id

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Validate category name is not empty."""
        if not v or not v.strip():
            raise ValueError("Category name cannot be empty")

        name = v.strip()
        if len(name) > 100:
            raise ValueError("Category name cannot exceed 100 characters")

        return name

    model_config = ConfigDict(
        validate_assignment=True,
    )


class VideoCategoryCreate(VideoCategoryBase):
    """Model for creating video categories."""

    pass


class VideoCategoryUpdate(BaseModel):
    """Model for updating video categories."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    assignable: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate category name if provided."""
        if v is None:
            return v

        if not v or not v.strip():
            raise ValueError("Category name cannot be empty")

        name = v.strip()
        if len(name) > 100:
            raise ValueError("Category name cannot exceed 100 characters")

        return name

    model_config = ConfigDict(
        validate_assignment=True,
    )


class VideoCategory(VideoCategoryBase):
    """Full video category model with timestamps."""

    created_at: datetime = Field(..., description="When the category was created")
    updated_at: datetime = Field(..., description="When the category was last updated")

    model_config = ConfigDict(
        from_attributes=True,  # Enable ORM mode for SQLAlchemy compatibility
        validate_assignment=True,
    )
