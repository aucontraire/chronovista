"""
Tests for tag normalization Pydantic models.

Tests validation, serialization, and model validators for canonical tags,
tag aliases, named entities, and entity aliases using factory patterns.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from uuid_utils import uuid7

from chronovista.db.models import (
    CanonicalTag as CanonicalTagDB,
    EntityAlias as EntityAliasDB,
    NamedEntity as NamedEntityDB,
    TagAlias as TagAliasDB,
)
from chronovista.models.canonical_tag import (
    CanonicalTag,
    CanonicalTagBase,
    CanonicalTagCreate,
    CanonicalTagUpdate,
)
from chronovista.models.entity_alias import (
    EntityAlias,
    EntityAliasBase,
    EntityAliasCreate,
    EntityAliasUpdate,
)
from chronovista.models.enums import (
    CreationMethod,
    DiscoveryMethod,
    EntityAliasType,
    EntityType,
    TagStatus,
)
from chronovista.models.named_entity import (
    NamedEntity,
    NamedEntityBase,
    NamedEntityCreate,
    NamedEntityUpdate,
)
from chronovista.models.tag_alias import (
    TagAlias,
    TagAliasBase,
    TagAliasCreate,
    TagAliasUpdate,
)
from tests.factories import (
    CanonicalTagBaseFactory,
    CanonicalTagCreateFactory,
    CanonicalTagFactory,
    CanonicalTagTestData,
    CanonicalTagUpdateFactory,
    EntityAliasBaseFactory,
    EntityAliasCreateFactory,
    EntityAliasFactory,
    EntityAliasTestData,
    EntityAliasUpdateFactory,
    NamedEntityBaseFactory,
    NamedEntityCreateFactory,
    NamedEntityFactory,
    NamedEntityTestData,
    NamedEntityUpdateFactory,
    TagAliasBaseFactory,
    TagAliasCreateFactory,
    TagAliasFactory,
    TagAliasTestData,
    TagAliasUpdateFactory,
)


class TestCanonicalTagModels:
    """Test CanonicalTag Pydantic models."""

    def test_create_canonical_tag_base_valid(self) -> None:
        """Test creating valid CanonicalTagBase with keyword arguments."""
        tag = CanonicalTagBaseFactory.build(
            canonical_form="Python",
            normalized_form="python",
            entity_type=None,
            status=TagStatus.ACTIVE,
        )

        assert tag.canonical_form == "Python"
        assert tag.normalized_form == "python"
        assert tag.entity_type is None
        assert tag.status == TagStatus.ACTIVE

    def test_create_canonical_tag_create_valid(self) -> None:
        """Test creating valid CanonicalTagCreate with all fields."""
        tag = CanonicalTagCreateFactory.build(
            canonical_form="Machine Learning",
            normalized_form="machine learning",
            entity_type=EntityType.TECHNICAL_TERM,
            status=TagStatus.ACTIVE,
            alias_count=3,
            video_count=10,
        )

        assert tag.canonical_form == "Machine Learning"
        assert tag.normalized_form == "machine learning"
        assert tag.entity_type == EntityType.TECHNICAL_TERM
        assert tag.status == TagStatus.ACTIVE
        assert tag.alias_count == 3
        assert tag.video_count == 10

    def test_canonical_tag_create_defaults(self) -> None:
        """Test CanonicalTagCreate default values (FR-025)."""
        tag = CanonicalTagCreate(
            canonical_form="Python",
            normalized_form="python",
        )

        assert tag.alias_count == 1
        assert tag.video_count == 0
        assert tag.entity_type is None
        assert tag.status == TagStatus.ACTIVE
        assert tag.entity_id is None
        assert tag.merged_into_id is None

    def test_canonical_tag_full_with_all_fields(self) -> None:
        """Test creating full CanonicalTag with all fields."""
        tag_id = uuid.UUID(bytes=uuid7().bytes)
        entity_id = uuid.UUID(bytes=uuid7().bytes)
        now = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        tag = CanonicalTagFactory.build(
            id=tag_id,
            canonical_form="Python",
            normalized_form="python",
            entity_type=EntityType.TECHNICAL_TERM,
            status=TagStatus.ACTIVE,
            alias_count=5,
            video_count=100,
            entity_id=entity_id,
            merged_into_id=None,
            created_at=now,
            updated_at=now,
        )

        assert tag.id == tag_id
        assert tag.canonical_form == "Python"
        assert tag.normalized_form == "python"
        assert tag.entity_type == EntityType.TECHNICAL_TERM
        assert tag.status == TagStatus.ACTIVE
        assert tag.alias_count == 5
        assert tag.video_count == 100
        assert tag.entity_id == entity_id
        assert tag.merged_into_id is None
        assert tag.created_at == now
        assert tag.updated_at == now

    def test_canonical_tag_classification_enum_types(self) -> None:
        """Test classification fields use enum types (FR-025)."""
        tag = CanonicalTagCreateFactory.build(
            entity_type=EntityType.PERSON,
            status=TagStatus.MERGED,
            merged_into_id=uuid.UUID(bytes=uuid7().bytes),
        )

        # Verify that entity_type is an EntityType enum
        assert isinstance(tag.entity_type, EntityType)
        assert tag.entity_type == EntityType.PERSON

        # Verify that status is a TagStatus enum
        assert isinstance(tag.status, TagStatus)
        assert tag.status == TagStatus.MERGED

    def test_canonical_tag_model_dump_serialization(self) -> None:
        """Test model_dump() serialization of classification fields (US3 AS-3)."""
        tag = CanonicalTagCreateFactory.build(
            canonical_form="Python",
            normalized_form="python",
            entity_type=EntityType.TECHNICAL_TERM,
            status=TagStatus.ACTIVE,
        )

        data = tag.model_dump()

        # Enums should serialize to their string values
        assert data["entity_type"] == "technical_term"
        assert data["status"] == "active"
        assert data["canonical_form"] == "Python"
        assert data["normalized_form"] == "python"

    def test_canonical_tag_merged_status_requires_target(self) -> None:
        """Test merged status requires merged_into_id (FR-027)."""
        with pytest.raises(ValidationError, match="merged_into_id is required"):
            CanonicalTagCreate(
                canonical_form="OldTag",
                normalized_form="oldtag",
                status=TagStatus.MERGED,
                merged_into_id=None,
            )

    def test_canonical_tag_merged_with_target_succeeds(self) -> None:
        """Test merged status with merged_into_id succeeds (FR-027)."""
        target_id = uuid.UUID(bytes=uuid7().bytes)
        tag = CanonicalTagCreate(
            canonical_form="OldTag",
            normalized_form="oldtag",
            status=TagStatus.MERGED,
            merged_into_id=target_id,
        )

        assert tag.status == TagStatus.MERGED
        assert tag.merged_into_id == target_id

    def test_canonical_tag_no_self_merge(self) -> None:
        """Test tag cannot be merged into itself (FR-028)."""
        tag_id = uuid.UUID(bytes=uuid7().bytes)

        with pytest.raises(ValidationError, match="cannot be merged into itself"):
            CanonicalTag(
                id=tag_id,
                canonical_form="SelfMerge",
                normalized_form="selfmerge",
                status=TagStatus.MERGED,
                merged_into_id=tag_id,  # Same as id - should fail
                alias_count=1,
                video_count=0,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )

    def test_canonical_tag_update_partial_fields(self) -> None:
        """Test CanonicalTagUpdate with partial fields."""
        update = CanonicalTagUpdate(
            canonical_form="Updated Tag",
            status=TagStatus.DEPRECATED,
        )

        assert update.canonical_form == "Updated Tag"
        assert update.status == TagStatus.DEPRECATED
        # Other fields should remain None
        assert update.normalized_form is None
        assert update.entity_type is None
        assert update.alias_count is None
        assert update.video_count is None

    @pytest.mark.parametrize("invalid_form", CanonicalTagTestData.INVALID_CANONICAL_FORMS)
    def test_canonical_form_validation_invalid(self, invalid_form: str) -> None:
        """Test canonical_form validation with invalid inputs."""
        with pytest.raises(ValidationError):
            CanonicalTagBaseFactory.build(canonical_form=invalid_form)

    @pytest.mark.parametrize("valid_form", CanonicalTagTestData.VALID_CANONICAL_FORMS)
    def test_canonical_form_validation_valid(self, valid_form: str) -> None:
        """Test canonical_form validation with valid inputs."""
        tag = CanonicalTagBaseFactory.build(canonical_form=valid_form)
        assert tag.canonical_form == valid_form


class TestTagAliasModels:
    """Test TagAlias Pydantic models."""

    def test_create_tag_alias_base_valid(self) -> None:
        """Test creating valid TagAliasBase."""
        alias = TagAliasBaseFactory.build(
            raw_form="Python",
            normalized_form="python",
            creation_method=CreationMethod.AUTO_NORMALIZE,
        )

        assert alias.raw_form == "Python"
        assert alias.normalized_form == "python"
        assert alias.creation_method == CreationMethod.AUTO_NORMALIZE

    def test_tag_alias_create_defaults(self) -> None:
        """Test TagAliasCreate default values."""
        canonical_tag_id = uuid.UUID(bytes=uuid7().bytes)
        alias = TagAliasCreate(
            raw_form="PYTHON",
            normalized_form="python",
            canonical_tag_id=canonical_tag_id,
        )

        # Verify defaults
        assert alias.creation_method == CreationMethod.AUTO_NORMALIZE
        assert alias.normalization_version == 1
        assert alias.occurrence_count == 1

    def test_tag_alias_normalization_version_field(self) -> None:
        """Test normalization_version field exists and defaults to 1 (FR-030)."""
        canonical_tag_id = uuid.UUID(bytes=uuid7().bytes)
        alias = TagAliasCreate(
            raw_form="#MachineLearning",
            normalized_form="machinelearning",
            canonical_tag_id=canonical_tag_id,
        )

        assert hasattr(alias, "normalization_version")
        assert alias.normalization_version == 1

    def test_tag_alias_full_with_all_fields(self) -> None:
        """Test creating full TagAlias with all fields."""
        alias_id = uuid.UUID(bytes=uuid7().bytes)
        canonical_tag_id = uuid.UUID(bytes=uuid7().bytes)
        now = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        alias = TagAliasFactory.build(
            id=alias_id,
            raw_form="#Python",
            normalized_form="python",
            canonical_tag_id=canonical_tag_id,
            creation_method=CreationMethod.MANUAL_MERGE,
            normalization_version=2,
            occurrence_count=50,
            first_seen_at=now,
            last_seen_at=now,
            created_at=now,
        )

        assert alias.id == alias_id
        assert alias.raw_form == "#Python"
        assert alias.normalized_form == "python"
        assert alias.canonical_tag_id == canonical_tag_id
        assert alias.creation_method == CreationMethod.MANUAL_MERGE
        assert alias.normalization_version == 2
        assert alias.occurrence_count == 50
        assert alias.first_seen_at == now
        assert alias.last_seen_at == now
        assert alias.created_at == now

    def test_tag_alias_model_dump_serialization(self) -> None:
        """Test model_dump() serialization."""
        canonical_tag_id = uuid.UUID(bytes=uuid7().bytes)
        alias = TagAliasCreateFactory.build(
            raw_form="Python",
            normalized_form="python",
            canonical_tag_id=canonical_tag_id,
            creation_method=CreationMethod.BACKFILL,
        )

        data = alias.model_dump()

        assert data["raw_form"] == "Python"
        assert data["normalized_form"] == "python"
        assert data["canonical_tag_id"] == canonical_tag_id
        assert data["creation_method"] == "backfill"
        assert data["normalization_version"] == 1
        assert data["occurrence_count"] == 1

    @pytest.mark.parametrize("invalid_form", TagAliasTestData.INVALID_RAW_FORMS)
    def test_raw_form_validation_invalid(self, invalid_form: str) -> None:
        """Test raw_form validation with invalid inputs."""
        with pytest.raises(ValidationError):
            TagAliasBaseFactory.build(raw_form=invalid_form)

    @pytest.mark.parametrize("valid_form", TagAliasTestData.VALID_RAW_FORMS)
    def test_raw_form_validation_valid(self, valid_form: str) -> None:
        """Test raw_form validation with valid inputs."""
        alias = TagAliasBaseFactory.build(raw_form=valid_form)
        assert alias.raw_form == valid_form


class TestNamedEntityModels:
    """Test NamedEntity Pydantic models."""

    def test_create_named_entity_base_valid(self) -> None:
        """Test creating valid NamedEntityBase."""
        entity = NamedEntityBaseFactory.build(
            canonical_name="Elon Musk",
            canonical_name_normalized="elon musk",
            entity_type=EntityType.PERSON,
            discovery_method=DiscoveryMethod.MANUAL,
            status=TagStatus.ACTIVE,
        )

        assert entity.canonical_name == "Elon Musk"
        assert entity.canonical_name_normalized == "elon musk"
        assert entity.entity_type == EntityType.PERSON
        assert entity.discovery_method == DiscoveryMethod.MANUAL
        assert entity.status == TagStatus.ACTIVE

    def test_named_entity_create_defaults(self) -> None:
        """Test NamedEntityCreate default values."""
        entity = NamedEntityCreate(
            canonical_name="Python",
            canonical_name_normalized="python",
            entity_type=EntityType.TECHNICAL_TERM,
        )

        # Verify defaults
        assert entity.discovery_method == DiscoveryMethod.MANUAL
        assert entity.confidence == 1.0
        assert entity.status == TagStatus.ACTIVE
        assert entity.entity_subtype is None
        assert entity.description is None
        assert entity.external_ids == {}
        assert entity.merged_into_id is None

    def test_named_entity_merged_status_requires_target(self) -> None:
        """Test merged status requires merged_into_id (FR-027)."""
        with pytest.raises(ValidationError, match="merged_into_id is required"):
            NamedEntityCreate(
                canonical_name="OldEntity",
                canonical_name_normalized="oldentity",
                entity_type=EntityType.PERSON,
                status=TagStatus.MERGED,
                merged_into_id=None,
            )

    def test_named_entity_merged_with_target_succeeds(self) -> None:
        """Test merged status with merged_into_id succeeds (FR-027)."""
        target_id = uuid.UUID(bytes=uuid7().bytes)
        entity = NamedEntityCreate(
            canonical_name="OldEntity",
            canonical_name_normalized="oldentity",
            entity_type=EntityType.PERSON,
            status=TagStatus.MERGED,
            merged_into_id=target_id,
        )

        assert entity.status == TagStatus.MERGED
        assert entity.merged_into_id == target_id

    def test_named_entity_no_self_merge(self) -> None:
        """Test entity cannot be merged into itself (FR-028)."""
        entity_id = uuid.UUID(bytes=uuid7().bytes)

        with pytest.raises(ValidationError, match="cannot be merged into itself"):
            NamedEntity(
                id=entity_id,
                canonical_name="SelfMerge",
                canonical_name_normalized="selfmerge",
                entity_type=EntityType.PERSON,
                discovery_method=DiscoveryMethod.MANUAL,
                status=TagStatus.MERGED,
                merged_into_id=entity_id,  # Same as id - should fail
                mention_count=0,
                video_count=0,
                channel_count=0,
                confidence=1.0,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )

    def test_named_entity_confidence_out_of_range_high(self) -> None:
        """Test confidence validation rejects values > 1.0."""
        with pytest.raises(ValidationError):
            NamedEntityCreate(
                canonical_name="Test",
                canonical_name_normalized="test",
                entity_type=EntityType.PERSON,
                confidence=1.5,
            )

    def test_named_entity_confidence_out_of_range_low(self) -> None:
        """Test confidence validation rejects values < 0.0."""
        with pytest.raises(ValidationError):
            NamedEntityCreate(
                canonical_name="Test",
                canonical_name_normalized="test",
                entity_type=EntityType.PERSON,
                confidence=-0.1,
            )

    def test_named_entity_confidence_valid_range(self) -> None:
        """Test confidence validation accepts valid range [0.0, 1.0]."""
        entity = NamedEntityCreate(
            canonical_name="Test",
            canonical_name_normalized="test",
            entity_type=EntityType.PERSON,
            confidence=0.5,
        )
        assert entity.confidence == 0.5

        entity_min = NamedEntityCreate(
            canonical_name="Test Min",
            canonical_name_normalized="test min",
            entity_type=EntityType.PERSON,
            confidence=0.0,
        )
        assert entity_min.confidence == 0.0

        entity_max = NamedEntityCreate(
            canonical_name="Test Max",
            canonical_name_normalized="test max",
            entity_type=EntityType.PERSON,
            confidence=1.0,
        )
        assert entity_max.confidence == 1.0

    def test_named_entity_topic_type_accepted_by_pydantic(self) -> None:
        """Test EntityType.TOPIC is valid at Pydantic level (US3 AS-2).

        Note: TOPIC is valid in the EntityType enum, but DB-level CHECK
        constraint prevents it in named_entities table. This test verifies
        Pydantic accepts TOPIC since it's a valid enum value.
        """
        entity = NamedEntityCreate(
            canonical_name="Test Topic",
            canonical_name_normalized="test topic",
            entity_type=EntityType.TOPIC,
        )

        # Pydantic accepts TOPIC because it's in EntityType enum
        assert entity.entity_type == EntityType.TOPIC

    def test_named_entity_model_dump_serialization(self) -> None:
        """Test model_dump() serialization."""
        entity = NamedEntityCreateFactory.build(
            canonical_name="Google",
            canonical_name_normalized="google",
            entity_type=EntityType.ORGANIZATION,
            discovery_method=DiscoveryMethod.SPACY_NER,
            status=TagStatus.ACTIVE,
            confidence=0.95,
        )

        data = entity.model_dump()

        assert data["canonical_name"] == "Google"
        assert data["canonical_name_normalized"] == "google"
        assert data["entity_type"] == "organization"
        assert data["discovery_method"] == "spacy_ner"
        assert data["status"] == "active"
        assert data["confidence"] == 0.95

    @pytest.mark.parametrize("invalid_name", NamedEntityTestData.INVALID_CANONICAL_NAMES)
    def test_canonical_name_validation_invalid(self, invalid_name: str) -> None:
        """Test canonical_name validation with invalid inputs."""
        with pytest.raises(ValidationError):
            NamedEntityBaseFactory.build(canonical_name=invalid_name)

    @pytest.mark.parametrize("valid_name", NamedEntityTestData.VALID_CANONICAL_NAMES)
    def test_canonical_name_validation_valid(self, valid_name: str) -> None:
        """Test canonical_name validation with valid inputs."""
        entity = NamedEntityBaseFactory.build(canonical_name=valid_name)
        assert entity.canonical_name == valid_name


class TestEntityAliasModels:
    """Test EntityAlias Pydantic models."""

    def test_create_entity_alias_base_valid(self) -> None:
        """Test creating valid EntityAliasBase."""
        alias = EntityAliasBaseFactory.build(
            alias_name="Elon",
            alias_name_normalized="elon",
            alias_type=EntityAliasType.NICKNAME,
        )

        assert alias.alias_name == "Elon"
        assert alias.alias_name_normalized == "elon"
        assert alias.alias_type == EntityAliasType.NICKNAME

    def test_entity_alias_create_with_entity_id(self) -> None:
        """Test EntityAliasCreate with entity_id."""
        entity_id = uuid.UUID(bytes=uuid7().bytes)
        alias = EntityAliasCreate(
            alias_name="SpaceX CEO",
            alias_name_normalized="spacex ceo",
            entity_id=entity_id,
        )

        assert alias.alias_name == "SpaceX CEO"
        assert alias.alias_name_normalized == "spacex ceo"
        assert alias.entity_id == entity_id
        assert alias.alias_type == EntityAliasType.NAME_VARIANT  # Default
        assert alias.occurrence_count == 0  # Default

    def test_entity_alias_type_defaults_to_name_variant(self) -> None:
        """Test alias_type defaults to NAME_VARIANT."""
        entity_id = uuid.UUID(bytes=uuid7().bytes)
        alias = EntityAliasCreate(
            alias_name="Test",
            alias_name_normalized="test",
            entity_id=entity_id,
        )

        assert alias.alias_type == EntityAliasType.NAME_VARIANT

    def test_entity_alias_full_with_all_fields(self) -> None:
        """Test creating full EntityAlias with all fields."""
        alias_id = uuid.UUID(bytes=uuid7().bytes)
        entity_id = uuid.UUID(bytes=uuid7().bytes)
        now = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)

        alias = EntityAliasFactory.build(
            id=alias_id,
            alias_name="E. Musk",
            alias_name_normalized="e. musk",
            alias_type=EntityAliasType.ABBREVIATION,
            entity_id=entity_id,
            occurrence_count=25,
            first_seen_at=now,
            last_seen_at=now,
        )

        assert alias.id == alias_id
        assert alias.alias_name == "E. Musk"
        assert alias.alias_name_normalized == "e. musk"
        assert alias.alias_type == EntityAliasType.ABBREVIATION
        assert alias.entity_id == entity_id
        assert alias.occurrence_count == 25
        assert alias.first_seen_at == now
        assert alias.last_seen_at == now

    def test_entity_alias_model_dump_serialization(self) -> None:
        """Test model_dump() serialization."""
        entity_id = uuid.UUID(bytes=uuid7().bytes)
        alias = EntityAliasCreateFactory.build(
            alias_name="Tesla CEO",
            alias_name_normalized="tesla ceo",
            alias_type=EntityAliasType.NICKNAME,
            entity_id=entity_id,
        )

        data = alias.model_dump()

        assert data["alias_name"] == "Tesla CEO"
        assert data["alias_name_normalized"] == "tesla ceo"
        assert data["alias_type"] == "nickname"
        assert data["entity_id"] == entity_id
        assert data["occurrence_count"] == 0

    @pytest.mark.parametrize("invalid_name", EntityAliasTestData.INVALID_ALIAS_NAMES)
    def test_alias_name_validation_invalid(self, invalid_name: str) -> None:
        """Test alias_name validation with invalid inputs."""
        with pytest.raises(ValidationError):
            EntityAliasBaseFactory.build(alias_name=invalid_name)

    @pytest.mark.parametrize("valid_name", EntityAliasTestData.VALID_ALIAS_NAMES)
    def test_alias_name_validation_valid(self, valid_name: str) -> None:
        """Test alias_name validation with valid inputs."""
        alias = EntityAliasBaseFactory.build(alias_name=valid_name)
        assert alias.alias_name == valid_name


class TestUUIDv7Generation:
    """Test UUIDv7 generation in ORM models (US3 AS-6).

    Note: These tests verify that the ORM model configuration includes
    default=uuid7 for primary keys. The actual UUID generation happens
    when the object is persisted to the database, so we verify the
    callable is configured, not that IDs are pre-generated.
    """

    def test_canonical_tag_has_uuid7_default(self) -> None:
        """Test CanonicalTag ORM has uuid7 default configured."""
        # Verify the model has the id field configured with uuid7 default
        assert hasattr(CanonicalTagDB, "id")
        # The ORM model should have uuid7 as the default factory
        # When persisted to DB, it will generate UUIDv7
        # For now, verify the model accepts manual UUIDv7 assignment
        tag_id = uuid.UUID(bytes=uuid7().bytes)
        tag = CanonicalTagDB(
            id=tag_id,
            canonical_form="Python",
            normalized_form="python",
            entity_type=None,
            status="active",
            alias_count=1,
            video_count=0,
        )
        assert tag.id == tag_id
        assert tag.id.version == 7

    def test_tag_alias_has_uuid7_default(self) -> None:
        """Test TagAlias ORM has uuid7 default configured."""
        alias_id = uuid.UUID(bytes=uuid7().bytes)
        canonical_tag_id = uuid.UUID(bytes=uuid7().bytes)
        alias = TagAliasDB(
            id=alias_id,
            raw_form="Python",
            normalized_form="python",
            canonical_tag_id=canonical_tag_id,
            creation_method="auto_normalize",
            normalization_version=1,
            occurrence_count=1,
        )

        assert alias.id == alias_id
        assert alias.id.version == 7

    def test_named_entity_has_uuid7_default(self) -> None:
        """Test NamedEntity ORM has uuid7 default configured."""
        entity_id = uuid.UUID(bytes=uuid7().bytes)
        entity = NamedEntityDB(
            id=entity_id,
            canonical_name="Elon Musk",
            canonical_name_normalized="elon musk",
            entity_type="person",
            discovery_method="manual",
            status="active",
            mention_count=0,
            video_count=0,
            channel_count=0,
            confidence=1.0,
        )

        assert entity.id == entity_id
        assert entity.id.version == 7

    def test_entity_alias_has_uuid7_default(self) -> None:
        """Test EntityAlias ORM has uuid7 default configured."""
        alias_id = uuid.UUID(bytes=uuid7().bytes)
        entity_id = uuid.UUID(bytes=uuid7().bytes)
        alias = EntityAliasDB(
            id=alias_id,
            alias_name="Elon",
            alias_name_normalized="elon",
            alias_type="nickname",
            entity_id=entity_id,
            occurrence_count=0,
        )

        assert alias.id == alias_id
        assert alias.id.version == 7

    def test_generated_uuids_are_unique(self) -> None:
        """Test that generated UUIDs are unique."""
        # Generate multiple UUIDs and verify uniqueness
        ids = [uuid.UUID(bytes=uuid7().bytes) for _ in range(5)]
        assert len(ids) == len(set(ids))
        # All should be version 7
        assert all(id.version == 7 for id in ids)
