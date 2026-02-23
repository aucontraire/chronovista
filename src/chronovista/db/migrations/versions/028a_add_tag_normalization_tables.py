"""add_tag_normalization_tables

Revision ID: f9b5c8d6e3a1
Revises: e8a4f5c9d7b2
Create Date: 2026-02-22 14:00:00.000000

This migration implements the tag normalization schema for Feature 028
(Tag Normalization Schema). It creates five new tables to support
conservative tag normalization, entity extraction, and operation logging.

New Tables:
1. named_entities - Named entities extracted from tags (people, places, orgs, etc.)
2. entity_aliases - Alternative names/variations for named entities
3. canonical_tags - Canonical tag forms with normalization
4. tag_aliases - Raw tag forms mapped to canonical tags
5. tag_operation_logs - Audit log for tag management operations

Key Features:
- UUIDv7 primary keys for all new tables
- Conservative normalization (case/accent/hashtag folding only)
- Entity linking with confidence scores
- Tag merge/split operation tracking with rollback support
- Comprehensive CHECK constraints for data integrity
- 15 performance indexes including partial indexes

Related: Feature 028 (Tag Normalization Schema), Tasks T005-T006
Architecture: ADR-003 Tag Normalization
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

# revision identifiers, used by Alembic.
revision = "f9b5c8d6e3a1"
down_revision = "e8a4f5c9d7b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """
    Create tag normalization tables with all constraints and indexes.

    Creates tables in FK dependency order:
    1. named_entities (no FK dependencies)
    2. entity_aliases, canonical_tags (FK to named_entities)
    3. tag_aliases, tag_operation_logs (FK to canonical_tags or none)
    """
    # =========================================================================
    # TABLE 1: named_entities (no FK dependencies)
    # =========================================================================
    op.create_table(
        "named_entities",
        sa.Column("id", UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column("canonical_name", sa.String(500), nullable=False),
        sa.Column("canonical_name_normalized", sa.String(500), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_subtype", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "external_ids",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("mention_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("video_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("channel_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "discovery_method",
            sa.String(30),
            nullable=False,
            server_default=sa.text("'manual'"),
        ),
        sa.Column("confidence", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("merged_into_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_named_entities"),
        sa.ForeignKeyConstraint(
            ["merged_into_id"],
            ["named_entities.id"],
            name="fk_named_entities_merged_into",
        ),
        sa.UniqueConstraint(
            "canonical_name_normalized",
            "entity_type",
            name="uq_named_entity_canonical",
        ),
        sa.CheckConstraint(
            "entity_type IN ('person', 'organization', 'place', 'event', 'work', 'technical_term')",
            name="chk_entity_type_valid",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'merged', 'deprecated')",
            name="chk_entity_status_valid",
        ),
        sa.CheckConstraint(
            "discovery_method IN ('manual', 'spacy_ner', 'tag_bootstrap', 'llm_extraction', 'user_created')",
            name="chk_entity_discovery_method_valid",
        ),
        sa.CheckConstraint(
            "confidence >= 0.0 AND confidence <= 1.0",
            name="chk_entity_confidence_range",
        ),
    )

    # =========================================================================
    # TABLE 2: entity_aliases (FK to named_entities)
    # =========================================================================
    op.create_table(
        "entity_aliases",
        sa.Column("id", UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("alias_name", sa.String(500), nullable=False),
        sa.Column("alias_name_normalized", sa.String(500), nullable=False),
        sa.Column(
            "alias_type",
            sa.String(30),
            nullable=False,
            server_default=sa.text("'name_variant'"),
        ),
        sa.Column("occurrence_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_entity_aliases"),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["named_entities.id"],
            name="fk_entity_aliases_entity",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "alias_name_normalized",
            "entity_id",
            name="uq_entity_alias_name",
        ),
        sa.CheckConstraint(
            "alias_type IN ('name_variant', 'abbreviation', 'nickname', 'asr_error', 'translated_name', 'former_name')",
            name="chk_alias_type_valid",
        ),
    )

    # =========================================================================
    # TABLE 3: canonical_tags (FK to named_entities)
    # =========================================================================
    op.create_table(
        "canonical_tags",
        sa.Column("id", UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column("canonical_form", sa.String(500), nullable=False),
        sa.Column("normalized_form", sa.String(500), nullable=False, unique=True),
        sa.Column("alias_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("video_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("entity_type", sa.String(50), nullable=True),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default=sa.text("'active'")),
        sa.Column("merged_into_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_canonical_tags"),
        sa.ForeignKeyConstraint(
            ["entity_id"],
            ["named_entities.id"],
            name="fk_canonical_tags_entity",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["merged_into_id"],
            ["canonical_tags.id"],
            name="fk_canonical_tags_merged_into",
        ),
        sa.CheckConstraint(
            "entity_type IN ('person', 'organization', 'place', 'event', 'work', 'technical_term', 'topic', 'descriptor') OR entity_type IS NULL",
            name="chk_canonical_tag_entity_type_valid",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'merged', 'deprecated')",
            name="chk_canonical_tag_status_valid",
        ),
        sa.CheckConstraint(
            "alias_count >= 1",
            name="chk_canonical_tag_alias_count_positive",
        ),
        sa.CheckConstraint(
            "video_count >= 0",
            name="chk_canonical_tag_video_count_non_negative",
        ),
        sa.CheckConstraint(
            "canonical_form != ''",
            name="chk_canonical_tag_canonical_form_not_empty",
        ),
    )

    # =========================================================================
    # TABLE 4: tag_aliases (FK to canonical_tags)
    # =========================================================================
    op.create_table(
        "tag_aliases",
        sa.Column("id", UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column("raw_form", sa.String(500), nullable=False, unique=True),
        sa.Column("normalized_form", sa.String(500), nullable=False),
        sa.Column("canonical_tag_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "creation_method",
            sa.String(30),
            nullable=False,
            server_default=sa.text("'auto_normalize'"),
        ),
        sa.Column(
            "normalization_version",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "occurrence_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column(
            "first_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tag_aliases"),
        sa.ForeignKeyConstraint(
            ["canonical_tag_id"],
            ["canonical_tags.id"],
            name="fk_tag_aliases_canonical_tag",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "creation_method IN ('auto_normalize', 'manual_merge', 'backfill', 'api_create')",
            name="chk_tag_alias_creation_method_valid",
        ),
        sa.CheckConstraint(
            "occurrence_count >= 1",
            name="chk_tag_alias_occurrence_count_positive",
        ),
    )

    # =========================================================================
    # TABLE 5: tag_operation_logs (no FK dependencies, just plain UUID column)
    # =========================================================================
    op.create_table(
        "tag_operation_logs",
        sa.Column("id", UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column("operation_type", sa.String(30), nullable=False),
        sa.Column(
            "source_canonical_ids",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("target_canonical_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "affected_alias_ids",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "performed_by",
            sa.String(100),
            nullable=False,
            server_default=sa.text("'system'"),
        ),
        sa.Column(
            "performed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "rollback_data",
            JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("rolled_back", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_tag_operation_logs"),
        sa.CheckConstraint(
            "operation_type IN ('merge', 'split', 'rename', 'delete', 'create')",
            name="chk_tag_operation_type_valid",
        ),
    )

    # =========================================================================
    # INDEXES (15 total)
    # =========================================================================

    # Index 1: canonical_tags - video count descending (hot tags)
    op.create_index(
        "idx_canonical_tags_video_count_desc",
        "canonical_tags",
        [sa.text("video_count DESC")],
        unique=False,
    )

    # Index 2: canonical_tags - canonical form pattern ops (LIKE queries)
    op.create_index(
        "idx_canonical_tags_canonical_pattern",
        "canonical_tags",
        ["canonical_form"],
        unique=False,
        postgresql_ops={"canonical_form": "varchar_pattern_ops"},
    )

    # Index 3: canonical_tags - entity_id (partial index WHERE NOT NULL)
    op.create_index(
        "idx_canonical_tags_entity_id",
        "canonical_tags",
        ["entity_id"],
        unique=False,
        postgresql_where=sa.text("entity_id IS NOT NULL"),
    )

    # Index 4: canonical_tags - normalized form for active tags (partial)
    op.create_index(
        "idx_canonical_tags_active_normalized",
        "canonical_tags",
        ["normalized_form"],
        unique=False,
        postgresql_where=sa.text("status = 'active'"),
    )

    # Index 5: tag_aliases - normalized form
    op.create_index(
        "idx_tag_aliases_normalized",
        "tag_aliases",
        ["normalized_form"],
        unique=False,
    )

    # Index 6: tag_aliases - canonical_tag_id
    op.create_index(
        "idx_tag_aliases_canonical_id",
        "tag_aliases",
        ["canonical_tag_id"],
        unique=False,
    )

    # Index 7: tag_aliases - raw form pattern ops (LIKE queries)
    op.create_index(
        "idx_tag_aliases_raw_pattern",
        "tag_aliases",
        ["raw_form"],
        unique=False,
        postgresql_ops={"raw_form": "varchar_pattern_ops"},
    )

    # Index 8: named_entities - normalized name
    op.create_index(
        "idx_named_entities_normalized",
        "named_entities",
        ["canonical_name_normalized"],
        unique=False,
    )

    # Index 9: named_entities - entity type
    op.create_index(
        "idx_named_entities_type",
        "named_entities",
        ["entity_type"],
        unique=False,
    )

    # Index 10: named_entities - status
    op.create_index(
        "idx_named_entities_status",
        "named_entities",
        ["status"],
        unique=False,
    )

    # Index 11: entity_aliases - normalized name
    op.create_index(
        "idx_entity_aliases_normalized",
        "entity_aliases",
        ["alias_name_normalized"],
        unique=False,
    )

    # Index 12: entity_aliases - entity_id
    op.create_index(
        "idx_entity_aliases_entity_id",
        "entity_aliases",
        ["entity_id"],
        unique=False,
    )

    # Index 13: entity_aliases - alias type
    op.create_index(
        "idx_entity_aliases_type",
        "entity_aliases",
        ["alias_type"],
        unique=False,
    )

    # Index 14: tag_operation_logs - performed_at
    op.create_index(
        "idx_tag_operation_logs_performed_at",
        "tag_operation_logs",
        ["performed_at"],
        unique=False,
    )

    # Index 15: video_tags - tag (NEW index on EXISTING table)
    # Use IF NOT EXISTS because this index may already exist from prior operations
    op.execute("CREATE INDEX IF NOT EXISTS idx_video_tags_tag ON video_tags (tag)")


def downgrade() -> None:
    """
    Drop tag normalization tables and all associated indexes.

    WARNING: This will permanently delete all tag normalization data including:
    - All canonical tags and their aliases
    - All named entities and their aliases
    - All tag operation history and rollback data
    - Statistics and confidence scores

    Ensure you have backups if this data is needed.

    Drop order is reverse of creation to respect FK constraints.
    """
    # =========================================================================
    # DROP INDEXES (reverse order)
    # =========================================================================

    # Drop new index on existing video_tags table first
    # Use IF EXISTS because the index may have pre-existed this migration
    op.execute("DROP INDEX IF EXISTS idx_video_tags_tag")

    # Drop tag_operation_logs indexes
    op.drop_index("idx_tag_operation_logs_performed_at", table_name="tag_operation_logs")

    # Drop entity_aliases indexes
    op.drop_index("idx_entity_aliases_type", table_name="entity_aliases")
    op.drop_index("idx_entity_aliases_entity_id", table_name="entity_aliases")
    op.drop_index("idx_entity_aliases_normalized", table_name="entity_aliases")

    # Drop named_entities indexes
    op.drop_index("idx_named_entities_status", table_name="named_entities")
    op.drop_index("idx_named_entities_type", table_name="named_entities")
    op.drop_index("idx_named_entities_normalized", table_name="named_entities")

    # Drop tag_aliases indexes
    op.drop_index("idx_tag_aliases_raw_pattern", table_name="tag_aliases")
    op.drop_index("idx_tag_aliases_canonical_id", table_name="tag_aliases")
    op.drop_index("idx_tag_aliases_normalized", table_name="tag_aliases")

    # Drop canonical_tags indexes
    op.drop_index("idx_canonical_tags_active_normalized", table_name="canonical_tags")
    op.drop_index("idx_canonical_tags_entity_id", table_name="canonical_tags")
    op.drop_index("idx_canonical_tags_canonical_pattern", table_name="canonical_tags")
    op.drop_index("idx_canonical_tags_video_count_desc", table_name="canonical_tags")

    # =========================================================================
    # DROP TABLES (reverse FK dependency order)
    # =========================================================================

    # Drop tables with no FK dependencies or that depend on others
    op.drop_table("tag_operation_logs")
    op.drop_table("tag_aliases")

    # Drop tables that depend on named_entities
    op.drop_table("canonical_tags")
    op.drop_table("entity_aliases")

    # Drop base table
    op.drop_table("named_entities")
