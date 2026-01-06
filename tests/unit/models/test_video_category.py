"""
Tests for video category Pydantic models.

Tests validation, keyword arguments, serialization, and model methods
for all VideoCategory model variants.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from chronovista.models.video_category import (
    VideoCategory,
    VideoCategoryBase,
    VideoCategoryCreate,
    VideoCategoryUpdate,
)


class TestVideoCategoryBase:
    """Test VideoCategoryBase model validation."""

    def test_create_valid_video_category_base(self):
        """Test creating valid VideoCategoryBase with all fields."""
        category = VideoCategoryBase(
            category_id="10",
            name="Music",
            assignable=True,
        )

        assert category.category_id == "10"
        assert category.name == "Music"
        assert category.assignable is True

    def test_create_video_category_minimal(self):
        """Test creating VideoCategoryBase with minimal required fields."""
        category = VideoCategoryBase(
            category_id="1",
            name="Film & Animation",
        )

        assert category.category_id == "1"
        assert category.name == "Film & Animation"
        assert category.assignable is True  # Default value

    def test_category_id_validation_numeric(self):
        """Test category_id must be numeric string."""
        # Valid numeric strings
        valid_ids = ["1", "10", "20", "99", "123", "9999999999"]
        for category_id in valid_ids:
            category = VideoCategoryBase(category_id=category_id, name="Test")
            assert category.category_id == category_id

    def test_category_id_validation_non_numeric_rejected(self):
        """Test category_id validation rejects non-numeric strings."""
        invalid_ids = [
            "abc",  # Letters
            "12a",  # Mixed
            "1.5",  # Decimal
            "1-2",  # Hyphen
            "1 2",  # Space
            "",     # Empty after strip
            "   ",  # Only whitespace
        ]

        for invalid_id in invalid_ids:
            with pytest.raises(ValidationError):
                VideoCategoryBase(category_id=invalid_id, name="Test")

    def test_category_id_validation_empty_rejected(self):
        """Test category_id validation rejects empty strings."""
        with pytest.raises(ValidationError):
            VideoCategoryBase(category_id="", name="Test")

    def test_category_id_validation_length_constraints(self):
        """Test category_id length constraints (1-10 chars)."""
        # Valid lengths
        assert VideoCategoryBase(category_id="1", name="Test").category_id == "1"
        assert VideoCategoryBase(category_id="1234567890", name="Test").category_id == "1234567890"

        # Too long (>10 chars)
        with pytest.raises(ValidationError):
            VideoCategoryBase(category_id="12345678901", name="Test")

    def test_category_id_strips_whitespace(self):
        """Test category_id strips leading/trailing whitespace."""
        category = VideoCategoryBase(category_id="  10  ", name="Test")
        assert category.category_id == "10"

    def test_name_validation_non_empty(self):
        """Test name validation requires non-empty value."""
        # Valid names
        category = VideoCategoryBase(category_id="1", name="Music")
        assert category.name == "Music"

        # Empty name rejected
        with pytest.raises(ValidationError):
            VideoCategoryBase(category_id="1", name="")

        # Whitespace-only name rejected
        with pytest.raises(ValidationError):
            VideoCategoryBase(category_id="1", name="   ")

    def test_name_validation_max_length(self):
        """Test name validation enforces max length of 100 characters."""
        # Valid length (exactly 100 chars)
        valid_name = "x" * 100
        category = VideoCategoryBase(category_id="1", name=valid_name)
        assert category.name == valid_name
        assert len(category.name) == 100

        # Too long (>100 chars)
        invalid_name = "x" * 101
        with pytest.raises(ValidationError):
            VideoCategoryBase(category_id="1", name=invalid_name)

    def test_name_strips_whitespace(self):
        """Test name strips leading/trailing whitespace."""
        category = VideoCategoryBase(category_id="1", name="  Music  ")
        assert category.name == "Music"

    def test_assignable_default_value(self):
        """Test assignable defaults to True."""
        category = VideoCategoryBase(category_id="1", name="Test")
        assert category.assignable is True

    def test_assignable_explicit_false(self):
        """Test assignable can be set to False."""
        category = VideoCategoryBase(category_id="1", name="Test", assignable=False)
        assert category.assignable is False

    def test_model_dump_functionality(self):
        """Test model_dump() method for serialization."""
        category = VideoCategoryBase(
            category_id="10",
            name="Music",
            assignable=True,
        )

        data = category.model_dump()
        expected = {
            "category_id": "10",
            "name": "Music",
            "assignable": True,
        }

        assert data == expected

    def test_model_validate_functionality(self):
        """Test model_validate() method for deserialization."""
        data = {
            "category_id": "20",
            "name": "Gaming",
            "assignable": True,
        }

        category = VideoCategoryBase.model_validate(data)

        assert category.category_id == "20"
        assert category.name == "Gaming"
        assert category.assignable is True


class TestVideoCategoryCreate:
    """Test VideoCategoryCreate model validation."""

    def test_create_valid_video_category_create(self):
        """Test creating valid VideoCategoryCreate with keyword arguments."""
        category = VideoCategoryCreate(
            category_id="10",
            name="Music",
            assignable=True,
        )

        assert category.category_id == "10"
        assert category.name == "Music"
        assert category.assignable is True

    def test_inherits_base_validation(self):
        """Test that VideoCategoryCreate inherits base validation."""
        # Should reject empty category_id
        with pytest.raises(ValidationError):
            VideoCategoryCreate(category_id="", name="Test")

        # Should reject non-numeric category_id
        with pytest.raises(ValidationError):
            VideoCategoryCreate(category_id="abc", name="Test")

        # Should reject empty name
        with pytest.raises(ValidationError):
            VideoCategoryCreate(category_id="1", name="")

    def test_model_is_instance_of_base(self):
        """Test that VideoCategoryCreate is instance of VideoCategoryBase."""
        category = VideoCategoryCreate(category_id="1", name="Test")
        assert isinstance(category, VideoCategoryBase)


class TestVideoCategoryUpdate:
    """Test VideoCategoryUpdate model validation."""

    def test_create_valid_video_category_update(self):
        """Test creating valid VideoCategoryUpdate with keyword arguments."""
        update = VideoCategoryUpdate(
            name="Updated Music",
            assignable=False,
        )

        assert update.name == "Updated Music"
        assert update.assignable is False

    def test_create_empty_video_category_update(self):
        """Test creating empty VideoCategoryUpdate (all fields None)."""
        update = VideoCategoryUpdate()

        assert update.name is None
        assert update.assignable is None

    def test_partial_update_name_only(self):
        """Test partial update with name only."""
        update = VideoCategoryUpdate(name="New Name")

        assert update.name == "New Name"
        assert update.assignable is None

    def test_partial_update_assignable_only(self):
        """Test partial update with assignable only."""
        update = VideoCategoryUpdate(assignable=True)

        assert update.name is None
        assert update.assignable is True

    def test_name_validation_in_update(self):
        """Test name validation in update model."""
        # Empty name rejected
        with pytest.raises(ValidationError):
            VideoCategoryUpdate(name="")

        # Whitespace-only name rejected
        with pytest.raises(ValidationError):
            VideoCategoryUpdate(name="   ")

        # Too long name rejected
        with pytest.raises(ValidationError):
            VideoCategoryUpdate(name="x" * 101)

    def test_name_strips_whitespace_in_update(self):
        """Test name strips whitespace in update."""
        update = VideoCategoryUpdate(name="  Test  ")
        assert update.name == "Test"

    def test_model_dump_excludes_none(self):
        """Test model_dump() excludes None values."""
        update = VideoCategoryUpdate(name="Test")

        data = update.model_dump(exclude_none=True)

        assert data == {"name": "Test"}
        assert "assignable" not in data

    def test_model_dump_includes_none(self):
        """Test model_dump() can include None values."""
        update = VideoCategoryUpdate(name="Test")

        data = update.model_dump()

        assert data == {"name": "Test", "assignable": None}


class TestVideoCategory:
    """Test VideoCategory full model with timestamps."""

    def test_create_valid_video_category(self):
        """Test creating valid VideoCategory with keyword arguments."""
        created_at = datetime.now(timezone.utc)
        updated_at = datetime.now(timezone.utc)

        category = VideoCategory(
            category_id="10",
            name="Music",
            assignable=True,
            created_at=created_at,
            updated_at=updated_at,
        )

        assert category.category_id == "10"
        assert category.name == "Music"
        assert category.assignable is True
        assert category.created_at == created_at
        assert category.updated_at == updated_at

    def test_from_attributes_compatibility(self):
        """Test ORM compatibility with from_attributes."""

        # Simulate SQLAlchemy model attributes
        class MockVideoCategoryDB:
            category_id = "20"
            name = "Gaming"
            assignable = True
            created_at = datetime.now(timezone.utc)
            updated_at = datetime.now(timezone.utc)

        mock_db = MockVideoCategoryDB()
        category = VideoCategory.model_validate(mock_db, from_attributes=True)

        assert category.category_id == "20"
        assert category.name == "Gaming"
        assert category.assignable is True
        assert isinstance(category.created_at, datetime)
        assert isinstance(category.updated_at, datetime)

    def test_model_is_instance_of_base(self):
        """Test that VideoCategory is instance of VideoCategoryBase."""
        created_at = datetime.now(timezone.utc)
        updated_at = datetime.now(timezone.utc)

        category = VideoCategory(
            category_id="1",
            name="Test",
            created_at=created_at,
            updated_at=updated_at,
        )

        assert isinstance(category, VideoCategoryBase)

    def test_timestamps_required(self):
        """Test that timestamps are required fields."""
        # Missing created_at
        with pytest.raises(ValidationError):
            VideoCategory(
                category_id="1",
                name="Test",
                updated_at=datetime.now(timezone.utc),
            )

        # Missing updated_at
        with pytest.raises(ValidationError):
            VideoCategory(
                category_id="1",
                name="Test",
                created_at=datetime.now(timezone.utc),
            )

    def test_model_dump_includes_timestamps(self):
        """Test model_dump() includes timestamp fields."""
        created_at = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        updated_at = datetime(2024, 1, 2, 12, 0, 0, tzinfo=timezone.utc)

        category = VideoCategory(
            category_id="10",
            name="Music",
            assignable=True,
            created_at=created_at,
            updated_at=updated_at,
        )

        data = category.model_dump()

        assert data["category_id"] == "10"
        assert data["name"] == "Music"
        assert data["assignable"] is True
        assert data["created_at"] == created_at
        assert data["updated_at"] == updated_at


class TestVideoCategoryModelInteractions:
    """Test interactions between different VideoCategory models."""

    def test_create_then_update_workflow(self):
        """Test typical create then update workflow."""
        # Create
        category_create = VideoCategoryCreate(
            category_id="10",
            name="Music",
            assignable=True,
        )

        # Simulate creation
        created_at = datetime.now(timezone.utc)
        updated_at = created_at

        category_full = VideoCategory(
            category_id=category_create.category_id,
            name=category_create.name,
            assignable=category_create.assignable,
            created_at=created_at,
            updated_at=updated_at,
        )

        # Update
        category_update = VideoCategoryUpdate(
            name="Updated Music",
            assignable=False,
        )

        # Apply update (simulated)
        updated_data = category_full.model_dump()
        update_data = category_update.model_dump(exclude_unset=True)
        updated_data.update(update_data)
        updated_data["updated_at"] = datetime.now(timezone.utc)

        category_updated = VideoCategory.model_validate(updated_data)

        assert category_updated.category_id == "10"
        assert category_updated.name == "Updated Music"
        assert category_updated.assignable is False
        assert category_updated.updated_at > category_updated.created_at

    def test_real_youtube_categories(self):
        """Test with real YouTube category data."""
        real_categories = [
            {"category_id": "1", "name": "Film & Animation", "assignable": True},
            {"category_id": "2", "name": "Autos & Vehicles", "assignable": True},
            {"category_id": "10", "name": "Music", "assignable": True},
            {"category_id": "15", "name": "Pets & Animals", "assignable": True},
            {"category_id": "20", "name": "Gaming", "assignable": True},
            {"category_id": "22", "name": "People & Blogs", "assignable": True},
            {"category_id": "23", "name": "Comedy", "assignable": True},
            {"category_id": "24", "name": "Entertainment", "assignable": True},
            {"category_id": "25", "name": "News & Politics", "assignable": True},
            {"category_id": "26", "name": "Howto & Style", "assignable": True},
            {"category_id": "27", "name": "Education", "assignable": True},
            {"category_id": "28", "name": "Science & Technology", "assignable": True},
        ]

        for category_data in real_categories:
            category = VideoCategoryBase.model_validate(category_data)
            assert category.category_id == category_data["category_id"]
            assert category.name == category_data["name"]
            assert category.assignable == category_data["assignable"]

    def test_edge_cases(self):
        """Test edge cases in category validation."""
        # Single character name
        category = VideoCategoryBase(category_id="1", name="X")
        assert category.name == "X"

        # Name with special characters
        category = VideoCategoryBase(category_id="1", name="Film & Animation")
        assert category.name == "Film & Animation"

        # Name with numbers
        category = VideoCategoryBase(category_id="1", name="3D Animation")
        assert category.name == "3D Animation"

        # Name with unicode
        category = VideoCategoryBase(category_id="1", name="音楽 Music")
        assert category.name == "音楽 Music"

    def test_model_config_validation(self):
        """Test model configuration settings."""
        # Test validate_assignment works
        created_at = datetime.now(timezone.utc)
        updated_at = datetime.now(timezone.utc)

        category = VideoCategory(
            category_id="10",
            name="Music",
            created_at=created_at,
            updated_at=updated_at,
        )

        # Assignment should trigger validation
        with pytest.raises(ValidationError):
            category.category_id = "abc"  # Non-numeric

        with pytest.raises(ValidationError):
            category.name = ""  # Empty
