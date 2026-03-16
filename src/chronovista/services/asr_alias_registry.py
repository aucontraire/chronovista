"""Shared utility for registering ASR error aliases on entity matches.

Both ``TranscriptCorrectionService`` (single-segment) and
``BatchCorrectionService`` (batch find-replace) need to auto-register
ASR error aliases when a correction's replacement text matches a known
entity.  This module provides a single implementation to avoid
duplication.
"""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.entity_alias import EntityAliasCreate
from chronovista.models.enums import EntityAliasType
from chronovista.repositories.entity_alias_repository import EntityAliasRepository
from chronovista.services.tag_normalization import TagNormalizationService

logger = logging.getLogger(__name__)


async def resolve_entity_id_from_text(
    session: AsyncSession,
    text: str,
) -> tuple[UUID, str] | None:
    """Resolve an entity ID from text by matching canonical names then aliases.

    Parameters
    ----------
    session : AsyncSession
        Database session.
    text : str
        Text to match against entity names/aliases (case-insensitive).

    Returns
    -------
    tuple[UUID, str] | None
        ``(entity_id, entity_name)`` if matched, else ``None``.
    """
    normalized_text = text.lower().strip()

    entity_stmt = select(NamedEntityDB).where(
        NamedEntityDB.status == "active",
        func.lower(NamedEntityDB.canonical_name) == normalized_text,
    )
    result = await session.execute(entity_stmt)
    entity = result.scalar_one_or_none()

    if entity is not None:
        return entity.id, entity.canonical_name

    alias_stmt = select(EntityAliasDB).where(
        func.lower(EntityAliasDB.alias_name) == normalized_text,
    )
    alias_result = await session.execute(alias_stmt)
    matched_alias = alias_result.scalars().first()
    if matched_alias is None:
        return None
    return matched_alias.entity_id, text


async def register_asr_alias(
    session: AsyncSession,
    *,
    original_text: str,
    corrected_text: str,
    occurrence_count: int = 1,
    commit: bool = False,
    log_prefix: str = "asr-alias",
) -> None:
    """Best-effort hook: register an ASR error alias when a correction matches an entity.

    If ``corrected_text`` matches a known entity canonical name or alias
    (case-insensitive exact match), register ``original_text`` as an
    ``asr_error`` alias for that entity.  If the alias already exists
    (by normalized form), increment its ``occurrence_count``.

    Parameters
    ----------
    session : AsyncSession
        Database session (caller manages outer transaction).
    original_text : str
        The text that was replaced (potential ASR error form).
    corrected_text : str
        The corrected text that may match an entity name.
    occurrence_count : int
        Number of occurrences to record (default 1 for single-segment,
        batch count for find-replace).
    commit : bool
        Whether to commit after the operation (batch hook needs this,
        single-segment hook does not).
    log_prefix : str
        Prefix for log messages to distinguish callers.
    """
    try:
        match = await resolve_entity_id_from_text(session, corrected_text)
        if match is None:
            return
        entity_id, entity_name = match

        normalizer = TagNormalizationService()
        normalized = normalizer.normalize(original_text) or original_text.lower()

        # Check by normalized form — matches the unique constraint
        existing_alias_stmt = select(EntityAliasDB).where(
            EntityAliasDB.entity_id == entity_id,
            EntityAliasDB.alias_name_normalized == normalized,
        )
        existing_result = await session.execute(existing_alias_stmt)
        existing_alias = existing_result.scalar_one_or_none()

        if existing_alias is not None:
            existing_alias.occurrence_count = (
                existing_alias.occurrence_count or 0
            ) + occurrence_count
            await session.flush()
            if commit:
                await session.commit()
            logger.debug(
                "%s: incremented occurrence_count for alias '%s' on entity '%s' (+%d)",
                log_prefix,
                original_text,
                entity_name,
                occurrence_count,
            )
        else:
            # Use a savepoint so IntegrityError doesn't poison the outer transaction
            async with session.begin_nested():
                new_alias = EntityAliasCreate(
                    entity_id=entity_id,
                    alias_name=original_text,
                    alias_name_normalized=normalized,
                    alias_type=EntityAliasType.ASR_ERROR,
                    occurrence_count=occurrence_count,
                )
                alias_repo = EntityAliasRepository()
                await alias_repo.create(session, obj_in=new_alias)
            if commit:
                await session.commit()
            logger.info(
                "%s: registered ASR alias '%s' for entity '%s' "
                "(occurrence_count=%d)",
                log_prefix,
                original_text,
                entity_name,
                occurrence_count,
            )

        # ----- Word-level diff: register minimal error tokens (T022) -----
        # Only attempt sub-token alias registration when the full-string
        # correction matched an entity.
        try:
            from chronovista.services.batch_correction_service import word_level_diff

            diff = word_level_diff(original_text, corrected_text)
            for error_token, canonical_token in diff.changed_pairs:
                # Skip empty tokens (insertions/deletions) and duplicates of
                # the full-string alias we just registered.
                if (
                    not error_token
                    or not canonical_token
                    or error_token.strip() == original_text.strip()
                ):
                    continue

                sub_normalized = normalizer.normalize(error_token) or error_token.lower()

                # Check if this sub-token alias already exists
                sub_existing_stmt = select(EntityAliasDB).where(
                    EntityAliasDB.entity_id == entity_id,
                    EntityAliasDB.alias_name_normalized == sub_normalized,
                )
                sub_existing_result = await session.execute(sub_existing_stmt)
                sub_existing = sub_existing_result.scalar_one_or_none()

                if sub_existing is not None:
                    sub_existing.occurrence_count = (
                        sub_existing.occurrence_count or 0
                    ) + occurrence_count
                    await session.flush()
                    logger.debug(
                        "%s: incremented sub-token alias '%s' for entity '%s' (+%d)",
                        log_prefix,
                        error_token,
                        entity_name,
                        occurrence_count,
                    )
                else:
                    async with session.begin_nested():
                        sub_alias = EntityAliasCreate(
                            entity_id=entity_id,
                            alias_name=error_token,
                            alias_name_normalized=sub_normalized,
                            alias_type=EntityAliasType.ASR_ERROR,
                            occurrence_count=occurrence_count,
                        )
                        alias_repo_sub = EntityAliasRepository()
                        await alias_repo_sub.create(session, obj_in=sub_alias)
                    logger.info(
                        "%s: registered sub-token ASR alias '%s' for entity '%s'",
                        log_prefix,
                        error_token,
                        entity_name,
                    )

            if commit:
                await session.commit()
        except Exception:
            logger.debug(
                "%s: word-level diff sub-token registration failed (non-blocking)",
                log_prefix,
                exc_info=True,
            )

    except Exception:
        logger.warning(
            "%s hook failed (non-blocking): original_text='%s', corrected_text='%s'",
            log_prefix,
            original_text,
            corrected_text,
            exc_info=True,
        )
