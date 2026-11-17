"""Shared utility for registering ASR error aliases on entity matches.

Both ``TranscriptCorrectionService`` (single-segment) and
``BatchCorrectionService`` (batch find-replace) need to auto-register
ASR error aliases when a correction's replacement text matches a known
entity.  This module provides a single implementation to avoid
duplication.
"""

from __future__ import annotations

import logging
import re
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import (
    ChannelOwnershipAssertion as ChannelOwnershipAssertionDB,
)
from chronovista.db.models import ChannelPrincipal as ChannelPrincipalDB
from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import Video as VideoDB
from chronovista.models.entity_asr_error import EntityAsrErrorCreate
from chronovista.repositories.entity_asr_error_repository import (
    EntityAsrErrorRepository,
)
from chronovista.services.tag_normalization import TagNormalizationService

logger = logging.getLogger(__name__)

# Common English function words.  When every token in a candidate alias
# belongs to this set the alias is almost certainly a false positive
# (e.g. "be out" from "Alan Turner").
_HIGH_FREQUENCY_WORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "not",
        "no",
        "so",
        "is",
        "am",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "shall",
        "should",
        "may",
        "might",
        "can",
        "could",
        "i",
        "me",
        "my",
        "we",
        "us",
        "our",
        "you",
        "your",
        "he",
        "him",
        "his",
        "she",
        "her",
        "it",
        "its",
        "they",
        "them",
        "their",
        "this",
        "that",
        "these",
        "those",
        "in",
        "on",
        "at",
        "to",
        "of",
        "for",
        "by",
        "with",
        "from",
        "up",
        "out",
        "off",
        "over",
        "into",
        "onto",
        "upon",
        "if",
        "then",
        "than",
        "as",
        "while",
        "when",
        "where",
        "how",
        "what",
        "who",
        "whom",
        "which",
        "why",
        "all",
        "each",
        "every",
        "both",
        "few",
        "more",
        "most",
        "some",
        "any",
        "much",
        "many",
        "such",
        "own",
        "other",
        "just",
        "also",
        "very",
        "too",
        "quite",
        "about",
        "still",
        "here",
        "there",
        "now",
        "well",
        "back",
        "get",
        "got",
        "go",
        "going",
        "gone",
        "come",
        "came",
        "make",
        "made",
        "take",
        "took",
        "put",
        "let",
        "say",
        "said",
        "know",
        "think",
        "see",
        "look",
        "want",
        "give",
        "use",
    }
)

# Minimum character length for an alias to be worth registering.
_MIN_ALIAS_LENGTH = 4


def is_valid_asr_alias(alias_text: str) -> bool:
    """Check whether an alias candidate is worth registering.

    Rejects aliases that are too short or consist entirely of common
    English function words — these produce overwhelming false-positive
    entity mentions when scanned across a large transcript corpus.

    Parameters
    ----------
    alias_text : str
        The candidate alias text (the ASR error form).

    Returns
    -------
    bool
        ``True`` if the alias passes quality gates, ``False`` otherwise.
    """
    stripped = alias_text.strip()
    if len(stripped) < _MIN_ALIAS_LENGTH:
        return False

    tokens = stripped.lower().split()
    if not tokens:
        return False

    return not all(t in _HIGH_FREQUENCY_WORDS for t in tokens)


class EntityResolution(BaseModel):
    """Outcome of resolving a text fragment to a single entity.

    Distinguishes the three terminal states that the legacy
    ``tuple[UUID, str] | None`` contract could not: a confident single
    entity, a genuine no-match, and an *ambiguous* input that could belong
    to more than one entity and was deliberately not attached to any
    (Feature 111 FR-008). The last state is what lets a caller count a
    skip instead of silently committing an arbitrary mislink.

    Attributes
    ----------
    entity_id : UUID | None
        The resolved entity, or ``None`` when unresolved.
    entity_name : str | None
        The resolved entity's canonical name, or ``None`` when unresolved.
    ambiguous : bool
        ``True`` when the text matched several candidates and no context
        could single one out — the caller should skip, not attach.
    """

    entity_id: UUID | None = None
    entity_name: str | None = None
    ambiguous: bool = False


def _resolved(entity: NamedEntityDB) -> EntityResolution:
    """Build a resolved :class:`EntityResolution` from an entity row.

    ``entity.id`` may be a ``uuid_utils.UUID`` (the ORM default); it is
    normalised to a stdlib :class:`~uuid.UUID` so the Pydantic field and
    downstream equality checks behave as a DB round-trip would.
    """
    return EntityResolution(
        entity_id=UUID(str(entity.id)),
        entity_name=entity.canonical_name,
    )


def _fold_token(token: str) -> str:
    """Case-fold and strip a token for name-token comparison."""
    return token.strip().casefold()


def _name_tokens(name: str) -> set[str]:
    """Split *name* into folded word tokens (punctuation-insensitive)."""
    return {_fold_token(t) for t in re.split(r"[^\w]+", name) if t.strip()}


def _escape_like(value: str) -> str:
    """Escape LIKE wildcards so a literal substring match stays literal."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _dedupe_by_id(entities: list[NamedEntityDB]) -> list[NamedEntityDB]:
    """Return *entities* with duplicates (by id) removed, order preserved."""
    seen: set[str] = set()
    unique: list[NamedEntityDB] = []
    for entity in entities:
        key = str(entity.id)
        if key not in seen:
            seen.add(key)
            unique.append(entity)
    return unique


async def _known_entity_ids_for_video(session: AsyncSession, video_id: str) -> set[str]:
    """Collect entity ids already associated with a video.

    The "known" set is the union of (a) entities with any mention in the
    video (any ``mention_source``) and (b) entities associated with the
    video's channel — both the reviewed cast (``channel_principals``) and
    manual ownership assertions (``channel_ownership_assertions``). The
    query is bounded because the video, and therefore its channel, is a
    single known row.

    Returns
    -------
    set[str]
        Entity ids as strings (normalised for cross-type comparison).
    """
    known: set[str] = set()

    mention_rows = (
        (
            await session.execute(
                select(distinct(EntityMentionDB.entity_id)).where(
                    EntityMentionDB.video_id == video_id
                )
            )
        )
        .scalars()
        .all()
    )
    known.update(str(i) for i in mention_rows)

    channel_id = (
        await session.execute(
            select(VideoDB.channel_id).where(VideoDB.video_id == video_id)
        )
    ).scalar_one_or_none()
    if channel_id is not None:
        principal_rows = (
            (
                await session.execute(
                    select(ChannelPrincipalDB.entity_id).where(
                        ChannelPrincipalDB.channel_id == channel_id
                    )
                )
            )
            .scalars()
            .all()
        )
        known.update(str(i) for i in principal_rows)

        owner_rows = (
            (
                await session.execute(
                    select(ChannelOwnershipAssertionDB.entity_id).where(
                        ChannelOwnershipAssertionDB.channel_id == channel_id
                    )
                )
            )
            .scalars()
            .all()
        )
        known.update(str(i) for i in owner_rows)

    return known


async def _disambiguate(
    session: AsyncSession,
    candidates: list[NamedEntityDB],
    surname_token: str,
    adjacent_token: str | None,
    video_id: str | None,
) -> EntityResolution:
    """Pick a single entity from *candidates* using context (FR-008).

    Applies the selection order: (1) the adjacent correctly-transcribed
    token folds to a first-name token of exactly one candidate; else (2)
    exactly one candidate is already known in the video; else (3) skip —
    return an ambiguous result and attach to nothing.
    """
    # (1) Fast path: adjacent token matches one candidate's first name.
    if adjacent_token:
        folded = _fold_token(adjacent_token)
        if folded:
            hits = [
                c
                for c in candidates
                if folded in (_name_tokens(c.canonical_name) - {surname_token})
            ]
            if len(hits) == 1:
                return _resolved(hits[0])

    # (2) Video-context fallback: restrict to entities known in the video.
    if video_id:
        known = await _known_entity_ids_for_video(session, video_id)
        restricted = [c for c in candidates if str(c.id) in known]
        if len(restricted) == 1:
            return _resolved(restricted[0])

    # (3) No confident single candidate → skip, do not attach arbitrarily.
    return EntityResolution(ambiguous=True)


async def _resolve_entity(
    session: AsyncSession,
    text: str,
    *,
    adjacent_token: str | None = None,
    video_id: str | None = None,
) -> EntityResolution:
    """Resolve *text* to a single entity, disambiguating on ambiguity.

    A single exact match (canonical first, then alias) resolves directly —
    the long-standing behaviour. A canonical-name collision or a shared
    alias (previously a swallowed ``MultipleResultsFound`` or an arbitrary
    ``.first()`` pick) now routes through context-aware disambiguation, as
    does a bare surname that matches no name exactly but is contained in
    several names. Without any disambiguating context an ambiguous input
    resolves to nothing (``ambiguous=True``) rather than a guess.
    """
    normalized = text.lower().strip()
    if not normalized:
        return EntityResolution()

    # Exact canonical match (all rows — a collision must not raise/drop).
    canonical_rows = list(
        (
            await session.execute(
                select(NamedEntityDB).where(
                    NamedEntityDB.status == "active",
                    func.lower(NamedEntityDB.canonical_name) == normalized,
                )
            )
        )
        .scalars()
        .all()
    )
    if len(canonical_rows) == 1:
        return _resolved(canonical_rows[0])
    if len(canonical_rows) > 1:
        return await _disambiguate(
            session, canonical_rows, normalized, adjacent_token, video_id
        )

    # Exact alias match (join to the entity so only active ones count).
    alias_rows = list(
        (
            await session.execute(
                select(NamedEntityDB)
                .join(EntityAliasDB, EntityAliasDB.entity_id == NamedEntityDB.id)
                .where(
                    NamedEntityDB.status == "active",
                    func.lower(EntityAliasDB.alias_name) == normalized,
                )
            )
        )
        .scalars()
        .all()
    )
    alias_entities = _dedupe_by_id(alias_rows)
    if len(alias_entities) == 1:
        return _resolved(alias_entities[0])
    if len(alias_entities) > 1:
        return await _disambiguate(
            session, alias_entities, normalized, adjacent_token, video_id
        )

    # No exact match. Context-free callers keep the legacy no-match result.
    if adjacent_token is None and video_id is None:
        return EntityResolution()

    # Bare-surname fast path: active entities whose name contains the token.
    contains_rows = list(
        (
            await session.execute(
                select(NamedEntityDB).where(
                    NamedEntityDB.status == "active",
                    func.lower(NamedEntityDB.canonical_name).like(
                        f"%{_escape_like(normalized)}%", escape="\\"
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    candidates = _dedupe_by_id(contains_rows)
    if not candidates:
        return EntityResolution()
    return await _disambiguate(
        session, candidates, normalized, adjacent_token, video_id
    )


async def resolve_entity_id_from_text(
    session: AsyncSession,
    text: str,
    *,
    adjacent_token: str | None = None,
    video_id: str | None = None,
) -> tuple[UUID, str] | None:
    """Resolve an entity ID from text by matching canonical names then aliases.

    On an ambiguous match (a canonical collision or a shared alias) the
    resolver no longer attaches to an arbitrary entity: it returns ``None``
    unless *adjacent_token* or *video_id* can single out one candidate
    (Feature 111 FR-008). Callers that need to tell an ambiguous skip apart
    from a genuine no-match should use :func:`_resolve_entity` directly.

    Parameters
    ----------
    session : AsyncSession
        Database session.
    text : str
        Text to match against entity names/aliases (case-insensitive).
    adjacent_token : str | None, optional
        A correctly-transcribed token sitting beside *text* (e.g. the first
        name beside a surname), used to disambiguate shared names.
    video_id : str | None, optional
        The video the correction was made in, used to restrict ambiguous
        candidates to entities already known in that video.

    Returns
    -------
    tuple[UUID, str] | None
        ``(entity_id, entity_name)`` if resolved to exactly one entity,
        else ``None`` (no match, or ambiguous with no disambiguator).
    """
    resolution = await _resolve_entity(
        session, text, adjacent_token=adjacent_token, video_id=video_id
    )
    if resolution.entity_id is not None and resolution.entity_name is not None:
        return resolution.entity_id, resolution.entity_name
    return None


async def register_asr_alias(
    session: AsyncSession,
    *,
    original_text: str,
    corrected_text: str,
    occurrence_count: int = 1,
    commit: bool = False,
    log_prefix: str = "asr-alias",
    video_id: str | None = None,
    adjacent_token: str | None = None,
) -> int:
    """Best-effort hook: register a known-error string when a correction matches an entity.

    If ``corrected_text`` matches a known entity canonical name or alias
    (case-insensitive exact match), register ``original_text`` in the dedicated
    ``entity_asr_errors`` store for that entity (Feature 110 — these strings no
    longer live among names in ``entity_aliases``). Idempotent on the entity +
    normalized form.

    When *corrected_text* is a bare surname shared across entities, the match is
    disambiguated with *adjacent_token* and *video_id* (Feature 111 FR-008). On an
    unresolvable ambiguity the hook attaches to nothing and reports the skip so the
    caller can count it — the replacement of the former arbitrary ``.first()`` pick.

    Parameters
    ----------
    session : AsyncSession
        Database session (caller manages outer transaction).
    original_text : str
        The text that was replaced (potential ASR error form).
    corrected_text : str
        The corrected text that may match an entity name.
    occurrence_count : int
        Accepted for caller compatibility; the dedicated store keeps no occurrence
        counter (Feature 110 dropped it as a derived, unread column), so this value
        no longer affects what is written.
    commit : bool
        Whether to commit after the operation (batch hook needs this,
        single-segment hook does not).
    log_prefix : str
        Prefix for log messages to distinguish callers.
    video_id : str | None, optional
        The video the correction was made in; used to disambiguate a shared name.
    adjacent_token : str | None, optional
        A correctly-transcribed token beside *corrected_text* (e.g. a first name
        beside a surname); used to disambiguate and to build the full-name form.

    Returns
    -------
    int
        The number of corrections skipped as ambiguous (0 or 1) — a confident
        resolution, a quality-gate rejection, and a genuine no-match all return 0.
    """
    try:
        # Quality gate: reject aliases that are too short or consist
        # entirely of common English function words.
        if not is_valid_asr_alias(original_text):
            logger.debug(
                "%s: rejected alias '%s' (failed quality gate)",
                log_prefix,
                original_text,
            )
            return 0

        resolution = await _resolve_entity(
            session,
            corrected_text,
            adjacent_token=adjacent_token,
            video_id=video_id,
        )
        if resolution.ambiguous:
            logger.info(
                "%s: skipped ambiguous correction '%s' — no confident entity "
                "(not attaching to an arbitrary match)",
                log_prefix,
                corrected_text,
            )
            return 1
        if resolution.entity_id is None:
            return 0
        entity_id = resolution.entity_id
        entity_name = resolution.entity_name or corrected_text

        # R2 (FR-009): when a bare surname was disambiguated via an adjacent
        # first name, register the specific full-name form rather than the
        # ambiguous bare fragment — a safe, specific entry in the name index.
        adjacent = adjacent_token.strip() if adjacent_token else ""
        original_is_bare_surname = len(original_text.split()) == 1
        if (
            adjacent
            and original_is_bare_surname
            and _fold_token(corrected_text) != _fold_token(entity_name)
        ):
            # Register the specific full GARBLE form (adjacent first name + the
            # garbled surname as it appears in the transcript), NOT the corrected
            # name: the corrected name is already matched via canonical/alias, so
            # registering it as an ASR-error form would be inert. R2 (FR-009).
            primary_form = f"{adjacent} {original_text.strip()}"
        else:
            primary_form = original_text

        normalizer = TagNormalizationService()
        normalized = normalizer.normalize(primary_form) or primary_form.lower()

        # Register the known-error string in the dedicated store (Feature 110).
        # create_or_update is idempotent on (entity_id, alias_name_normalized); the
        # savepoint keeps a rare IntegrityError from poisoning the outer transaction.
        async with session.begin_nested():
            asr_repo = EntityAsrErrorRepository()
            await asr_repo.create_or_update(
                session,
                obj_in=EntityAsrErrorCreate(
                    entity_id=entity_id,
                    alias_name=primary_form,
                    alias_name_normalized=normalized,
                ),
            )
        if commit:
            await session.commit()
        logger.info(
            "%s: registered ASR error '%s' for entity '%s'",
            log_prefix,
            primary_form,
            entity_name,
        )

        # ----- Word-level diff: register minimal error tokens (T022) -----
        # Only attempt sub-token alias registration when the full-string
        # correction matched an entity.
        try:
            from chronovista.services.batch_correction_service import word_level_diff

            diff = word_level_diff(original_text, corrected_text)
            for error_token, canonical_token in diff.changed_pairs:
                # Skip empty tokens (insertions/deletions), duplicates of
                # the full-string alias, and sub-tokens that fail the
                # quality gate.
                if (
                    not error_token
                    or not canonical_token
                    or error_token.strip() == original_text.strip()
                    or not is_valid_asr_alias(error_token)
                ):
                    continue

                sub_normalized = (
                    normalizer.normalize(error_token) or error_token.lower()
                )

                # Register the sub-token error in the dedicated store (Feature 110).
                async with session.begin_nested():
                    asr_repo_sub = EntityAsrErrorRepository()
                    await asr_repo_sub.create_or_update(
                        session,
                        obj_in=EntityAsrErrorCreate(
                            entity_id=entity_id,
                            alias_name=error_token,
                            alias_name_normalized=sub_normalized,
                        ),
                    )
                logger.info(
                    "%s: registered sub-token ASR error '%s' for entity '%s'",
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

        return 0

    except Exception:
        logger.warning(
            "%s hook failed (non-blocking): original_text='%s', corrected_text='%s'",
            log_prefix,
            original_text,
            corrected_text,
            exc_info=True,
        )
        return 0
