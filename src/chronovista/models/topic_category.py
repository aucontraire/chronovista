"""
Topic category models.

Defines Pydantic models for YouTube topic classification system with hierarchical
structure validation and serialization support.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .enums import TopicType
from .youtube_types import TopicId


class TopicCategoryBase(BaseModel):
    """Base model for topic categories with dynamic resolution support."""

    topic_id: TopicId = Field(..., description="Unique topic identifier (validated)")
    category_name: str = Field(
        ..., min_length=1, max_length=255, description="Human-readable topic name"
    )
    parent_topic_id: Optional[TopicId] = Field(
        default=None,
        description="Parent topic ID for hierarchical structure (validated)",
    )
    topic_type: TopicType = Field(
        default=TopicType.YOUTUBE, description="Type of topic: youtube (official) or custom"
    )

    # Dynamic topic resolution fields (Option 4 implementation)
    wikipedia_url: Optional[str] = Field(
        default=None,
        max_length=500,
        description="Full Wikipedia URL from YouTube API",
    )
    normalized_name: Optional[str] = Field(
        default=None,
        max_length=255,
        description="Lowercase, no underscores for matching",
    )
    source: str = Field(
        default="seeded",
        description="Topic origin: 'seeded' or 'dynamic'",
    )

    # topic_id validation is now handled by TopicId type

    @field_validator("category_name")
    @classmethod
    def validate_category_name(cls, v: str) -> str:
        """Validate category name."""
        if not v or not v.strip():
            raise ValueError("Category name cannot be empty")

        name = v.strip()
        if len(name) > 255:
            raise ValueError("Category name cannot exceed 255 characters")

        return name

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        """Validate source field."""
        valid_sources = {"seeded", "dynamic"}
        if v not in valid_sources:
            raise ValueError(f"Source must be one of: {valid_sources}")
        return v

    # parent_topic_id validation is now handled by Optional[TopicId] type

    model_config = ConfigDict(
        validate_assignment=True,
    )


class TopicCategoryCreate(TopicCategoryBase):
    """Model for creating topic categories."""

    def model_post_init(self, __context: Any) -> None:
        """Validate hierarchy constraints after model creation."""
        # Prevent self-reference
        if self.parent_topic_id == self.topic_id:
            raise ValueError("Topic cannot be its own parent")


class TopicCategoryUpdate(BaseModel):
    """Model for updating topic categories."""

    category_name: Optional[str] = Field(None, min_length=1, max_length=255)
    parent_topic_id: Optional[TopicId] = Field(
        None, description="Parent topic ID (validated)"
    )
    topic_type: Optional[TopicType] = None

    @field_validator("category_name")
    @classmethod
    def validate_category_name(cls, v: Optional[str]) -> Optional[str]:
        """Validate category name."""
        if v is None:
            return v

        if not v or not v.strip():
            raise ValueError("Category name cannot be empty")

        name = v.strip()
        if len(name) > 255:
            raise ValueError("Category name cannot exceed 255 characters")

        return name

    # parent_topic_id validation is now handled by Optional[TopicId] type

    model_config = ConfigDict(
        validate_assignment=True,
    )


class TopicCategory(TopicCategoryBase):
    """Full topic category model with timestamps."""

    created_at: datetime = Field(..., description="When the topic was created")

    model_config = ConfigDict(
        from_attributes=True,  # Enable ORM mode for SQLAlchemy compatibility
        validate_assignment=True,
    )


class TopicCategorySearchFilters(BaseModel):
    """Filters for searching topic categories."""

    topic_ids: Optional[List[TopicId]] = Field(
        default=None, description="Filter by specific topic IDs (validated)"
    )
    category_name_query: Optional[str] = Field(
        default=None, min_length=1, description="Search in category names"
    )
    parent_topic_ids: Optional[List[TopicId]] = Field(
        default=None, description="Filter by parent topic IDs (validated)"
    )
    topic_types: Optional[List[TopicType]] = Field(
        default=None, description="Filter by topic types"
    )
    is_root_topic: Optional[bool] = Field(
        default=None, description="Filter for root topics (no parent)"
    )
    has_children: Optional[bool] = Field(
        default=None, description="Filter topics that have child topics"
    )
    max_depth: Optional[int] = Field(
        default=None, ge=0, description="Maximum hierarchy depth"
    )
    created_after: Optional[datetime] = Field(
        default=None, description="Filter by creation date"
    )
    created_before: Optional[datetime] = Field(
        default=None, description="Filter by creation date"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )


class TopicCategoryStatistics(BaseModel):
    """Topic category statistics."""

    total_topics: int = Field(..., description="Total number of topics")
    root_topics: int = Field(..., description="Number of root topics")
    max_hierarchy_depth: int = Field(..., description="Maximum hierarchy depth")
    avg_children_per_topic: float = Field(..., description="Average children per topic")
    topic_type_distribution: dict[TopicType, int] = Field(
        default_factory=dict, description="Distribution by topic type"
    )
    most_popular_topics: List[tuple[str, int]] = Field(
        default_factory=list, description="Most referenced topics with usage counts"
    )
    hierarchy_distribution: dict[int, int] = Field(
        default_factory=dict, description="Number of topics at each hierarchy level"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )


class TopicCategoryHierarchy(BaseModel):
    """Hierarchical representation of topic categories."""

    topic_id: TopicId = Field(..., description="Topic identifier (validated)")
    category_name: str = Field(..., description="Topic name")
    topic_type: TopicType = Field(..., description="Topic type")
    level: int = Field(..., ge=0, description="Hierarchy level (0 = root)")
    children: List["TopicCategoryHierarchy"] = Field(
        default_factory=list, description="Child topics"
    )
    path: List[str] = Field(
        default_factory=list, description="Path from root to this topic"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )


class TopicCategoryAnalytics(BaseModel):
    """Advanced topic category analytics."""

    topic_trends: dict[str, List[int]] = Field(
        default_factory=dict, description="Topic usage trends over time"
    )
    topic_relationships: dict[str, List[str]] = Field(
        default_factory=dict, description="Related topics mapping"
    )
    semantic_similarity: dict[str, float] = Field(
        default_factory=dict, description="Semantic similarity scores between topics"
    )
    content_classification: dict[str, dict[str, float]] = Field(
        default_factory=dict, description="Content classification confidence scores"
    )

    model_config = ConfigDict(
        validate_assignment=True,
    )
