"""
Entity curation service — edit a named entity's display name / description.

Owns the multi-step business logic for editing an entity's ``canonical_name``
and/or ``description``: trim + validation, normalized-form recompute,
same-type collision pre-check, persistence, and an append-only audit/rollback
log with an undo path (Feature 057, FR-001..FR-020).

This service never touches the tag(s) an entity was derived from (FR-003),
never modifies the entity's aliases (FR-015), and never rewrites existing
entity-mention records (FR-020).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.entity_operation_log import (
    EntityEditRollback,
    EntityEditSnapshot,
    EntityOperationLogCreate,
)
from chronovista.models.enums import EntityType
from chronovista.models.named_entity import NamedEntityUpdate
from chronovista.repositories.entity_operation_log_repository import (
    EntityOperationLogRepository,
)
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.services.tag_normalization import TagNormalizationService

logger = logging.getLogger(__name__)

_MAX_NAME_LENGTH = 500


class EntityCurationError(Exception):
    """Base class for entity curation domain errors."""


class EntityNotFoundError(EntityCurationError):
    """The target entity does not exist (maps to HTTP 404).

    Carries the missing entity's id so callers (e.g. the undo endpoint, which
    only knows the operation id) can label the 404 with the correct identifier.
    """

    def __init__(self, message: str, *, entity_id: uuid.UUID) -> None:
        super().__init__(message)
        self.entity_id = entity_id


class InvalidEntityEditError(EntityCurationError):
    """The requested edit is invalid (maps to HTTP 400)."""


class EntityNameCollisionError(EntityCurationError):
    """The new name collides with an existing same-type entity (HTTP 409)."""


class OperationNotFoundError(EntityCurationError):
    """The referenced operation log entry does not exist (HTTP 404)."""


class OperationAlreadyUndoneError(EntityCurationError):
    """The referenced operation was already rolled back (HTTP 409)."""


class EntityCurationService:
    """Service for editing and undoing named-entity name/description edits."""

    def __init__(
        self,
        named_entity_repo: NamedEntityRepository,
        operation_log_repo: EntityOperationLogRepository,
        normalizer: TagNormalizationService | None = None,
    ) -> None:
        """
        Initialize the service with its repositories.

        Parameters
        ----------
        named_entity_repo : NamedEntityRepository
            Repository for reading/updating named entities.
        operation_log_repo : EntityOperationLogRepository
            Repository for the entity-curation audit log.
        normalizer : TagNormalizationService, optional
            Normalization service used to recompute ``canonical_name_normalized``
            (the same one ``classify`` relies on). A default instance is created
            when omitted.
        """
        self._entity_repo = named_entity_repo
        self._operation_log_repo = operation_log_repo
        self._normalizer = normalizer or TagNormalizationService()

    async def update_entity(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        *,
        canonical_name: str | None = None,
        description: str | None = None,
        entity_type: str | None = None,
        actor: str,
    ) -> NamedEntityDB:
        """
        Edit an entity's display name, description, and/or type.

        PATCH semantics: an omitted argument (``None``) leaves that field
        unchanged. Passing ``description=""`` clears the description (a valid,
        distinct value — FR-013). ``canonical_name`` is stored verbatim (only
        leading/trailing whitespace trimmed — FR-013); its normalized form is
        recomputed together with it (INV-1). Aliases and mentions are never
        touched (FR-015, FR-020).

        Uniqueness is a property of the **pair** ``(canonical_name_normalized,
        entity_type)``, so the collision pre-check runs against the values as
        they will be *after* the edit. Checking a renamed entity against its old
        type — or a retyped entity against its old name — would let a duplicate
        through the pre-check and fail at flush time with an IntegrityError
        (→ 500) instead of a clean 409.

        Parameters
        ----------
        session : AsyncSession
            Database session (caller manages the transaction/commit).
        entity_id : uuid.UUID
            The entity to edit.
        canonical_name : str, optional
            New display name (verbatim). Omit to leave unchanged.
        description : str, optional
            New description (empty string clears it). Omit to leave unchanged.
        entity_type : str, optional
            New entity type. Must be a valid ``EntityType``. Omit to leave
            unchanged.
        actor : str
            Actor string recorded in the audit log (e.g. ``"user:local"``).

        Returns
        -------
        NamedEntityDB
            The updated entity.

        Raises
        ------
        InvalidEntityEditError
            No fields provided, the name is empty / too long / normalizes to
            empty, or the entity type is not a valid ``EntityType``.
        EntityNotFoundError
            The entity does not exist.
        EntityNameCollisionError
            The resulting ``(normalized name, entity type)`` pair collides with
            an existing entity.
        """
        if canonical_name is None and description is None and entity_type is None:
            raise InvalidEntityEditError(
                "At least one of 'canonical_name', 'description' or "
                "'entity_type' is required."
            )

        entity = await self._entity_repo.get(session, entity_id)
        if entity is None:
            raise EntityNotFoundError(
                f"Entity '{entity_id}' not found.", entity_id=entity_id
            )

        before = EntityEditSnapshot()
        after = EntityEditSnapshot()
        changed_fields: list[str] = []
        update_fields: dict[str, Any] = {}

        # The values the entity will hold after this edit. Both feed one
        # collision check below, because uniqueness is on the pair.
        effective_normalized = entity.canonical_name_normalized
        effective_type = entity.entity_type
        name_changed = False
        type_changed = False
        trimmed = ""

        if canonical_name is not None:
            trimmed = canonical_name.strip()
            if not trimmed:
                raise InvalidEntityEditError(
                    "Entity name must not be empty after trimming."
                )
            if len(trimmed) > _MAX_NAME_LENGTH:
                raise InvalidEntityEditError(
                    f"Entity name must be at most {_MAX_NAME_LENGTH} characters."
                )
            normalized = self._normalizer.normalize(trimmed)
            if not normalized:
                raise InvalidEntityEditError(
                    "Entity name normalizes to an empty value."
                )
            name_changed = (
                trimmed != entity.canonical_name
                or normalized != entity.canonical_name_normalized
            )
            if name_changed:
                effective_normalized = normalized

        if entity_type is not None:
            valid_types = {t.value for t in EntityType}
            if entity_type not in valid_types:
                raise InvalidEntityEditError(
                    f"Entity type must be one of {sorted(valid_types)}, "
                    f"got {entity_type!r}."
                )
            type_changed = entity_type != entity.entity_type
            if type_changed:
                effective_type = entity_type

        # One check, on the pair as it will be. A rename validated against the
        # old type, or a retype validated against the old name, both miss.
        if name_changed or type_changed:
            await self._assert_no_collision(
                session,
                normalized=effective_normalized,
                entity_type=effective_type,
                exclude_id=entity.id,
            )

        if name_changed:
            before.canonical_name = entity.canonical_name
            before.canonical_name_normalized = entity.canonical_name_normalized
            after.canonical_name = trimmed
            after.canonical_name_normalized = effective_normalized
            changed_fields.append("canonical_name")
            # INV-1: both columns always move together.
            update_fields["canonical_name"] = trimmed
            update_fields["canonical_name_normalized"] = effective_normalized

        if type_changed:
            before.entity_type = entity.entity_type
            after.entity_type = effective_type
            changed_fields.append("entity_type")
            update_fields["entity_type"] = effective_type

        if description is not None and description != entity.description:
            before.description = entity.description
            after.description = description
            changed_fields.append("description")
            update_fields["description"] = description

        # No-op save: identical values → success, no side effects.
        if not changed_fields:
            return entity

        updated = await self._entity_repo.update(
            session,
            db_obj=entity,
            obj_in=NamedEntityUpdate.model_validate(update_fields),
        )

        log_create = EntityOperationLogCreate(
            entity_id=entity_id,
            operation_type="update",
            rollback_data=EntityEditRollback(
                before=before,
                after=after,
                changed_fields=changed_fields,
            ),
            performed_by=actor,
        )
        log_entry = await self._operation_log_repo.create(session, obj_in=log_create)
        logger.info(
            "Entity edit logged: entity=%s, op=%s, fields=%s, actor=%s",
            entity_id,
            log_entry.id,
            changed_fields,
            actor,
        )
        return updated

    async def undo_operation(
        self,
        session: AsyncSession,
        operation_id: uuid.UUID,
        *,
        actor: str,
    ) -> NamedEntityDB:
        """
        Undo a previously logged entity edit, restoring the prior values.

        Restores the ``before`` snapshot for the fields recorded in
        ``changed_fields``, re-checks uniqueness on a restored name, and marks
        the log entry ``rolled_back``. An already-rolled-back entry cannot be
        undone again.

        Parameters
        ----------
        session : AsyncSession
            Database session (caller manages the transaction/commit).
        operation_id : uuid.UUID
            The operation log entry to undo.
        actor : str
            Actor string performing the undo (recorded for observability).

        Returns
        -------
        NamedEntityDB
            The restored entity.

        Raises
        ------
        OperationNotFoundError
            The operation log entry does not exist.
        OperationAlreadyUndoneError
            The operation has already been rolled back.
        EntityNotFoundError
            The referenced entity no longer exists.
        EntityNameCollisionError
            Restoring the name would collide with an existing same-type entity.
        """
        log_entry = await self._operation_log_repo.get(session, operation_id)
        if log_entry is None:
            raise OperationNotFoundError(f"Operation '{operation_id}' not found.")
        if log_entry.rolled_back:
            raise OperationAlreadyUndoneError(
                f"Operation '{operation_id}' has already been rolled back."
            )

        entity = await self._entity_repo.get(session, log_entry.entity_id)
        if entity is None:
            raise EntityNotFoundError(
                f"Entity '{log_entry.entity_id}' not found.",
                entity_id=log_entry.entity_id,
            )

        rollback = EntityEditRollback.model_validate(log_entry.rollback_data)
        before = rollback.before
        update_fields: dict[str, Any] = {}

        # Resolve both restored values before checking, for the same reason the
        # forward edit does: the constraint is on the pair. An undo that
        # restores name and type together must be checked against both.
        restored_normalized = entity.canonical_name_normalized
        restored_type = entity.entity_type

        if "canonical_name" in rollback.changed_fields:
            if (
                before.canonical_name is None
                or before.canonical_name_normalized is None
            ):
                raise InvalidEntityEditError(
                    "Rollback data is missing the previous name."
                )
            restored_normalized = before.canonical_name_normalized

        if "entity_type" in rollback.changed_fields:
            if before.entity_type is None:
                raise InvalidEntityEditError(
                    "Rollback data is missing the previous entity type."
                )
            restored_type = before.entity_type

        if (
            restored_normalized != entity.canonical_name_normalized
            or restored_type != entity.entity_type
        ):
            await self._assert_no_collision(
                session,
                normalized=restored_normalized,
                entity_type=restored_type,
                exclude_id=entity.id,
            )

        if "canonical_name" in rollback.changed_fields:
            update_fields["canonical_name"] = before.canonical_name
            update_fields["canonical_name_normalized"] = restored_normalized

        if "entity_type" in rollback.changed_fields:
            update_fields["entity_type"] = restored_type

        if "description" in rollback.changed_fields:
            update_fields["description"] = before.description

        if update_fields:
            entity = await self._entity_repo.update(
                session,
                db_obj=entity,
                obj_in=NamedEntityUpdate.model_validate(update_fields),
            )

        await self._operation_log_repo.mark_rolled_back(session, operation_id)
        logger.info(
            "Entity edit undone: op=%s, entity=%s, actor=%s",
            operation_id,
            entity.id,
            actor,
        )
        return entity

    async def _assert_no_collision(
        self,
        session: AsyncSession,
        *,
        normalized: str,
        entity_type: str,
        exclude_id: uuid.UUID,
    ) -> None:
        """
        Raise if any same-type entity already owns ``normalized``.

        The check is intentionally NOT scoped by ``status``: the DB unique
        constraint ``uq_named_entity_canonical (canonical_name_normalized,
        entity_type)`` is global, so a merged/deprecated entity's normalized
        name still collides. Scoping the pre-check to active entities would let
        such a rename pass here and then fail with an ``IntegrityError`` (→ 500)
        at flush time; keeping it global surfaces a clean 409 instead.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        normalized : str
            The normalized name to check for collisions.
        entity_type : str
            The entity type that participates in the uniqueness rule.
        exclude_id : uuid.UUID
            The entity being edited (excluded from the collision check).

        Raises
        ------
        EntityNameCollisionError
            If a different same-type entity (any status) has the normalized name.
        """
        result = await session.execute(
            select(NamedEntityDB.id).where(
                NamedEntityDB.canonical_name_normalized == normalized,
                NamedEntityDB.entity_type == entity_type,
                NamedEntityDB.id != exclude_id,
            )
        )
        if result.first() is not None:
            raise EntityNameCollisionError(
                f"A {entity_type} entity with normalized name "
                f"'{normalized}' already exists."
            )
