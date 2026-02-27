"""
Tag management service for CLI curation operations.

Orchestrates merge, split, undo, rename, classify, deprecate, and collision
review operations on the canonical tag system. All mutations are atomic
(single transaction) and logged to tag_operation_logs with self-contained
rollback_data for undo capability.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import distinct, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import CanonicalTag as CanonicalTagDB
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TagAlias as TagAliasDB
from chronovista.db.models import TagOperationLog as TagOperationLogDB
from chronovista.db.models import VideoTag
from chronovista.models.enums import (
    DiscoveryMethod,
    EntityAliasType,
    EntityType,
    TagOperationType,
    TagStatus,
)
from chronovista.models.tag_operation_log import (
    TagOperationLogCreate,
    TagOperationLogUpdate,
)
from chronovista.repositories.canonical_tag_repository import CanonicalTagRepository
from chronovista.repositories.entity_alias_repository import EntityAliasRepository
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.repositories.tag_alias_repository import TagAliasRepository
from chronovista.repositories.tag_operation_log_repository import (
    TagOperationLogRepository,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types — service-layer return types for CLI formatting
# ---------------------------------------------------------------------------


@dataclass
class MergeResult:
    """Result of a merge operation."""

    source_tags: list[str]
    target_tag: str
    aliases_moved: int
    new_alias_count: int
    new_video_count: int
    operation_id: uuid.UUID
    entity_hint: Optional[str] = None


@dataclass
class SplitResult:
    """Result of a split operation."""

    original_tag: str
    new_tag: str
    new_canonical_form: str
    new_normalized_form: str
    aliases_moved: int
    original_alias_count: int
    original_video_count: int
    new_alias_count: int
    new_video_count: int
    operation_id: uuid.UUID


@dataclass
class RenameResult:
    """Result of a rename operation."""

    normalized_form: str
    old_form: str
    new_form: str
    operation_id: uuid.UUID


@dataclass
class ClassifyResult:
    """Result of a classify operation."""

    normalized_form: str
    canonical_form: str
    entity_type: str
    entity_created: bool
    entity_alias_count: int
    operation_id: uuid.UUID


@dataclass
class DeprecateResult:
    """Result of a deprecate operation."""

    normalized_form: str
    canonical_form: str
    alias_count: int
    operation_id: uuid.UUID


@dataclass
class UndoResult:
    """Result of an undo operation."""

    operation_type: str
    operation_id: uuid.UUID
    details: str


@dataclass
class CollisionGroup:
    """A group of aliases that may represent a diacritic collision."""

    canonical_form: str
    normalized_form: str
    canonical_tag_id: uuid.UUID
    aliases: list[dict[str, Any]] = field(default_factory=list)
    total_occurrence_count: int = 0


class UndoNotImplementedError(Exception):
    """Raised when undo for a specific operation type is not yet implemented."""

    pass


class TagManagementService:
    """
    Service for managing canonical tags via CLI curation operations.

    All operations are atomic (single transaction), logged with self-contained
    rollback data, and reversible via the undo mechanism.
    """

    def __init__(
        self,
        canonical_tag_repo: CanonicalTagRepository,
        tag_alias_repo: TagAliasRepository,
        named_entity_repo: NamedEntityRepository,
        entity_alias_repo: EntityAliasRepository,
        operation_log_repo: TagOperationLogRepository,
    ) -> None:
        self._canonical_tag_repo = canonical_tag_repo
        self._tag_alias_repo = tag_alias_repo
        self._named_entity_repo = named_entity_repo
        self._entity_alias_repo = entity_alias_repo
        self._operation_log_repo = operation_log_repo

    # -------------------------------------------------------------------
    # Shared private utilities
    # -------------------------------------------------------------------

    async def _validate_active_tag(
        self, session: AsyncSession, normalized_form: str
    ) -> CanonicalTagDB:
        """
        Look up a canonical tag by normalized form and validate it is active.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        normalized_form : str
            Normalized form to look up.

        Returns
        -------
        CanonicalTagDB
            The active canonical tag.

        Raises
        ------
        ValueError
            If the tag does not exist or is not active.
        """
        tag = await self._canonical_tag_repo.get_by_normalized_form(
            session, normalized_form
        )
        if tag is None:
            # Check if it exists with any status
            any_status_tag = await self._canonical_tag_repo.get_by_normalized_form(
                session, normalized_form, status="merged"
            )
            if any_status_tag is None:
                any_status_tag = await self._canonical_tag_repo.get_by_normalized_form(
                    session, normalized_form, status="deprecated"
                )
            if any_status_tag is not None:
                raise ValueError(
                    f"Tag '{normalized_form}' exists but has status "
                    f"'{any_status_tag.status}' (expected 'active')"
                )
            raise ValueError(f"Tag '{normalized_form}' not found")
        return tag

    async def _recalculate_counts(
        self, session: AsyncSession, canonical_tag_id: uuid.UUID
    ) -> tuple[int, int]:
        """
        Recalculate alias_count and video_count for a canonical tag.

        Uses COUNT and COUNT DISTINCT queries scoped to the specific tag,
        not a full table recount.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        canonical_tag_id : uuid.UUID
            The canonical tag to recalculate counts for.

        Returns
        -------
        tuple[int, int]
            (alias_count, video_count)
        """
        # alias_count
        alias_result = await session.execute(
            select(func.count()).select_from(TagAliasDB).where(
                TagAliasDB.canonical_tag_id == canonical_tag_id
            )
        )
        alias_count: int = alias_result.scalar_one()

        # video_count via raw_form JOIN
        video_result = await session.execute(
            select(func.count(distinct(VideoTag.video_id)))
            .select_from(VideoTag)
            .join(TagAliasDB, VideoTag.tag == TagAliasDB.raw_form)
            .where(TagAliasDB.canonical_tag_id == canonical_tag_id)
        )
        video_count: int = video_result.scalar_one()

        # Update the canonical tag
        await session.execute(
            update(CanonicalTagDB)
            .where(CanonicalTagDB.id == canonical_tag_id)
            .values(alias_count=alias_count, video_count=video_count)
        )

        return alias_count, video_count

    async def _log_operation(
        self,
        session: AsyncSession,
        *,
        operation_type: str,
        source_ids: list[uuid.UUID],
        target_id: Optional[uuid.UUID],
        alias_ids: list[uuid.UUID],
        reason: Optional[str],
        rollback_data: dict[str, Any],
    ) -> uuid.UUID:
        """
        Create a tag_operation_logs entry for an operation.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        operation_type : str
            One of: merge, split, rename, delete, create.
        source_ids : list[uuid.UUID]
            Source canonical tag IDs involved.
        target_id : Optional[uuid.UUID]
            Target canonical tag ID (if applicable).
        alias_ids : list[uuid.UUID]
            Affected alias IDs.
        reason : Optional[str]
            Human-readable reason for the operation.
        rollback_data : dict[str, Any]
            Self-contained data for reversing the operation.

        Returns
        -------
        uuid.UUID
            The operation log entry ID.
        """
        # Convert UUID objects to strings for JSONB serialization.
        # source_canonical_ids and affected_alias_ids are JSONB columns;
        # Python's json.dumps() cannot serialize uuid.UUID objects.
        serialized_source_ids = [str(s) for s in source_ids]
        serialized_alias_ids = [str(a) for a in alias_ids]

        log_create = TagOperationLogCreate(
            operation_type=operation_type,
            source_canonical_ids=serialized_source_ids,
            target_canonical_id=target_id,
            affected_alias_ids=serialized_alias_ids,
            reason=reason,
            rollback_data=rollback_data,
            performed_by="cli",
        )
        log_entry = await self._operation_log_repo.create(
            session, obj_in=log_create
        )
        logger.info(
            "Operation logged: type=%s, id=%s, sources=%s, target=%s",
            operation_type,
            log_entry.id,
            [str(s) for s in source_ids],
            str(target_id) if target_id else None,
        )
        return log_entry.id

    # -------------------------------------------------------------------
    # Public operation methods (stubs — implemented in later phases)
    # -------------------------------------------------------------------

    async def merge(
        self,
        session: AsyncSession,
        source_normalized_forms: list[str],
        target_normalized_form: str,
        *,
        reason: Optional[str] = None,
    ) -> MergeResult:
        """
        Merge one or more source canonical tags into a target.

        Reassigns all aliases from source tags to the target, marks sources
        as merged, recalculates target counts, and logs the operation with
        self-contained rollback data.

        Parameters
        ----------
        session : AsyncSession
            Database session (caller manages transaction).
        source_normalized_forms : list[str]
            Normalized forms of source tags to merge.
        target_normalized_form : str
            Normalized form of the target tag.
        reason : Optional[str]
            Human-readable reason for the merge.

        Returns
        -------
        MergeResult
            Summary of the merge for CLI display.

        Raises
        ------
        ValueError
            If validation fails (self-merge, missing tags, non-active tags).
        """
        if not source_normalized_forms:
            raise ValueError("At least one source tag is required")

        # Validate target
        target = await self._validate_active_tag(session, target_normalized_form)

        # Validate no self-merge
        for src_form in source_normalized_forms:
            if src_form == target_normalized_form:
                raise ValueError(
                    f"Cannot merge tag '{src_form}' into itself"
                )

        # Validate all sources are active
        sources: list[CanonicalTagDB] = []
        for src_form in source_normalized_forms:
            src = await self._validate_active_tag(session, src_form)
            sources.append(src)

        # Build rollback data
        rollback_sources = []
        all_moved_alias_ids: list[uuid.UUID] = []
        total_aliases_moved = 0

        for src in sources:
            # Get all aliases for this source
            alias_result = await session.execute(
                select(TagAliasDB).where(
                    TagAliasDB.canonical_tag_id == src.id
                )
            )
            source_aliases = list(alias_result.scalars().all())
            alias_ids = [a.id for a in source_aliases]

            rollback_sources.append({
                "canonical_tag_id": str(src.id),
                "previous_status": src.status,
                "previous_alias_count": src.alias_count,
                "previous_video_count": src.video_count,
                "previous_entity_type": (
                    src.entity_type if src.entity_type else None
                ),
                "previous_entity_id": (
                    str(src.entity_id) if src.entity_id else None
                ),
                "alias_ids": [str(a) for a in alias_ids],
            })

            # Reassign aliases to target
            if alias_ids:
                await session.execute(
                    update(TagAliasDB)
                    .where(TagAliasDB.canonical_tag_id == src.id)
                    .values(canonical_tag_id=target.id)
                )
                all_moved_alias_ids.extend(alias_ids)
                total_aliases_moved += len(alias_ids)

            # Mark source as merged
            src.status = TagStatus.MERGED.value
            src.merged_into_id = target.id
            session.add(src)

        rollback_data = {
            "sources": rollback_sources,
            "target": {
                "canonical_tag_id": str(target.id),
                "previous_alias_count": target.alias_count,
                "previous_video_count": target.video_count,
            },
        }

        # Recalculate target counts
        new_alias_count, new_video_count = await self._recalculate_counts(
            session, target.id
        )

        # Log operation
        operation_id = await self._log_operation(
            session,
            operation_type=TagOperationType.MERGE.value,
            source_ids=[s.id for s in sources],
            target_id=target.id,
            alias_ids=all_moved_alias_ids,
            reason=reason,
            rollback_data=rollback_data,
        )

        # FR-005a: entity hint if target is unclassified but sources had types
        entity_hint = None
        if target.entity_type is None:
            source_types = [
                s.entity_type for s in sources if s.entity_type is not None
            ]
            if source_types:
                entity_hint = (
                    f"Source tag(s) had entity type(s): "
                    f"{', '.join(source_types)}. "
                    f"Consider classifying target '{target_normalized_form}'."
                )

        logger.info(
            "Merge complete: %s -> %s, %d aliases moved",
            [s.normalized_form for s in sources],
            target_normalized_form,
            total_aliases_moved,
        )

        return MergeResult(
            source_tags=[s.normalized_form for s in sources],
            target_tag=target_normalized_form,
            aliases_moved=total_aliases_moved,
            new_alias_count=new_alias_count,
            new_video_count=new_video_count,
            operation_id=operation_id,
            entity_hint=entity_hint,
        )

    async def split(
        self,
        session: AsyncSession,
        normalized_form: str,
        alias_raw_forms: list[str],
        *,
        reason: Optional[str] = None,
    ) -> SplitResult:
        """
        Split specific aliases from a canonical tag into a new canonical tag.

        Creates a new canonical tag from the specified aliases, using the
        existing select_canonical_form algorithm and TagNormalizationService
        for normalized form computation.

        Parameters
        ----------
        session : AsyncSession
            Database session (caller manages transaction).
        normalized_form : str
            Normalized form of the source tag to split from.
        alias_raw_forms : list[str]
            Raw forms of aliases to move to the new tag.
        reason : Optional[str]
            Human-readable reason for the split.

        Returns
        -------
        SplitResult
            Summary of the split for CLI display.

        Raises
        ------
        ValueError
            If validation fails.
        """
        from chronovista.services.tag_normalization import TagNormalizationService

        if not alias_raw_forms:
            raise ValueError("At least one alias must be specified for split")

        # Validate source tag is active
        source_tag = await self._validate_active_tag(session, normalized_form)

        # Get all aliases for the source tag
        all_aliases_result = await session.execute(
            select(TagAliasDB).where(
                TagAliasDB.canonical_tag_id == source_tag.id
            )
        )
        all_aliases = list(all_aliases_result.scalars().all())
        all_raw_forms = {a.raw_form for a in all_aliases}

        # Validate all specified aliases belong to this tag (all-or-nothing FR-010)
        invalid_aliases = [
            rf for rf in alias_raw_forms if rf not in all_raw_forms
        ]
        if invalid_aliases:
            raise ValueError(
                f"Alias(es) not found on tag '{normalized_form}': "
                f"{', '.join(invalid_aliases)}"
            )

        # Ensure at least one alias remains on the original tag
        remaining_count = len(all_aliases) - len(alias_raw_forms)
        if remaining_count < 1:
            raise ValueError(
                f"Cannot split all aliases from '{normalized_form}'. "
                "At least one alias must remain. Use 'deprecate' to remove a tag entirely."
            )

        # Select canonical form from moved aliases using existing algorithm
        normalization_service = TagNormalizationService()
        moved_aliases = [
            a for a in all_aliases if a.raw_form in alias_raw_forms
        ]
        forms_with_counts = [
            (a.raw_form, a.occurrence_count) for a in moved_aliases
        ]
        new_canonical_form = normalization_service.select_canonical_form(
            forms_with_counts
        )

        # Compute normalized form
        new_normalized_form = normalization_service.normalize(new_canonical_form)
        if new_normalized_form is None:
            raise ValueError(
                f"Normalization of '{new_canonical_form}' produced empty result"
            )

        # Check for collision with existing active or deprecated tag (FR-010)
        existing = await self._canonical_tag_repo.get_by_normalized_form(
            session, new_normalized_form
        )
        if existing is not None:
            raise ValueError(
                f"Normalized form '{new_normalized_form}' already exists as an "
                f"active canonical tag. Consider using 'merge' instead."
            )
        # Also check deprecated
        existing_deprecated = await self._canonical_tag_repo.get_by_normalized_form(
            session, new_normalized_form, status="deprecated"
        )
        if existing_deprecated is not None:
            raise ValueError(
                f"Normalized form '{new_normalized_form}' already exists as a "
                f"deprecated canonical tag."
            )

        # Create new canonical tag
        from chronovista.models.canonical_tag import CanonicalTagCreate

        new_tag_create = CanonicalTagCreate(
            canonical_form=new_canonical_form,
            normalized_form=new_normalized_form,
            alias_count=0,
            video_count=0,
        )
        new_tag = await self._canonical_tag_repo.create(
            session, obj_in=new_tag_create
        )

        # Reassign aliases to the new tag
        moved_alias_ids = [a.id for a in moved_aliases]
        await session.execute(
            update(TagAliasDB)
            .where(TagAliasDB.id.in_(moved_alias_ids))
            .values(canonical_tag_id=new_tag.id)
        )

        # Build rollback data
        rollback_data = {
            "original_canonical_id": str(source_tag.id),
            "created_canonical_id": str(new_tag.id),
            "moved_alias_ids": [str(a) for a in moved_alias_ids],
            "previous_counts": {
                "original_alias_count": source_tag.alias_count,
                "original_video_count": source_tag.video_count,
            },
        }

        # Recalculate counts on both tags
        orig_alias_count, orig_video_count = await self._recalculate_counts(
            session, source_tag.id
        )
        new_alias_count, new_video_count = await self._recalculate_counts(
            session, new_tag.id
        )

        # Log operation
        operation_id = await self._log_operation(
            session,
            operation_type=TagOperationType.SPLIT.value,
            source_ids=[source_tag.id],
            target_id=new_tag.id,
            alias_ids=moved_alias_ids,
            reason=reason,
            rollback_data=rollback_data,
        )

        logger.info(
            "Split complete: %s -> %s, %d aliases moved",
            normalized_form,
            new_normalized_form,
            len(moved_alias_ids),
        )

        return SplitResult(
            original_tag=normalized_form,
            new_tag=new_normalized_form,
            new_canonical_form=new_canonical_form,
            new_normalized_form=new_normalized_form,
            aliases_moved=len(moved_alias_ids),
            original_alias_count=orig_alias_count,
            original_video_count=orig_video_count,
            new_alias_count=new_alias_count,
            new_video_count=new_video_count,
            operation_id=operation_id,
        )

    async def undo(
        self,
        session: AsyncSession,
        operation_id: uuid.UUID,
    ) -> UndoResult:
        """
        Undo a previously logged operation.

        Looks up the operation by ID, dispatches to the appropriate undo
        handler based on operation type, marks the log entry as rolled back,
        and returns a summary for CLI display.

        Parameters
        ----------
        session : AsyncSession
            Database session (caller manages transaction).
        operation_id : uuid.UUID
            The operation log entry ID to undo.

        Returns
        -------
        UndoResult
            Summary of the undo for CLI display.

        Raises
        ------
        ValueError
            If the operation is not found, already undone, or has an unknown type.
        UndoNotImplementedError
            If undo for the operation type is not yet implemented.
        """
        # Look up the operation
        log_entry = await self._operation_log_repo.get(session, operation_id)
        if log_entry is None:
            raise ValueError(f"Operation '{operation_id}' not found")

        if log_entry.rolled_back is True:
            raise ValueError(
                f"Operation '{operation_id}' has already been undone"
            )

        # Dispatch based on operation type
        op_type = log_entry.operation_type
        if op_type == TagOperationType.MERGE.value:
            details = await self._undo_merge(session, log_entry)
        elif op_type == TagOperationType.SPLIT.value:
            details = await self._undo_split(session, log_entry)
        elif op_type == TagOperationType.RENAME.value:
            details = await self._undo_rename(session, log_entry)
        elif op_type == TagOperationType.CREATE.value:
            details = await self._undo_classify(session, log_entry)
        elif op_type == TagOperationType.DELETE.value:
            details = await self._undo_deprecate(session, log_entry)
        else:
            raise ValueError(f"Unknown operation type: {op_type}")

        # Mark the log entry as rolled back
        log_entry.rolled_back = True
        log_entry.rolled_back_at = datetime.now(timezone.utc)
        session.add(log_entry)

        logger.info(
            "Undo complete: type=%s, operation_id=%s",
            op_type,
            operation_id,
        )

        return UndoResult(
            operation_type=op_type,
            operation_id=operation_id,
            details=details,
        )

    async def list_recent_operations(
        self,
        session: AsyncSession,
        *,
        limit: int = 20,
    ) -> list[TagOperationLogDB]:
        """List recent operations from the audit log."""
        return await self._operation_log_repo.get_recent(session, limit=limit)

    async def rename(
        self,
        session: AsyncSession,
        normalized_form: str,
        new_display_form: str,
        *,
        reason: Optional[str] = None,
    ) -> RenameResult:
        """
        Rename a canonical tag's display form (canonical_form).

        Updates the canonical_form on the tag without changing the
        normalized_form or any alias mappings. Logged with rollback data
        for undo capability.

        Parameters
        ----------
        session : AsyncSession
            Database session (caller manages transaction).
        normalized_form : str
            Normalized form of the tag to rename.
        new_display_form : str
            New display form (canonical_form) for the tag.
        reason : Optional[str]
            Human-readable reason for the rename.

        Returns
        -------
        RenameResult
            Summary of the rename for CLI display.

        Raises
        ------
        ValueError
            If the tag is not found/active or new_display_form is empty.
        """
        # Validate new display form is not empty
        new_display_form = new_display_form.strip()
        if not new_display_form:
            raise ValueError("New display form cannot be empty")

        # Validate tag is active
        tag = await self._validate_active_tag(session, normalized_form)

        old_form = tag.canonical_form

        # Update canonical_form
        tag.canonical_form = new_display_form
        session.add(tag)

        # Build rollback data
        rollback_data = {
            "canonical_id": str(tag.id),
            "previous_form": old_form,
            "new_form": new_display_form,
        }

        # Log operation
        operation_id = await self._log_operation(
            session,
            operation_type=TagOperationType.RENAME.value,
            source_ids=[tag.id],
            target_id=None,
            alias_ids=[],
            reason=reason,
            rollback_data=rollback_data,
        )

        logger.info(
            "Rename complete: '%s' -> '%s' (normalized: %s)",
            old_form,
            new_display_form,
            normalized_form,
        )

        return RenameResult(
            normalized_form=normalized_form,
            old_form=old_form,
            new_form=new_display_form,
            operation_id=operation_id,
        )

    async def classify(
        self,
        session: AsyncSession,
        normalized_form: str,
        entity_type: EntityType,
        *,
        force: bool = False,
        reason: Optional[str] = None,
    ) -> ClassifyResult:
        """
        Classify a canonical tag with an entity type.

        For entity-producing types (person, organization, place, event, work,
        technical_term), creates or links a NamedEntity record and copies
        tag aliases as entity aliases. For tag-only types (topic, descriptor),
        only sets entity_type on the canonical tag with no entity record.

        Parameters
        ----------
        session : AsyncSession
            Database session (caller manages transaction).
        normalized_form : str
            Normalized form of the tag to classify.
        entity_type : EntityType
            The entity type to assign.
        force : bool
            If True, override existing classification.
        reason : Optional[str]
            Human-readable reason for the classification.

        Returns
        -------
        ClassifyResult
            Summary of the classification for CLI display.

        Raises
        ------
        ValueError
            If the tag is not found/active or already classified without force.
        """
        from chronovista.models.entity_alias import EntityAliasCreate
        from chronovista.models.named_entity import NamedEntityCreate

        # 1. Validate tag is active
        tag = await self._validate_active_tag(session, normalized_form)

        # 2. Check existing classification
        previous_entity_type = tag.entity_type
        if previous_entity_type is not None and not force:
            raise ValueError(
                f"Tag '{normalized_form}' is already classified as "
                f"'{previous_entity_type}'. Use --force to override."
            )

        if previous_entity_type is not None and force:
            # If old entity was user_created, delete it and its aliases
            if tag.entity_id is not None:
                old_entity = await self._named_entity_repo.get(
                    session, tag.entity_id
                )
                if (
                    old_entity is not None
                    and old_entity.discovery_method
                    == DiscoveryMethod.USER_CREATED.value
                ):
                    # Delete entity aliases for old entity
                    old_aliases_result = await session.execute(
                        select(EntityAliasDB).where(
                            EntityAliasDB.entity_id == old_entity.id
                        )
                    )
                    for old_alias in old_aliases_result.scalars().all():
                        await session.delete(old_alias)
                    await session.flush()
                    # Delete the entity itself
                    await session.delete(old_entity)
                    await session.flush()

            # Clear entity_type and entity_id on the tag
            tag.entity_type = None
            tag.entity_id = None

        # 3. Determine entity-producing vs tag-only types
        entity_producing_types = {
            EntityType.PERSON,
            EntityType.ORGANIZATION,
            EntityType.PLACE,
            EntityType.EVENT,
            EntityType.WORK,
            EntityType.TECHNICAL_TERM,
        }
        tag_only_types = {EntityType.TOPIC, EntityType.DESCRIPTOR}

        created_entity_id: Optional[uuid.UUID] = None
        linked_existing_entity_id: Optional[uuid.UUID] = None
        created_entity_alias_ids: list[uuid.UUID] = []
        entity_created = False

        if entity_type in entity_producing_types:
            # 4. Check if a named_entity already exists with same name and type
            existing_entity_result = await session.execute(
                select(NamedEntityDB).where(
                    NamedEntityDB.canonical_name_normalized
                    == tag.normalized_form,
                    NamedEntityDB.entity_type == entity_type.value,
                )
            )
            existing_entity = existing_entity_result.scalar_one_or_none()

            if existing_entity is not None:
                # Link to existing entity
                tag.entity_type = entity_type.value
                tag.entity_id = existing_entity.id
                linked_existing_entity_id = existing_entity.id
            else:
                # Create new NamedEntity
                entity_create = NamedEntityCreate(
                    canonical_name=tag.canonical_form,
                    canonical_name_normalized=tag.normalized_form,
                    entity_type=entity_type,
                    discovery_method=DiscoveryMethod.USER_CREATED,
                    confidence=1.0,
                )
                new_entity = await self._named_entity_repo.create(
                    session, obj_in=entity_create
                )
                tag.entity_type = entity_type.value
                tag.entity_id = new_entity.id
                created_entity_id = new_entity.id
                entity_created = True

            # Copy tag_aliases as entity_aliases
            tag_aliases_result = await session.execute(
                select(TagAliasDB).where(
                    TagAliasDB.canonical_tag_id == tag.id
                )
            )
            tag_aliases = list(tag_aliases_result.scalars().all())

            entity_id_for_aliases = tag.entity_id
            # Track normalized forms we've already seen to handle
            # multiple tag aliases that normalize to the same form
            # (e.g., "Aaron Mate" and "Aaron Maté" both → "aaron mate").
            # FR-019: upsert semantics — update occurrence_count on conflict.
            seen_normalized: dict[str, EntityAliasDB] = {}
            for tag_alias in tag_aliases:
                norm = tag_alias.normalized_form
                if norm in seen_normalized:
                    # Same normalized form already inserted in this batch —
                    # accumulate occurrence_count on the existing record.
                    existing_ea = seen_normalized[norm]
                    existing_ea.occurrence_count = (
                        (existing_ea.occurrence_count or 0)
                        + (tag_alias.occurrence_count or 0)
                    )
                    session.add(existing_ea)
                    continue

                # Check if entity alias already exists in DB
                existing_result = await session.execute(
                    select(EntityAliasDB).where(
                        EntityAliasDB.entity_id == entity_id_for_aliases,
                        EntityAliasDB.alias_name_normalized == norm,
                    )
                )
                existing_db = existing_result.scalar_one_or_none()
                if existing_db is not None:
                    # Upsert: update occurrence_count on existing record
                    existing_db.occurrence_count = (
                        (existing_db.occurrence_count or 0)
                        + (tag_alias.occurrence_count or 0)
                    )
                    session.add(existing_db)
                    seen_normalized[norm] = existing_db
                    # Don't add to created_entity_alias_ids — pre-existing
                    continue

                ea_create = EntityAliasCreate(
                    entity_id=entity_id_for_aliases,
                    alias_name=tag_alias.raw_form,
                    alias_name_normalized=norm,
                    alias_type=EntityAliasType.NAME_VARIANT,
                    occurrence_count=tag_alias.occurrence_count,
                )
                ea_db = await self._entity_alias_repo.create(
                    session, obj_in=ea_create
                )
                created_entity_alias_ids.append(ea_db.id)
                seen_normalized[norm] = ea_db

        elif entity_type in tag_only_types:
            # 5. Tag-only types: set entity_type only
            tag.entity_type = entity_type.value
            # No entity record, no entity_aliases, entity_id stays None

        session.add(tag)

        # 6. Build rollback_data
        rollback_data: dict[str, Any] = {
            "canonical_id": str(tag.id),
            "previous_entity_type": previous_entity_type,
            "new_entity_type": entity_type.value,
            "created_entity_id": (
                str(created_entity_id) if created_entity_id else None
            ),
            "linked_existing_entity_id": (
                str(linked_existing_entity_id)
                if linked_existing_entity_id
                else None
            ),
            "created_entity_alias_ids": [
                str(ea_id) for ea_id in created_entity_alias_ids
            ],
        }

        # 7. Log operation
        operation_id = await self._log_operation(
            session,
            operation_type=TagOperationType.CREATE.value,
            source_ids=[tag.id],
            target_id=None,
            alias_ids=[],
            reason=reason,
            rollback_data=rollback_data,
        )

        logger.info(
            "Classify complete: %s -> %s (entity_created=%s, aliases=%d)",
            normalized_form,
            entity_type.value,
            entity_created,
            len(created_entity_alias_ids),
        )

        # 8. Return ClassifyResult
        return ClassifyResult(
            normalized_form=normalized_form,
            canonical_form=tag.canonical_form,
            entity_type=entity_type.value,
            entity_created=entity_created,
            entity_alias_count=len(created_entity_alias_ids),
            operation_id=operation_id,
        )

    async def classify_top_unclassified(
        self,
        session: AsyncSession,
        *,
        limit: int = 20,
    ) -> list[CanonicalTagDB]:
        """
        Get top unclassified canonical tags by video count.

        Queries active canonical tags that have no entity_type set,
        ordered by video_count descending so the most impactful tags
        are surfaced first for classification.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        limit : int
            Maximum number of tags to return (default 20).

        Returns
        -------
        list[CanonicalTagDB]
            Unclassified active canonical tags, ordered by video_count desc.
        """
        result = await session.execute(
            select(CanonicalTagDB)
            .where(CanonicalTagDB.entity_type.is_(None))
            .where(CanonicalTagDB.status == TagStatus.ACTIVE.value)
            .order_by(CanonicalTagDB.video_count.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_collisions(
        self,
        session: AsyncSession,
        *,
        limit: Optional[int] = None,
        include_reviewed: bool = False,
    ) -> list[CollisionGroup]:
        """
        Get diacritic collision candidates from active canonical tags.

        Detects groups where a single canonical tag has aliases whose
        casefolded forms (after stripping # and whitespace but preserving
        diacritics) are distinct — indicating potential false merges from
        Tier 1 diacritic stripping.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        limit : Optional[int]
            Maximum number of collision groups to return.
        include_reviewed : bool
            If True, include collisions that have been previously reviewed
            (marked via collision_reviewed log entries).

        Returns
        -------
        list[CollisionGroup]
            Collision candidates sorted by total occurrence count descending.
        """
        # Query all active canonical tags with their aliases
        result = await session.execute(
            select(CanonicalTagDB).where(
                CanonicalTagDB.status == TagStatus.ACTIVE.value
            )
        )
        active_tags = list(result.scalars().all())

        # Get reviewed collision tag IDs (if filtering)
        reviewed_tag_ids: set[str] = set()
        if not include_reviewed:
            reviewed_result = await session.execute(
                select(TagOperationLogDB).where(
                    TagOperationLogDB.operation_type == TagOperationType.CREATE.value,
                    TagOperationLogDB.reason == "collision_reviewed",
                    TagOperationLogDB.rolled_back == False,  # noqa: E712
                )
            )
            for log_entry in reviewed_result.scalars().all():
                if log_entry.source_canonical_ids:
                    for sid in log_entry.source_canonical_ids:
                        reviewed_tag_ids.add(str(sid))

        collisions: list[CollisionGroup] = []

        for tag in active_tags:
            if not include_reviewed and str(tag.id) in reviewed_tag_ids:
                continue

            # Get aliases for this tag
            alias_result = await session.execute(
                select(TagAliasDB).where(
                    TagAliasDB.canonical_tag_id == tag.id
                )
            )
            aliases = list(alias_result.scalars().all())

            if len(aliases) < 2:
                continue

            # Detect collision: distinct casefolded forms (preserving diacritics)
            casefolded_set: set[str] = set()
            for alias in aliases:
                cleaned = alias.raw_form.strip()
                if cleaned.startswith("#"):
                    cleaned = cleaned[1:]
                cleaned = cleaned.strip().casefold()
                casefolded_set.add(cleaned)

            if len(casefolded_set) < 2:
                continue

            total_count = sum(a.occurrence_count for a in aliases)

            collisions.append(
                CollisionGroup(
                    canonical_form=tag.canonical_form,
                    normalized_form=tag.normalized_form,
                    canonical_tag_id=tag.id,
                    aliases=[
                        {
                            "raw_form": a.raw_form,
                            "occurrence_count": a.occurrence_count,
                        }
                        for a in aliases
                    ],
                    total_occurrence_count=total_count,
                )
            )

        # Sort by total occurrence count descending
        collisions.sort(key=lambda c: c.total_occurrence_count, reverse=True)

        if limit is not None:
            collisions = collisions[:limit]

        return collisions

    async def log_collision_reviewed(
        self,
        session: AsyncSession,
        canonical_tag_id: uuid.UUID,
    ) -> uuid.UUID:
        """
        Log that a collision was reviewed and kept as-is.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        canonical_tag_id : uuid.UUID
            The canonical tag that was reviewed.

        Returns
        -------
        uuid.UUID
            The operation log entry ID.
        """
        return await self._log_operation(
            session,
            operation_type=TagOperationType.CREATE.value,
            source_ids=[canonical_tag_id],
            target_id=None,
            alias_ids=[],
            reason="collision_reviewed",
            rollback_data={"canonical_id": str(canonical_tag_id)},
        )

    async def deprecate(
        self,
        session: AsyncSession,
        normalized_form: str,
        *,
        reason: Optional[str] = None,
    ) -> DeprecateResult:
        """
        Deprecate a canonical tag (soft delete).

        Sets the tag status to deprecated, preserving all aliases and
        video associations. The operation is logged and reversible via undo.

        Parameters
        ----------
        session : AsyncSession
            Database session (caller manages transaction).
        normalized_form : str
            Normalized form of the tag to deprecate.
        reason : Optional[str]
            Human-readable reason for the deprecation.

        Returns
        -------
        DeprecateResult
            Summary of the deprecation for CLI display.

        Raises
        ------
        ValueError
            If the tag does not exist or is not active.
        """
        # Validate tag is active (rejects merged/deprecated)
        tag = await self._validate_active_tag(session, normalized_form)

        # Build rollback data before mutation
        rollback_data: dict[str, Any] = {
            "canonical_id": str(tag.id),
            "previous_status": tag.status,
        }

        # Mark as deprecated
        tag.status = TagStatus.DEPRECATED.value
        session.add(tag)

        # Log operation (operation_type=DELETE per spec)
        operation_id = await self._log_operation(
            session,
            operation_type=TagOperationType.DELETE.value,
            source_ids=[tag.id],
            target_id=None,
            alias_ids=[],
            reason=reason,
            rollback_data=rollback_data,
        )

        logger.info(
            "Deprecate complete: %s (canonical: %s), alias_count=%d",
            normalized_form,
            tag.canonical_form,
            tag.alias_count,
        )

        return DeprecateResult(
            normalized_form=normalized_form,
            canonical_form=tag.canonical_form,
            alias_count=tag.alias_count,
            operation_id=operation_id,
        )

    async def list_deprecated(
        self,
        session: AsyncSession,
    ) -> list[CanonicalTagDB]:
        """
        List all deprecated canonical tags.

        Parameters
        ----------
        session : AsyncSession
            Database session.

        Returns
        -------
        list[CanonicalTagDB]
            All canonical tags with status 'deprecated', ordered by
            canonical_form alphabetically.
        """
        result = await session.execute(
            select(CanonicalTagDB)
            .where(CanonicalTagDB.status == TagStatus.DEPRECATED.value)
            .order_by(CanonicalTagDB.canonical_form)
        )
        return list(result.scalars().all())

    # -------------------------------------------------------------------
    # Private undo reversal methods (stubs — implemented per phase)
    # -------------------------------------------------------------------

    async def _undo_merge(
        self, session: AsyncSession, log_entry: TagOperationLogDB
    ) -> str:
        """
        Reverse a merge operation.

        Reassigns aliases back to their original source canonical tags,
        restores source status to active, clears merged_into_id, and
        recalculates counts on all affected tags.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        log_entry : TagOperationLogDB
            The operation log entry with rollback_data.

        Returns
        -------
        str
            Human-readable description of what was reversed.
        """
        rollback = log_entry.rollback_data
        sources = rollback["sources"]
        target_info = rollback["target"]
        target_id = uuid.UUID(target_info["canonical_tag_id"])

        restored_tags = []

        for source_data in sources:
            source_id = uuid.UUID(source_data["canonical_tag_id"])
            alias_ids = [uuid.UUID(a) for a in source_data["alias_ids"]]

            # Reassign aliases back to the source
            if alias_ids:
                for alias_id in alias_ids:
                    await session.execute(
                        update(TagAliasDB)
                        .where(TagAliasDB.id == alias_id)
                        .values(canonical_tag_id=source_id)
                    )

            # Restore source tag to active
            source_tag = await self._canonical_tag_repo.get(session, source_id)
            if source_tag is not None:
                source_tag.status = TagStatus.ACTIVE.value
                source_tag.merged_into_id = None
                session.add(source_tag)

                # Recalculate counts on source
                await self._recalculate_counts(session, source_id)
                restored_tags.append(source_tag.normalized_form)

        # Recalculate counts on target
        await self._recalculate_counts(session, target_id)

        return f"Unmerged {', '.join(restored_tags)} from target"

    async def _undo_split(
        self, session: AsyncSession, log_entry: TagOperationLogDB
    ) -> str:
        """
        Reverse a split operation.

        Moves aliases back to the original canonical tag, deletes the
        created canonical tag, and recalculates counts. Blocked if the
        created tag has subsequent non-rolled-back operations (FR-012a).

        Parameters
        ----------
        session : AsyncSession
            Database session.
        log_entry : TagOperationLogDB
            The operation log entry with rollback_data.

        Returns
        -------
        str
            Human-readable description of what was reversed.

        Raises
        ------
        ValueError
            If the created tag has subsequent operations (FR-012a).
        """
        rollback = log_entry.rollback_data
        original_id = uuid.UUID(rollback["original_canonical_id"])
        created_id = uuid.UUID(rollback["created_canonical_id"])
        moved_alias_ids = [uuid.UUID(a) for a in rollback["moved_alias_ids"]]

        # FR-012a: Check for subsequent operations on the created tag
        subsequent_ops_result = await session.execute(
            select(TagOperationLogDB).where(
                TagOperationLogDB.id != log_entry.id,
                TagOperationLogDB.rolled_back == False,  # noqa: E712
                (
                    TagOperationLogDB.source_canonical_ids.contains(
                        [str(created_id)]
                    )
                    | (TagOperationLogDB.target_canonical_id == created_id)
                ),
            )
        )
        subsequent_ops = list(subsequent_ops_result.scalars().all())
        if subsequent_ops:
            op_types = [op.operation_type for op in subsequent_ops]
            raise ValueError(
                f"Cannot undo split: tag created by this split has "
                f"{len(subsequent_ops)} subsequent operation(s) "
                f"({', '.join(op_types)}). Undo those operations first."
            )

        # Move aliases back to original
        if moved_alias_ids:
            for alias_id in moved_alias_ids:
                await session.execute(
                    update(TagAliasDB)
                    .where(TagAliasDB.id == alias_id)
                    .values(canonical_tag_id=original_id)
                )

        # Delete the created canonical tag
        created_tag = await self._canonical_tag_repo.get(session, created_id)
        if created_tag is not None:
            await session.delete(created_tag)
            await session.flush()

        # Recalculate counts on original
        await self._recalculate_counts(session, original_id)

        original_tag = await self._canonical_tag_repo.get(session, original_id)
        original_name = (
            original_tag.normalized_form if original_tag else str(original_id)
        )
        return f"Reunited {len(moved_alias_ids)} aliases back into '{original_name}'"

    async def _undo_rename(
        self, session: AsyncSession, log_entry: TagOperationLogDB
    ) -> str:
        """
        Reverse a rename operation.

        Restores the canonical_form to its previous value using the
        rollback data stored in the operation log entry.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        log_entry : TagOperationLogDB
            The operation log entry with rollback_data.

        Returns
        -------
        str
            Human-readable description of what was reversed.
        """
        rollback = log_entry.rollback_data
        canonical_id = uuid.UUID(rollback["canonical_id"])
        previous_form = rollback["previous_form"]
        new_form = rollback["new_form"]

        tag = await self._canonical_tag_repo.get(session, canonical_id)
        if tag is None:
            raise ValueError(
                f"Cannot undo rename: canonical tag {canonical_id} not found"
            )

        tag.canonical_form = previous_form
        session.add(tag)

        return f"Renamed '{new_form}' back to '{previous_form}'"

    async def _undo_classify(
        self, session: AsyncSession, log_entry: TagOperationLogDB
    ) -> str:
        """
        Reverse a classify operation.

        Clears entity_type and entity_id on the canonical tag. If a new
        entity was created (created_entity_id), deletes its entity aliases
        and the entity itself (only if user_created). If an existing entity
        was linked (linked_existing_entity_id), only clears the link and
        deletes entity aliases that were created during the classify.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        log_entry : TagOperationLogDB
            The operation log entry with rollback_data.

        Returns
        -------
        str
            Human-readable description of what was reversed.

        Raises
        ------
        ValueError
            If the canonical tag cannot be found.
        """
        rollback = log_entry.rollback_data
        canonical_id = uuid.UUID(rollback["canonical_id"])
        previous_entity_type = rollback.get("previous_entity_type")
        created_entity_id_str = rollback.get("created_entity_id")
        linked_existing_entity_id_str = rollback.get("linked_existing_entity_id")
        created_entity_alias_ids = [
            uuid.UUID(ea_id)
            for ea_id in rollback.get("created_entity_alias_ids", [])
        ]

        # Look up the canonical tag
        tag = await self._canonical_tag_repo.get(session, canonical_id)
        if tag is None:
            raise ValueError(
                f"Cannot undo classify: canonical tag {canonical_id} not found"
            )

        # Clear entity_type and entity_id on the tag
        tag.entity_type = previous_entity_type
        tag.entity_id = None
        session.add(tag)

        # Delete created entity aliases
        if created_entity_alias_ids:
            for ea_id in created_entity_alias_ids:
                ea = await self._entity_alias_repo.get(session, ea_id)
                if ea is not None:
                    await session.delete(ea)
            await session.flush()

        if created_entity_id_str is not None:
            # We created a new entity — delete it if user_created
            created_entity_id = uuid.UUID(created_entity_id_str)
            entity = await self._named_entity_repo.get(
                session, created_entity_id
            )
            if (
                entity is not None
                and entity.discovery_method
                == DiscoveryMethod.USER_CREATED.value
            ):
                await session.delete(entity)
                await session.flush()

        # If linked_existing_entity_id, we only clear the link (already done above)
        # and deleted the created aliases (also done above). No entity deletion.

        new_entity_type = rollback.get("new_entity_type", "unknown")
        return (
            f"Unclassified '{tag.normalized_form}' "
            f"(removed type '{new_entity_type}')"
        )

    async def _undo_deprecate(
        self, session: AsyncSession, log_entry: TagOperationLogDB
    ) -> str:
        """
        Reverse a deprecate operation.

        Restores the canonical tag's status to its previous value
        (typically 'active') using the rollback data stored in the
        operation log entry.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        log_entry : TagOperationLogDB
            The operation log entry with rollback_data.

        Returns
        -------
        str
            Human-readable description of what was reversed.

        Raises
        ------
        ValueError
            If the canonical tag cannot be found.
        """
        rollback = log_entry.rollback_data
        canonical_id = uuid.UUID(rollback["canonical_id"])
        previous_status = rollback["previous_status"]

        tag = await self._canonical_tag_repo.get(session, canonical_id)
        if tag is None:
            raise ValueError(
                f"Cannot undo deprecate: canonical tag {canonical_id} not found"
            )

        tag.status = previous_status
        session.add(tag)

        return (
            f"Restored '{tag.normalized_form}' from deprecated to {previous_status}"
        )
