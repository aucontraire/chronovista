"""
Entity mention repository for tracking named entity occurrences in transcripts.

Handles bulk insert, scoped deletion, aggregation queries, and counter updates
for the entity_mentions table.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import (
    ColumnElement,
    ColumnExpressionArgument,
    Integer,
    ScalarSelect,
    Select,
    String,
    Subquery,
    Uuid,
    and_,
    bindparam,
    case,
    cast,
    delete,
    distinct,
    func,
    literal,
    null,
    or_,
    select,
    text,
    type_coerce,
    union,
    union_all,
    update,
)
from sqlalchemy.dialects.postgresql import ARRAY, insert
from sqlalchemy.ext.asyncio import AsyncSession
from uuid_utils import uuid7

from chronovista.db.models import (
    CanonicalTag as CanonicalTagDB,
)
from chronovista.db.models import (
    Channel,
)
from chronovista.db.models import (
    EntityAlias as EntityAliasDB,
)
from chronovista.db.models import (
    EntityMention as EntityMentionDB,
)
from chronovista.db.models import (
    NamedEntity as NamedEntityDB,
)
from chronovista.db.models import (
    TagAlias as TagAliasDB,
)
from chronovista.db.models import (
    TranscriptSegment as TranscriptSegmentDB,
)
from chronovista.db.models import (
    Video as VideoDB,
)
from chronovista.db.models import (
    VideoTag as VideoTagDB,
)
from chronovista.exceptions import APIValidationError, ConflictError, NotFoundError
from chronovista.models.entity_association import (
    AssociationCount,
    AssociationSourceBreakdown,
    ChannelEntityRankingRow,
)
from chronovista.models.entity_mention import EntityMentionCreate
from chronovista.models.enums import (
    AvailabilityStatus,
    EntityAliasType,
    EvidenceScope,
    MentionSource,
)
from chronovista.repositories.base import BaseSQLAlchemyRepository
from chronovista.services.tag_normalization import TagNormalizationService

# The mention sources that count as "spoken/vouched" evidence under
# EvidenceScope.TRANSCRIPT (Feature 062 entity intersection). Manual assertions
# are the highest-trust evidence and are deliberately retained here — before
# Feature 066 US4 they carried a false ``transcript`` source and so were
# included by value; after the reclassification they carry ``manual`` and must
# be included explicitly, or the intersection would silently shed them.
_TRANSCRIPT_SCOPE_SOURCES = (
    MentionSource.TRANSCRIPT.value,
    MentionSource.MANUAL.value,
)


def _folded(col: ColumnExpressionArgument[str]) -> ColumnElement[str]:
    """Fold a name column to its case- and accent-insensitive form for visible-name matching.

    Returns ``lower(unaccent(col))`` — the ONE fold shared by every visible-name membership site
    (video panel, entity video list, the Feature 066 shared resolver, provenance filter) and by the
    stored-counter recompute, so they cannot drift apart (FR-011, single definition).

    This fold matches how mention **detection** already recognises names (NFD + drop combining marks;
    ``unaccent`` folds the same Latin diacritics), so a mention detection accepted is not then hidden
    by membership. It deliberately does NOT match the stored ``*_normalized`` columns, which retain
    Tier-2 marks (tilde, cedilla) — those are for tag identity, not membership, and are out of scope.

    Applying it is safe even though ``unaccent`` folds slightly more aggressively than detection
    (e.g. ``ø→o``): membership is always evaluated per entity (``entity_id = mention.entity_id``), so
    a wider fold can only ever match a mention to its own entity — never introduce a cross-entity
    association (data-model INV-2). Requires the ``unaccent`` extension (enabled by migration).
    """
    return func.lower(func.unaccent(col))


class EntityMentionRepository(
    BaseSQLAlchemyRepository[
        EntityMentionDB,
        EntityMentionCreate,
        dict[str, Any],
        uuid.UUID,
    ]
):
    """Repository for entity mention CRUD and aggregation operations."""

    def __init__(self) -> None:
        """Initialize repository with EntityMention model."""
        super().__init__(EntityMentionDB)

    async def get(self, session: AsyncSession, id: uuid.UUID) -> EntityMentionDB | None:
        """Get entity mention by UUID primary key.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        id : uuid.UUID
            The entity mention UUID.

        Returns
        -------
        Optional[EntityMentionDB]
            The entity mention or None if not found.
        """
        result = await session.execute(
            select(EntityMentionDB).where(EntityMentionDB.id == id)
        )
        return result.scalar_one_or_none()

    async def exists(self, session: AsyncSession, id: uuid.UUID) -> bool:
        """Check if entity mention exists by UUID primary key.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        id : uuid.UUID
            The entity mention UUID.

        Returns
        -------
        bool
            True if the mention exists.
        """
        result = await session.execute(
            select(EntityMentionDB.id).where(EntityMentionDB.id == id)
        )
        return result.first() is not None

    async def bulk_create_with_conflict_skip(
        self,
        session: AsyncSession,
        mentions: list[EntityMentionCreate],
    ) -> int:
        """Bulk insert entity mentions, skipping duplicates on conflict.

        Uses INSERT ... ON CONFLICT DO NOTHING for efficient bulk insertion
        with automatic deduplication.  Conflicts are detected by the applicable
        partial unique indexes: ``uq_entity_mentions_transcript`` for
        segment-bound mentions and ``uq_entity_mentions_manual`` for manual
        mentions.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        mentions : list[EntityMentionCreate]
            List of entity mentions to insert.

        Returns
        -------
        int
            Count of actually inserted rows (excludes skipped duplicates).
        """
        if not mentions:
            return 0

        values = [m.model_dump() for m in mentions]
        # Convert enum fields to their string values
        for v in values:
            if hasattr(v["detection_method"], "value"):
                v["detection_method"] = v["detection_method"].value
            if hasattr(v.get("mention_source"), "value"):
                v["mention_source"] = v["mention_source"].value

        stmt = insert(EntityMentionDB).values(values).on_conflict_do_nothing()
        result = await session.execute(stmt)
        return int(result.rowcount)

    async def delete_by_scope(
        self,
        session: AsyncSession,
        entity_ids: list[uuid.UUID] | None = None,
        video_ids: list[str] | None = None,
        language_code: str | None = None,
        detection_method: str = "rule_match",
        mention_source: str | None = None,
    ) -> int:
        """Delete mentions matching the given scope filters.

        Used by --full rescan to clear existing mentions before re-detection.
        The optional ``mention_source`` parameter enables FR-010 source-scoped
        deletion: ``--sources title --full`` deletes only title-sourced mentions
        without touching transcript or description mentions.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        entity_ids : list[uuid.UUID] | None
            Filter by specific entity IDs.
        video_ids : list[str] | None
            Filter by specific video IDs.
        language_code : str | None
            Filter by language code.
        detection_method : str
            Filter by detection method (default: "rule_match").
        mention_source : str | None
            When provided, restrict deletion to mentions with this
            ``mention_source`` value (e.g. ``"title"``, ``"description"``,
            ``"transcript"``).  When ``None`` (default), no source filter is
            applied and all sources matching the other criteria are deleted.

        Returns
        -------
        int
            Count of deleted rows.
        """
        stmt = delete(EntityMentionDB).where(
            EntityMentionDB.detection_method == detection_method
        )

        if entity_ids is not None:
            stmt = stmt.where(EntityMentionDB.entity_id.in_(entity_ids))
        if video_ids is not None:
            stmt = stmt.where(EntityMentionDB.video_id.in_(video_ids))
        if language_code is not None:
            stmt = stmt.where(EntityMentionDB.language_code == language_code)
        if mention_source is not None:
            stmt = stmt.where(EntityMentionDB.mention_source == mention_source)

        result = await session.execute(stmt)
        return int(result.rowcount)

    async def delete_by_correction_ids(
        self,
        session: AsyncSession,
        correction_ids: list[uuid.UUID],
    ) -> int:
        """Delete mentions linked to specific correction IDs.

        Used when corrections are reverted to remove entity mentions that
        were created as a result of those corrections.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        correction_ids : list[uuid.UUID]
            Correction IDs whose linked mentions should be deleted.

        Returns
        -------
        int
            Count of deleted rows.
        """
        if not correction_ids:
            return 0

        stmt = delete(EntityMentionDB).where(
            EntityMentionDB.correction_id.in_(correction_ids)
        )
        result = await session.execute(stmt)
        return int(result.rowcount)

    async def get_entity_ids_by_correction_ids(
        self,
        session: AsyncSession,
        correction_ids: list[uuid.UUID],
    ) -> list[uuid.UUID]:
        """Return distinct entity IDs linked to the given correction IDs.

        Used before deleting correction-linked mentions to know which entity
        counters need recalculation after the deletion.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        correction_ids : list[uuid.UUID]
            Correction IDs to look up.

        Returns
        -------
        list[uuid.UUID]
            Distinct entity IDs that have mentions linked to those corrections.
        """
        if not correction_ids:
            return []

        stmt = select(distinct(EntityMentionDB.entity_id)).where(
            EntityMentionDB.correction_id.in_(correction_ids)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def get_entities_with_zero_mentions(
        self,
        session: AsyncSession,
        entity_type: str | None = None,
    ) -> list[uuid.UUID]:
        """Return entity IDs that have zero entity_mentions rows.

        Used by --new-entities-only to find entities needing initial detection.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        entity_type : str | None
            Optional filter by entity type.

        Returns
        -------
        list[uuid.UUID]
            List of entity IDs with no mentions.
        """
        # Subquery: entity IDs that DO have mentions
        mentioned_subq = select(distinct(EntityMentionDB.entity_id)).scalar_subquery()

        stmt = select(NamedEntityDB.id).where(
            NamedEntityDB.id.notin_(mentioned_subq),
            NamedEntityDB.status == "active",
        )

        if entity_type is not None:
            stmt = stmt.where(NamedEntityDB.entity_type == entity_type)

        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update_entity_counters(
        self,
        session: AsyncSession,
        entity_ids: list[uuid.UUID],
    ) -> None:
        """Update mention_count and video_count on named_entities.

        Computes aggregate counts from entity_mentions and applies them to
        the named_entities table for the specified entity IDs.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        entity_ids : list[uuid.UUID]
            Entity IDs whose counters should be refreshed.
        """
        if not entity_ids:
            return

        # Build a subquery of "visible names" per entity: canonical names
        # plus non-ASR-error aliases.  Only mentions matching these names
        # should be counted, so that ASR-error alias mentions are excluded.
        canonical_names = select(
            NamedEntityDB.id.label("entity_id"),
            _folded(NamedEntityDB.canonical_name).label("name_lower"),
        ).where(NamedEntityDB.id.in_(entity_ids))

        non_asr_aliases = select(
            EntityAliasDB.entity_id,
            _folded(EntityAliasDB.alias_name).label("name_lower"),
        ).where(
            EntityAliasDB.entity_id.in_(entity_ids),
            EntityAliasDB.alias_type != EntityAliasType.ASR_ERROR,
        )

        visible_names = union(canonical_names, non_asr_aliases).subquery()

        # Count only mentions whose mention_text matches a visible name
        agg_subq = (
            select(
                EntityMentionDB.entity_id,
                func.count(distinct(EntityMentionDB.id)).label("mention_count"),
                func.count(distinct(EntityMentionDB.video_id)).label("video_count"),
            )
            .join(
                visible_names,
                and_(
                    EntityMentionDB.entity_id == visible_names.c.entity_id,
                    _folded(EntityMentionDB.mention_text) == visible_names.c.name_lower,
                ),
            )
            .where(EntityMentionDB.entity_id.in_(entity_ids))
            .group_by(EntityMentionDB.entity_id)
            .subquery()
        )

        # Update entities that have visible mentions
        stmt = (
            update(NamedEntityDB)
            .where(NamedEntityDB.id == agg_subq.c.entity_id)
            .values(
                mention_count=agg_subq.c.mention_count,
                video_count=agg_subq.c.video_count,
            )
        )
        await session.execute(stmt)

        # Set counters to 0 for entities with no visible mentions
        entities_with_visible_mentions = select(agg_subq.c.entity_id).scalar_subquery()
        zero_stmt = (
            update(NamedEntityDB)
            .where(
                NamedEntityDB.id.in_(entity_ids),
                NamedEntityDB.id.notin_(entities_with_visible_mentions),
            )
            .values(mention_count=0, video_count=0)
        )
        await session.execute(zero_stmt)

    async def update_alias_counters(
        self,
        session: AsyncSession,
        entity_ids: list[uuid.UUID],
    ) -> None:
        """Update occurrence_count on entity_aliases from entity_mentions.

        For each alias belonging to the given entities, counts how many
        mentions have a ``mention_text`` that matches the alias name
        (case-insensitive) and writes the count back to
        ``entity_aliases.occurrence_count``.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        entity_ids : list[uuid.UUID]
            Entity IDs whose alias counters should be refreshed.
        """
        if not entity_ids:
            return

        # Aggregate mention_text counts per (entity_id, lower(mention_text))
        mention_counts_subq = (
            select(
                EntityMentionDB.entity_id,
                _folded(EntityMentionDB.mention_text).label("mention_lower"),
                func.count().label("cnt"),
            )
            .where(EntityMentionDB.entity_id.in_(entity_ids))
            .group_by(
                EntityMentionDB.entity_id,
                _folded(EntityMentionDB.mention_text),
            )
            .subquery()
        )

        # Join aliases to mention counts on (entity_id, lower(alias_name))
        # and update occurrence_count
        update_stmt = (
            update(EntityAliasDB)
            .where(
                EntityAliasDB.entity_id == mention_counts_subq.c.entity_id,
                _folded(EntityAliasDB.alias_name)
                == mention_counts_subq.c.mention_lower,
            )
            .values(occurrence_count=mention_counts_subq.c.cnt)
        )
        await session.execute(update_stmt)

        # Zero out aliases that have no matching mentions
        aliases_with_mentions = (
            select(EntityAliasDB.id)
            .join(
                mention_counts_subq,
                (EntityAliasDB.entity_id == mention_counts_subq.c.entity_id)
                & (
                    _folded(EntityAliasDB.alias_name)
                    == mention_counts_subq.c.mention_lower
                ),
            )
            .scalar_subquery()
        )
        zero_stmt = (
            update(EntityAliasDB)
            .where(
                EntityAliasDB.entity_id.in_(entity_ids),
                EntityAliasDB.id.notin_(aliases_with_mentions),
            )
            .values(occurrence_count=0)
        )
        await session.execute(zero_stmt)

    # Category mapping for detection methods → source categories.
    #
    # Retained only for callers that genuinely classify by *detection method*.
    # It must NOT be used to report where a mention was found: it predates
    # Feature 054's ``mention_source`` column and hardcodes the assumption that
    # a rule-matched mention came from a transcript, which stopped being true
    # the moment title and description scanning shipped (GitHub #172).
    async def get_video_entity_summary(
        self,
        session: AsyncSession,
        video_id: str,
        language_code: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get entity summary for a video.

        GROUP BY entity_id with COUNT(distinct segment_id) as mention_count,
        MIN(start_time) as first_mention_time. JOINs named_entities for
        canonical_name, entity_type, description. Uses LEFT JOIN on
        transcript_segments to include manual mentions (segment_id=NULL).
        Sorted by mention_count DESC.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        video_id : str
            YouTube video ID.
        language_code : str | None
            Optional language filter.

        Returns
        -------
        list[dict[str, Any]]
            List of dicts matching VideoEntitySummary schema including
            sources, has_manual, and nullable first_mention_time.
        """
        # What counts as one mention (Feature 066 FR-012).
        #
        # Transcript = frequency: counted per distinct segment, so an entity
        # said three times in one segment counts once but across three segments
        # counts three — the long-standing behaviour, preserved.
        #
        # Description = presence, title = presence: these collapse to one per
        # entity per video, so metadata boilerplate does not read as strong
        # signal. A name repeated in the description (5,610 (entity, video)
        # pairs carry more than one description row, up to five) contributes
        # exactly one; without this it inflated the count by its text-variant
        # count. Title already had at most one row (a partial unique index),
        # so collapsing it is a no-op that states the rule rather than relying
        # on the constraint. Both are keyed on ``mention_source`` (a constant
        # per branch) so every such row folds to a single token; the else
        # branch's tokens are segment/uuid strings and never collide with the
        # literal source names.
        #
        # Manual associations stay excluded, which is deliberate rather than
        # incidental: ``has_manual`` reports them, and the web client treats
        # ``mention_count == 0`` as "linked by hand, never actually detected"
        # when it optimistically removes an association. Counting them here
        # would silently break that removal.
        countable_mention = case(
            (EntityMentionDB.detection_method == "manual", null()),
            (
                EntityMentionDB.mention_source.in_(("description", "title")),
                EntityMentionDB.mention_source,
            ),
            else_=func.coalesce(
                cast(EntityMentionDB.segment_id, String),
                cast(EntityMentionDB.id, String),
            ),
        )
        mention_count = func.count(distinct(countable_mention))

        # Use array_agg to collect distinct detection methods per entity
        stmt = (
            select(
                EntityMentionDB.entity_id,
                NamedEntityDB.canonical_name,
                NamedEntityDB.entity_type,
                NamedEntityDB.description,
                mention_count.label("mention_count"),
                func.min(TranscriptSegmentDB.start_time).label("first_mention_time"),
                func.array_agg(distinct(EntityMentionDB.detection_method)).label(
                    "detection_methods"
                ),
                # Where the mentions were actually found. Reported from
                # mention_source, never inferred from detection method.
                #
                # Manual rows are excluded: they carry mention_source
                # 'transcript' regardless of whether the entity was ever said,
                # so including them would have a hand-linked entity claim a
                # transcript appearance it does not have. That a human added it
                # is reported by has_manual instead.
                func.array_agg(
                    distinct(
                        case(
                            (EntityMentionDB.detection_method == "manual", null()),
                            else_=EntityMentionDB.mention_source,
                        )
                    )
                ).label("mention_sources"),
                func.bool_or(EntityMentionDB.detection_method == "manual").label(
                    "has_manual"
                ),
            )
            .join(
                NamedEntityDB,
                EntityMentionDB.entity_id == NamedEntityDB.id,
            )
            .outerjoin(
                TranscriptSegmentDB,
                EntityMentionDB.segment_id == TranscriptSegmentDB.id,
            )
            .where(EntityMentionDB.video_id == video_id)
            .group_by(
                EntityMentionDB.entity_id,
                NamedEntityDB.canonical_name,
                NamedEntityDB.entity_type,
                NamedEntityDB.description,
            )
            .order_by(mention_count.desc())
        )

        if language_code is not None:
            # Language filter applies to transcript-derived mentions only;
            # manual mentions (language_code=NULL) are always included.
            stmt = stmt.where(
                or_(
                    EntityMentionDB.language_code == language_code,
                    EntityMentionDB.detection_method == "manual",
                )
            )

        result = await session.execute(stmt)
        rows = result.all()

        return [
            {
                "entity_id": str(row.entity_id),
                "canonical_name": row.canonical_name,
                "entity_type": row.entity_type,
                "description": row.description,
                "mention_count": row.mention_count,
                "first_mention_time": (
                    float(row.first_mention_time)
                    if row.first_mention_time is not None
                    else None
                ),
                # Where the mentions were found, plus "manual" when the entity
                # was also linked by hand. Previously derived by mapping
                # detection_method, which reported a title-only mention as
                # "transcript" because rule_match was hardcoded to mean
                # transcript. Location comes from mention_source; the manual
                # marker is a detection-method fact and still comes from there.
                # array_agg emits a NULL element for every manual row the CASE
                # blanked, so None is filtered rather than assumed absent.
                "sources": sorted(
                    {s for s in (row.mention_sources or []) if s is not None}
                    | ({"manual"} if row.has_manual else set())
                ),
                "has_manual": bool(row.has_manual),
            }
            for row in rows
        ]

    # Transcript-derived detection methods (excludes manual).
    _TRANSCRIPT_METHODS = {
        "rule_match",
        "spacy_ner",
        "llm_extraction",
        "user_correction",
    }

    async def get_entity_video_list(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        language_code: str | None = None,
        source_filter: Sequence[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Get paginated list of videos associated with an entity.

        Returns videos from three sources:
        1. **Transcript mentions** — entity_mentions rows (existing behaviour)
        2. **Canonical tag associations** — videos tagged with the entity's
           linked canonical tag (Feature 053, US1)
        3. **Alias-matched tag associations** — videos tagged with terms
           matching entity aliases via normalization (Feature 053, US2)

        Both tag sources (canonical and alias-matched) use the same ``"tag"``
        source indicator.  Videos appearing in multiple sources are
        deduplicated by video_id; the transcript-mention data (mention_count,
        mentions, first_mention_time) is preserved and ``"tag"`` is appended
        to the ``sources`` list (only once, regardless of how many tag paths
        matched — T020).

        Sort order: transcript-mention videos first (mention_count DESC,
        upload_date DESC), then tag-only videos (upload_date DESC).  This
        uses a composite key ``(has_transcript_mention DESC, mention_count
        DESC, upload_date DESC)`` per research.md Decision 5.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        entity_id : uuid.UUID
            The named entity UUID.
        language_code : str | None
            Optional language filter. Manual mentions (language_code=NULL) are
            always included regardless of this filter.
        source_filter : Sequence[str] | None
            Optional provenance filter over ``{"transcript", "title",
            "description", "tag", "manual"}``. A video is kept when its
            ``sources`` list intersects the requested set (union / OR — a
            single value gives "that source only"). ``None`` or empty means all
            sources. Affects both the result set and the total count. This is
            provenance, not detection method (FR-007/FR-009).
        limit : int
            Maximum results per page.
        offset : int
            Pagination offset.

        Returns
        -------
        tuple[list[dict[str, Any]], int]
            Tuple of (results list, total deduplicated count of distinct
            videos across transcript mentions and tag associations).
        """
        # Build "visible names" subquery: canonical name + non-ASR-error
        # aliases.  This keeps video/mention counts consistent with the
        # counters stored on named_entities (which also exclude ASR-error
        # alias mentions).
        canonical_names = select(
            _folded(NamedEntityDB.canonical_name).label("name_lower"),
        ).where(NamedEntityDB.id == entity_id)

        non_asr_aliases = select(
            _folded(EntityAliasDB.alias_name).label("name_lower"),
        ).where(
            EntityAliasDB.entity_id == entity_id,
            EntityAliasDB.alias_type != EntityAliasType.ASR_ERROR,
        )

        visible_names = union(canonical_names, non_asr_aliases).subquery()

        # Mention filter: visible-name match OR manual detection method.
        # Manual mentions always use mention_text=canonical_name which is
        # already in visible_names, but we include them via OR to be safe.
        mention_filter = and_(
            EntityMentionDB.entity_id == entity_id,
            or_(
                _folded(EntityMentionDB.mention_text) == visible_names.c.name_lower,
                EntityMentionDB.detection_method == "manual",
            ),
        )

        # Language filter: manual mentions (language_code=NULL) always pass.
        lang_filter = (
            or_(
                EntityMentionDB.language_code == language_code,
                EntityMentionDB.detection_method == "manual",
            )
            if language_code is not None
            else None
        )

        # ------------------------------------------------------------------
        # Step 1: Fetch transcript-mention video_ids (for total count)
        # ------------------------------------------------------------------
        transcript_vid_stmt = (
            select(distinct(EntityMentionDB.video_id))
            .outerjoin(
                visible_names,
                _folded(EntityMentionDB.mention_text) == visible_names.c.name_lower,
            )
            .where(mention_filter)
        )
        if lang_filter is not None:
            transcript_vid_stmt = transcript_vid_stmt.where(lang_filter)

        transcript_vid_result = await session.execute(transcript_vid_stmt)
        transcript_video_ids: set[str] = set(transcript_vid_result.scalars().all())

        # ------------------------------------------------------------------
        # Step 2: Fetch tag-associated video_ids (Sources 2 & 3)
        # ------------------------------------------------------------------
        # Source 2: canonical tag path
        canonical_tag_video_ids = await self._get_tag_associated_video_ids(
            session, entity_id
        )
        # Source 3: alias-matched tag path (T019)
        alias_tag_video_ids = await self._get_alias_matched_tag_video_ids(
            session, entity_id
        )
        # Union both tag sources — same "tag" indicator for both paths
        tag_video_ids = canonical_tag_video_ids | alias_tag_video_ids

        # Deduplicated total count across all sources (T015, T020)
        all_video_ids = transcript_video_ids | tag_video_ids
        total_count = len(all_video_ids)

        if total_count == 0:
            return [], 0

        # ------------------------------------------------------------------
        # Step 3: Fetch transcript-mention video details (existing logic)
        # ------------------------------------------------------------------
        # We still need the grouped query for transcript-mention videos
        # to get mention_count, detection_methods, first_mention_time, etc.
        results_dict: dict[str, dict[str, Any]] = {}

        if transcript_video_ids:
            main_stmt = (
                select(
                    EntityMentionDB.video_id,
                    VideoDB.title.label("video_title"),
                    func.coalesce(
                        Channel.title, VideoDB.channel_name_hint, "Unknown"
                    ).label("channel_name"),
                    # Transcript-only mention count (excludes manual)
                    func.count()
                    .filter(
                        EntityMentionDB.detection_method.in_(self._TRANSCRIPT_METHODS),
                        EntityMentionDB.mention_source == "transcript",
                    )
                    .label("mention_count"),
                    # Collect distinct detection methods for source mapping
                    func.array_agg(distinct(EntityMentionDB.detection_method)).label(
                        "detection_methods"
                    ),
                    # Collect distinct mention sources
                    func.array_agg(distinct(EntityMentionDB.mention_source)).label(
                        "mention_sources"
                    ),
                    # Has manual flag
                    func.bool_or(EntityMentionDB.detection_method == "manual").label(
                        "has_manual"
                    ),
                    # First mention time from transcript segments (LEFT JOIN)
                    func.min(TranscriptSegmentDB.start_time).label(
                        "first_mention_time"
                    ),
                    # Upload date for sorting
                    VideoDB.upload_date,
                )
                .outerjoin(
                    visible_names,
                    _folded(EntityMentionDB.mention_text) == visible_names.c.name_lower,
                )
                .join(VideoDB, EntityMentionDB.video_id == VideoDB.video_id)
                .outerjoin(Channel, VideoDB.channel_id == Channel.channel_id)
                .outerjoin(
                    TranscriptSegmentDB,
                    EntityMentionDB.segment_id == TranscriptSegmentDB.id,
                )
                .where(mention_filter)
            )
            if lang_filter is not None:
                main_stmt = main_stmt.where(lang_filter)

            main_stmt = main_stmt.group_by(
                EntityMentionDB.video_id,
                VideoDB.title,
                Channel.title,
                VideoDB.channel_name_hint,
                VideoDB.upload_date,
            )

            main_result = await session.execute(main_stmt)
            video_rows = main_result.all()

            for row in video_rows:
                # Provenance comes from mention_source, not detection_method
                # (#172 / Feature 066): a rule_match mention found in a title or
                # description is a title/description association, not a
                # transcript one. Deriving 'transcript' from detection_method
                # mislabelled every title/description video as transcript. Manual
                # is reported by has_manual; tag is appended below. This mirrors
                # the shared resolver's source labelling, so this filter and the
                # entity's per-source breakdown agree (FR-016).
                sources_set: set[str] = {
                    ms
                    for ms in (row.mention_sources or [])
                    if ms in ("transcript", "title", "description")
                }
                if row.has_manual:
                    sources_set.add("manual")
                sources = sorted(sources_set)

                # T013: If this video is also in tag results, append "tag"
                if row.video_id in tag_video_ids and "tag" not in sources:
                    sources.append("tag")
                    sources.sort()

                # Fetch up to 5 transcript-derived mention previews
                preview_stmt = (
                    select(
                        EntityMentionDB.segment_id,
                        TranscriptSegmentDB.start_time,
                        EntityMentionDB.mention_text,
                    )
                    .join(
                        TranscriptSegmentDB,
                        EntityMentionDB.segment_id == TranscriptSegmentDB.id,
                    )
                    .outerjoin(
                        visible_names,
                        _folded(EntityMentionDB.mention_text)
                        == visible_names.c.name_lower,
                    )
                    .where(
                        EntityMentionDB.entity_id == entity_id,
                        EntityMentionDB.video_id == row.video_id,
                        EntityMentionDB.detection_method != "manual",
                        or_(
                            _folded(EntityMentionDB.mention_text)
                            == visible_names.c.name_lower,
                            EntityMentionDB.detection_method == "manual",
                        ),
                    )
                )
                if language_code is not None:
                    preview_stmt = preview_stmt.where(
                        EntityMentionDB.language_code == language_code
                    )
                preview_stmt = preview_stmt.order_by(
                    TranscriptSegmentDB.start_time.asc()
                ).limit(5)

                preview_result = await session.execute(preview_stmt)
                previews = [
                    {
                        "segment_id": p.segment_id,
                        "start_time": p.start_time,
                        "mention_text": p.mention_text,
                    }
                    for p in preview_result.all()
                ]

                # Fetch description context if this video has description mentions
                description_context: str | None = None
                if "description" in (row.mention_sources or []):
                    desc_ctx_stmt = (
                        select(EntityMentionDB.mention_context)
                        .where(
                            EntityMentionDB.entity_id == entity_id,
                            EntityMentionDB.video_id == row.video_id,
                            EntityMentionDB.mention_source == "description",
                            EntityMentionDB.mention_context.isnot(None),
                        )
                        .limit(1)
                    )
                    desc_ctx_result = await session.execute(desc_ctx_stmt)
                    description_context = desc_ctx_result.scalar_one_or_none()

                results_dict[row.video_id] = {
                    "video_id": row.video_id,
                    "video_title": row.video_title,
                    "channel_name": row.channel_name,
                    "mention_count": row.mention_count,
                    "mentions": previews,
                    "sources": sources,
                    "has_manual": bool(row.has_manual),
                    "first_mention_time": (
                        float(row.first_mention_time)
                        if row.first_mention_time is not None
                        else None
                    ),
                    "upload_date": (
                        row.upload_date.isoformat()
                        if row.upload_date is not None
                        else None
                    ),
                    "description_context": description_context,
                }

        # ------------------------------------------------------------------
        # Step 4: Fetch tag-only video details (T012)
        # ------------------------------------------------------------------
        tag_only_ids = tag_video_ids - transcript_video_ids
        if tag_only_ids:
            tag_meta_stmt = (
                select(
                    VideoDB.video_id,
                    VideoDB.title.label("video_title"),
                    func.coalesce(
                        Channel.title, VideoDB.channel_name_hint, "Unknown"
                    ).label("channel_name"),
                    VideoDB.upload_date,
                )
                .outerjoin(Channel, VideoDB.channel_id == Channel.channel_id)
                .where(VideoDB.video_id.in_(tag_only_ids))
            )
            tag_meta_result = await session.execute(tag_meta_stmt)
            tag_meta_rows = tag_meta_result.all()

            for row in tag_meta_rows:
                results_dict[row.video_id] = {
                    "video_id": row.video_id,
                    "video_title": row.video_title,
                    "channel_name": row.channel_name,
                    "mention_count": 0,
                    "mentions": [],
                    "sources": ["tag"],
                    "has_manual": False,
                    "first_mention_time": None,
                    "upload_date": (
                        row.upload_date.isoformat()
                        if row.upload_date is not None
                        else None
                    ),
                    "description_context": None,
                }

        # ------------------------------------------------------------------
        # Step 5: Sort — transcript-mention videos first, then tag-only (T014)
        # ------------------------------------------------------------------
        # Composite sort key: (has_transcript_mention DESC, mention_count DESC,
        # upload_date DESC)  — per research.md Decision 5
        def _sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
            has_transcript = (
                1
                if item["mention_count"] > 0
                or any(s in ("transcript", "manual") for s in item["sources"])
                else 0
            )
            return (
                has_transcript,
                item["mention_count"],
                item["upload_date"] or "",
            )

        sorted_results = sorted(results_dict.values(), key=_sort_key, reverse=True)

        # ------------------------------------------------------------------
        # Step 5b: Apply the provenance filter if provided (T064, FR-031;
        # multi-select union, Feature 066 US3). Empty means all sources.
        # ------------------------------------------------------------------
        wanted = set(source_filter) if source_filter else None
        if wanted is not None:
            sorted_results = [
                item for item in sorted_results if wanted & set(item["sources"])
            ]

        # ------------------------------------------------------------------
        # Step 6: Apply pagination to the merged, sorted results (T015)
        # ------------------------------------------------------------------
        filtered_total = len(sorted_results)
        paginated = sorted_results[offset : offset + limit]

        return paginated, filtered_total if wanted is not None else total_count

    async def _tag_inclusive_association_arms(
        self,
        session: AsyncSession,
        entity_ids: list[uuid.UUID],
        evidence_scope: EvidenceScope,
    ) -> Subquery:
        """UNION ALL of the association arms for ``entity_ids``.

        Exposes ``(entity_id, video_id, mention_weight)`` -- the **single**
        association definition shared with :meth:`get_association_counts`
        (Feature 066), so the entity filter and the counts cannot drift
        (FR-005). One row per association event:

        - **mention arm** -- :meth:`_mention_assoc_stmt` (the visible-name /
          manual rule, #89), ``mention_weight = 1``. This is the count's own
          mention builder, adopted here so the filter's mention side matches the
          count by construction (research R6); it replaces the older
          ``entity_id IN (…)`` any-mention rule.
        - **canonical-tag arm** and **alias-tag arm** -- ``mention_weight = 0``,
          included **only at** ``EvidenceScope.ANY`` (FR-007). A tag is not
          transcript-strength evidence, so stricter scopes stay mention-only.

        ``mention_weight`` lets the qualification sum mention volume while tags
        contribute 0 (FR-006), with no second query.

        The alias-tag pairs are Python-normalised (:meth:`_alias_tag_pairs`; the
        #207 duplicate-normaliser trap keeps them out of SQL) and injected via
        **two** ``unnest`` **array binds** -- never a row-per-pair ``VALUES`` --
        so a heavy page's tens of thousands of pairs stay two binds and never
        approach asyncpg's 32,767 bind-parameter ceiling (mirrors
        :meth:`get_association_counts`).

        Because both the qualification (required-AND, in
        :meth:`build_entity_qualification_subquery`) and the exclusion
        (excluded-OR, in :meth:`build_entity_exclusion_subquery`) build their
        video set from this one selectable, they use the identical definition of
        "associated" by construction (FR-003).

        Parameters
        ----------
        session : AsyncSession
            Session used to fetch the alias-tag pairs (Python normalisation).
        entity_ids : list[uuid.UUID]
            The entities whose associations to assemble. Assumed already
            deduplicated by the caller.
        evidence_scope : EvidenceScope
            ``ANY`` includes the tag arms; ``TRANSCRIPT`` restricts the mention
            arm to ``_TRANSCRIPT_SCOPE_SOURCES`` and omits the tag arms.

        Returns
        -------
        Subquery
            ``assoc`` exposing ``entity_id``, ``video_id`` and
            ``mention_weight``.
        """
        mention_stmt = self._mention_assoc_stmt(entity_ids)
        if evidence_scope is EvidenceScope.TRANSCRIPT:
            mention_stmt = mention_stmt.where(
                EntityMentionDB.mention_source.in_(_TRANSCRIPT_SCOPE_SOURCES)
            )
        mention_sub = mention_stmt.subquery()
        arms: list[Any] = [
            select(
                mention_sub.c.entity_id.label("entity_id"),
                mention_sub.c.video_id.label("video_id"),
                literal(1).label("mention_weight"),
            )
        ]

        # Tag associations qualify only at the default ANY scope (FR-007); a tag
        # is not transcript-strength evidence.
        if evidence_scope is EvidenceScope.ANY:
            canonical_sub = self._canonical_tag_assoc_stmt(entity_ids).subquery()
            arms.append(
                select(
                    canonical_sub.c.entity_id.label("entity_id"),
                    canonical_sub.c.video_id.label("video_id"),
                    literal(0).label("mention_weight"),
                )
            )
            alias_pairs = await self._alias_tag_pairs(session, entity_ids)
            if alias_pairs:
                # Two array binds + unnest, NOT a row-per-pair VALUES: two binds
                # regardless of pair count keeps a heavy page under asyncpg's
                # 32,767 bind-parameter cap (mirrors get_association_counts).
                arms.append(
                    text(
                        "SELECT e AS entity_id, v AS video_id, "
                        "0 AS mention_weight "
                        "FROM unnest(:alias_entity_ids, :alias_video_ids) "
                        "AS t(e, v)"
                    )
                    .bindparams(
                        bindparam(
                            "alias_entity_ids",
                            value=[eid for eid, _ in alias_pairs],
                            type_=ARRAY(Uuid),
                        ),
                        bindparam(
                            "alias_video_ids",
                            value=[vid for _, vid in alias_pairs],
                            type_=ARRAY(String),
                        ),
                    )
                    .columns(entity_id=Uuid, video_id=String, mention_weight=Integer)
                )

        return union_all(*arms).subquery("assoc")

    async def build_entity_qualification_subquery(
        self,
        session: AsyncSession,
        entity_ids: Sequence[uuid.UUID],
        evidence_scope: EvidenceScope = EvidenceScope.ANY,
    ) -> Subquery:
        """
        Build the qualification subquery for an entity intersection.

        Produces ``(video_id, total_mentions)`` for exactly those videos
        **associated with every** requested entity, where "associated" means the
        same thing the entity counts mean (Feature 066): a mention **or** a tag
        (canonical-tag or alias-tag) at the default ``ANY`` scope, mentions only
        at ``TRANSCRIPT`` (FR-001/FR-007). This is what makes the filter and
        :meth:`get_association_counts` agree for every entity (FR-002).

        The association set comes from :meth:`_tag_inclusive_association_arms`,
        the one selectable that also feeds the counts, so there is no parallel
        definition of "associated" to drift (FR-005).

        The ``count == filter`` parity (FR-002) assumes referential integrity
        between ``entity_mentions`` / ``video_tags`` and ``videos``:
        :meth:`get_association_counts` does not join ``videos`` (it counts
        association rows directly), whereas this subquery is joined to
        ``videos`` by the caller. A mention or video-tag row pointing at a
        ``video_id`` with no ``videos`` row would be counted but not returned,
        breaking the equality. FK constraints on those tables keep that from
        happening.

        ``total_mentions`` is ``SUM(mention_weight)`` -- mention-arm rows only,
        since tag arms carry weight 0 -- so a tag-only video scores 0 and the
        RELEVANCE sort ranks by mention volume alone (FR-006).

        Duplicate-safe by construction. The association arms hold multiple rows
        per ``(entity_id, video_id)`` by design -- across sources, and within a
        source. Qualification counts *distinct* entity ids, so row multiplicity
        can neither make a video qualify for an entity it is not associated with
        nor raise the bar for one it is (FR-003, FR-004).

        ``transcript_segments`` is deliberately NOT joined here. Joining it
        before pagination returns byte-identical results at roughly eight times
        the cost (research R1). Timestamps are fetched for the returned page
        only, by :meth:`get_page_entity_matches`.

        Parameters
        ----------
        session : AsyncSession
            Session used to fetch the Python-normalised alias-tag pairs.
        entity_ids : Sequence[uuid.UUID]
            Required entities. Deduplicated internally, so requesting the same
            entity twice is idempotent and does not raise the bar.
        evidence_scope : EvidenceScope
            Which associations qualify. ``ANY`` accepts mentions and tags;
            ``TRANSCRIPT`` restricts to transcript-sourced mentions (retaining
            every human-added mention, FR-020c) and excludes tags (FR-007).

        Returns
        -------
        Subquery
            Joinable subquery exposing ``video_id`` and ``total_mentions``.
        """
        distinct_ids = list(dict.fromkeys(entity_ids))
        assoc = await self._tag_inclusive_association_arms(
            session, distinct_ids, evidence_scope
        )
        return (
            select(
                assoc.c.video_id.label("video_id"),
                # SUM of the per-row weight = mention-arm row count (mention
                # VOLUME); tag rows weigh 0. Deliberately NOT a distinct count:
                # each mention row is a distinct event, and relevance ranks by
                # volume (FR-006, research R3).
                func.sum(assoc.c.mention_weight).label("total_mentions"),
            )
            .group_by(assoc.c.video_id)
            .having(func.count(distinct(assoc.c.entity_id)) == len(distinct_ids))
            .subquery()
        )

    async def build_entity_exclusion_subquery(
        self,
        session: AsyncSession,
        entity_ids: Sequence[uuid.UUID],
        evidence_scope: EvidenceScope = EvidenceScope.ANY,
    ) -> ScalarSelect[str]:
        """
        Build the set of video ids disqualified by an excluded-entity filter.

        A video **associated with any** of the excluded entities is
        disqualified, regardless of how many required entities it matches
        (FR-014). This is OR semantics, in deliberate contrast to the AND
        semantics of qualification.

        "Associated" is the **same** tag-inclusive definition qualification
        uses: the excluded-video set is the distinct ``video_id``\\ s in
        :meth:`_tag_inclusive_association_arms` for the excluded entities —
        a mention **or** a tag (canonical-tag or alias-tag) at the default
        ``ANY`` scope, mentions only at ``TRANSCRIPT`` (FR-003/FR-007). Both
        sides consuming that one selectable is what keeps them symmetric by
        construction: a video excluded by ``exclude_entity_id=E`` is exactly a
        video that ``entity_id=E`` would include, so no request can treat the
        same video as both associated and not-associated (the incoherence the
        old asymmetric definition risked).

        The evidence scope is applied symmetrically with qualification: under
        ``TRANSCRIPT``, tags do not disqualify (they are not transcript-strength
        evidence) and a mention whose text is not one of the entity's visible
        names does not disqualify, because it does not qualify on the other side
        either.

        Parameters
        ----------
        session : AsyncSession
            Session used to fetch the Python-normalised alias-tag pairs (via the
            shared association helper).
        entity_ids : Sequence[uuid.UUID]
            Excluded entities. Deduplicated internally.
        evidence_scope : EvidenceScope
            Which associations count as associating. Must match the scope used
            for qualification.

        Returns
        -------
        ScalarSelect[str]
            Scalar subquery of ``video_id`` suitable for ``notin_()``.
        """
        distinct_ids = list(dict.fromkeys(entity_ids))
        assoc = await self._tag_inclusive_association_arms(
            session, distinct_ids, evidence_scope
        )
        return select(assoc.c.video_id).distinct().scalar_subquery()

    def build_cooccurrence_query(
        self,
        entity_id: uuid.UUID,
        limit: int = 12,
        evidence_scope: EvidenceScope = EvidenceScope.ANY,
    ) -> Select[Any]:
        """
        Return the entities sharing the most videos with ``entity_id``.

        Powers the appears-with panel (US3). Ordered by shared-video count
        descending, tiebroken by partner id ascending -- the tiebreak makes a
        bounded list deterministic, so two partners with equal counts cannot
        swap between requests and make the panel look unstable (R5).

        **Availability is not incidental here.** The count this returns is
        promised to equal the videos list's ``pagination.total`` for the same
        pair (FR-024b), and that list excludes unavailable videos by default.
        Counting every shared video would inflate this figure -- measured
        against production, one popular pair differs by nine -- and the user
        would be shown one number and land on another. The join to ``videos``
        below is what keeps the promise.

        Parameters
        ----------
        entity_id : uuid.UUID
            The subject entity.
        limit : int
            Maximum partners to return.
        evidence_scope : EvidenceScope
            Which mentions count as co-occurrence. Must match the scope the
            surrounding view is using, or the panel and the intersection it
            opens will disagree (FR-024a).

        Returns
        -------
        Select[Any]
            The unexecuted statement, so callers and tests can inspect it.
        """
        # The scope narrows the SUBJECT's videos before the partner select is
        # built, so both sides of the co-occurrence are computed under one
        # definition. Chained rather than rebuilt: two copies of this column
        # list would let the scoped and unscoped forms drift apart silently.
        subject_videos = select(EntityMentionDB.video_id).where(
            EntityMentionDB.entity_id == entity_id
        )
        if evidence_scope is EvidenceScope.TRANSCRIPT:
            subject_videos = subject_videos.where(
                EntityMentionDB.mention_source.in_(_TRANSCRIPT_SCOPE_SOURCES)
            )

        partner = select(
            EntityMentionDB.entity_id.label("partner_id"),
            func.count(distinct(EntityMentionDB.video_id)).label("shared"),
        ).where(
            EntityMentionDB.entity_id != entity_id,
            EntityMentionDB.video_id.in_(subject_videos),
        )
        if evidence_scope is EvidenceScope.TRANSCRIPT:
            partner = partner.where(
                EntityMentionDB.mention_source.in_(_TRANSCRIPT_SCOPE_SOURCES)
            )

        # Restrict to the same video population the videos list uses, so the
        # count shown equals the count landed on (FR-024b).
        available = select(VideoDB.video_id).where(
            VideoDB.availability_status == AvailabilityStatus.AVAILABLE
        )
        partner = partner.where(EntityMentionDB.video_id.in_(available))

        grouped = partner.group_by(EntityMentionDB.entity_id).subquery()

        stmt = (
            select(
                grouped.c.partner_id,
                grouped.c.shared,
                NamedEntityDB.canonical_name,
                NamedEntityDB.entity_type,
            )
            .join(NamedEntityDB, NamedEntityDB.id == grouped.c.partner_id)
            .order_by(grouped.c.shared.desc(), grouped.c.partner_id.asc())
            .limit(limit)
        )

        return stmt

    async def get_cooccurring_entities(
        self,
        session: AsyncSession,
        *,
        entity_id: uuid.UUID,
        limit: int = 12,
        evidence_scope: EvidenceScope = EvidenceScope.ANY,
    ) -> list[dict[str, Any]]:
        """
        Execute :meth:`build_cooccurrence_query` and shape the rows.

        The query is built separately so it can be compiled and inspected
        without a database. The ordering tiebreak that keeps a bounded list
        stable (R5) cannot be verified from returned rows -- Postgres happens
        to return small groups in ascending-id order whether or not the
        ``ORDER BY`` asks for it -- so the only way to assert it is to look at
        the statement.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        entity_id : uuid.UUID
            The subject entity.
        limit : int
            Maximum partners to return.
        evidence_scope : EvidenceScope
            Which mentions count as co-occurrence.

        Returns
        -------
        list[dict[str, Any]]
            Dicts with ``entity_id``, ``entity_type``, ``canonical_name``, and
            ``shared_video_count``.
        """
        result = await session.execute(
            self.build_cooccurrence_query(entity_id, limit, evidence_scope)
        )
        return [
            {
                "entity_id": row.partner_id,
                "entity_type": row.entity_type,
                "canonical_name": row.canonical_name,
                "shared_video_count": row.shared,
            }
            for row in result
        ]

    async def get_page_entity_matches(
        self,
        session: AsyncSession,
        *,
        video_ids: Sequence[str],
        entity_ids: Sequence[uuid.UUID],
        evidence_scope: EvidenceScope = EvidenceScope.ANY,
    ) -> dict[str, list[dict[str, Any]]]:
        """
        Fetch per-entity evidence for the videos on the returned page only.

        This is the sole place ``transcript_segments`` is joined. Restricting
        it to the page (at most ``limit`` videos) rather than the full
        qualifying set is the 806 ms -> 98 ms optimization recorded in research
        R1, and the two steps must not be recombined.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        video_ids : Sequence[str]
            Videos on the page being returned. Pass only the page.
        entity_ids : Sequence[uuid.UUID]
            Required entities, matching the qualification subquery.
        evidence_scope : EvidenceScope
            Must match the scope used for qualification, or counts will
            disagree with the set they describe.

        Returns
        -------
        dict[str, list[dict[str, Any]]]
            Keyed by ``video_id``. Each value holds one dict per required
            entity with ``entity_id``, ``entity_type``, ``canonical_name``,
            ``mention_count``, and ``first_timestamp`` (``None`` when the
            entity appears only in the title or description).
        """
        if not video_ids or not entity_ids:
            return {}

        stmt = (
            select(
                EntityMentionDB.video_id,
                EntityMentionDB.entity_id,
                NamedEntityDB.canonical_name,
                NamedEntityDB.entity_type,
                func.count().label("mention_count"),
                func.min(TranscriptSegmentDB.start_time).label("first_timestamp"),
            )
            .join(NamedEntityDB, NamedEntityDB.id == EntityMentionDB.entity_id)
            # Outer join: segment_id is nullable, since title and description
            # mentions have no segment and therefore no timestamp.
            .outerjoin(
                TranscriptSegmentDB,
                TranscriptSegmentDB.id == EntityMentionDB.segment_id,
            )
            .where(
                EntityMentionDB.video_id.in_(list(video_ids)),
                EntityMentionDB.entity_id.in_(list(dict.fromkeys(entity_ids))),
            )
            .group_by(
                EntityMentionDB.video_id,
                EntityMentionDB.entity_id,
                NamedEntityDB.canonical_name,
                NamedEntityDB.entity_type,
            )
        )

        if evidence_scope is EvidenceScope.TRANSCRIPT:
            stmt = stmt.where(
                EntityMentionDB.mention_source.in_(_TRANSCRIPT_SCOPE_SOURCES)
            )

        result = await session.execute(stmt)
        matches: dict[str, list[dict[str, Any]]] = {}
        for row in result:
            matches.setdefault(row.video_id, []).append(
                {
                    "entity_id": row.entity_id,
                    "entity_type": row.entity_type,
                    "canonical_name": row.canonical_name,
                    "mention_count": row.mention_count,
                    "first_timestamp": (
                        float(row.first_timestamp)
                        if row.first_timestamp is not None
                        else None
                    ),
                }
            )
        return matches

    # ── Canonical association resolver (Feature 066) ──────────────────────────
    #
    # One engine behind every association surface — entity list/detail counts,
    # the video panel, and the provenance filter — so the views cannot disagree.
    # `tag` is a derived label, never a stored mention_source (data-model I4).
    _PROVENANCE_SOURCES = ("manual", "transcript", "title", "description", "tag")

    def _mention_assoc_stmt(self, ids: list[uuid.UUID]) -> Select[Any]:
        """``(entity_id, video_id, source)`` for the mention associations.

        A non-manual mention counts only where its text matches one of the
        entity's visible names (canonical + non-ASR aliases, #89); a manual
        mention always counts and is labelled ``manual`` regardless of its
        stored source. One non-correlated relation, no per-row work.

        Shared by ``association_triples`` (which materialises rows) and
        ``get_association_counts`` (which aggregates in SQL), so the mention
        rule has a single definition rather than drifting copies.
        """
        visible_names = union(
            select(
                NamedEntityDB.id.label("entity_id"),
                _folded(NamedEntityDB.canonical_name).label("name_lower"),
            ).where(NamedEntityDB.id.in_(ids)),
            select(
                EntityAliasDB.entity_id.label("entity_id"),
                _folded(EntityAliasDB.alias_name).label("name_lower"),
            ).where(
                EntityAliasDB.entity_id.in_(ids),
                EntityAliasDB.alias_type != EntityAliasType.ASR_ERROR,
            ),
        ).subquery()

        source_label = case(
            (EntityMentionDB.detection_method == "manual", literal("manual")),
            else_=EntityMentionDB.mention_source,
        )
        return (
            select(
                EntityMentionDB.entity_id.label("entity_id"),
                EntityMentionDB.video_id.label("video_id"),
                source_label.label("source"),
            )
            .outerjoin(
                visible_names,
                and_(
                    visible_names.c.entity_id == EntityMentionDB.entity_id,
                    _folded(EntityMentionDB.mention_text) == visible_names.c.name_lower,
                ),
            )
            .where(
                EntityMentionDB.entity_id.in_(ids),
                or_(
                    visible_names.c.name_lower.is_not(None),
                    EntityMentionDB.detection_method == "manual",
                ),
            )
        )

    def _canonical_tag_assoc_stmt(self, ids: list[uuid.UUID]) -> Select[Any]:
        """``(entity_id, video_id, 'tag')`` for canonical-tag associations.

        entity → canonical_tag → tag_alias.raw_form → video_tags, all
        non-correlated joins. Shared with the count aggregator (single
        definition of the canonical-tag rule).
        """
        return (
            select(
                CanonicalTagDB.entity_id.label("entity_id"),
                VideoTagDB.video_id.label("video_id"),
                literal("tag").label("source"),
            )
            .join(TagAliasDB, TagAliasDB.canonical_tag_id == CanonicalTagDB.id)
            .join(VideoTagDB, VideoTagDB.tag == TagAliasDB.raw_form)
            .where(CanonicalTagDB.entity_id.in_(ids))
        )

    async def _alias_tag_pairs(
        self, session: AsyncSession, ids: list[uuid.UUID]
    ) -> list[tuple[uuid.UUID, str]]:
        """``(entity_id, video_id)`` for alias-matched-tag associations.

        Normalisation runs in Python (``TagNormalizationService``) — it cannot
        move into SQL without reimplementing the normalizer, the #207
        duplicate-definition trap. Non-correlated: one alias fetch, one tag
        lookup, mapped back in Python. A normalised form may belong to more
        than one entity. Shared by the triple builder and the count aggregator.
        """
        alias_rows = (
            await session.execute(
                select(EntityAliasDB.entity_id, EntityAliasDB.alias_name).where(
                    EntityAliasDB.entity_id.in_(ids),
                    EntityAliasDB.alias_type != EntityAliasType.ASR_ERROR,
                )
            )
        ).all()
        normalizer = TagNormalizationService()
        form_to_entities: dict[str, set[uuid.UUID]] = {}
        for entity_id, alias_name in alias_rows:
            normalized = normalizer.normalize(alias_name)
            if normalized is not None:
                form_to_entities.setdefault(normalized, set()).add(entity_id)
        if not form_to_entities:
            return []
        pairs: list[tuple[uuid.UUID, str]] = []
        alias_tag_stmt = (
            select(TagAliasDB.normalized_form, VideoTagDB.video_id)
            .join(VideoTagDB, VideoTagDB.tag == TagAliasDB.raw_form)
            .where(TagAliasDB.normalized_form.in_(list(form_to_entities)))
            .distinct()
        )
        for norm, video_id in (await session.execute(alias_tag_stmt)).all():
            for entity_id in form_to_entities.get(norm, set()):
                pairs.append((entity_id, video_id))
        return pairs

    async def association_triples(
        self,
        session: AsyncSession,
        entity_ids: Sequence[uuid.UUID],
    ) -> list[tuple[uuid.UUID, str, str]]:
        """`(entity_id, video_id, source)` for every association of these entities.

        Batched over a page of entities: a fixed number of queries, never
        per-row, and free of correlated subqueries (research.md query-shape
        hazards — correlated EXISTS and join-before-paginate have both regressed
        this repo). ``source`` is one of ``_PROVENANCE_SOURCES``.

        Keyed on ``video_id``, from which per-channel provenance is derivable, so
        a future false-positive-remediation feature can consume these triples and
        join channels without re-plumbing (FR-013). This is the shared hook point
        for the count aggregator, the video panel, and the provenance filter.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        entity_ids : Sequence[uuid.UUID]
            The page of entities to resolve. Empty input returns ``[]``.

        Returns
        -------
        list[tuple[uuid.UUID, str, str]]
            ``(entity_id, video_id, source)`` triples, deduplicated per query but
            possibly repeating a (entity, video) across sources — that is the
            point, since a video may be reached through more than one source.
        """
        if not entity_ids:
            return []
        ids = list(entity_ids)
        triples: list[tuple[uuid.UUID, str, str]] = []

        # Mention triples (visible-name / manual rule) and canonical-tag triples
        # come from the shared path builders; `.distinct()` collapses the join
        # fan-out on the projected tuple, not on a pre-aggregated count.
        for row in (
            await session.execute(self._mention_assoc_stmt(ids).distinct())
        ).all():
            triples.append((row.entity_id, row.video_id, row.source))

        for row in (
            await session.execute(self._canonical_tag_assoc_stmt(ids).distinct())
        ).all():
            triples.append((row.entity_id, row.video_id, "tag"))

        # Alias-matched-tag triples: normalisation is Python-side (#207 trap),
        # so this path yields (entity_id, video_id) pairs rather than a SELECT.
        for entity_id, video_id in await self._alias_tag_pairs(session, ids):
            triples.append((entity_id, video_id, "tag"))

        return triples

    async def get_association_counts(
        self,
        session: AsyncSession,
        entity_ids: Sequence[uuid.UUID],
    ) -> dict[uuid.UUID, AssociationCount]:
        """Distinct-video association count + per-source breakdown, per entity.

        The single definition the entity list and detail both consume, so they
        cannot disagree (FR-001/FR-002). ``total`` is distinct videos across all
        sources — repetition of a name within one field never inflates it
        (FR-003) — and the per-source parts need not sum to ``total`` because a
        video reached through two sources counts once in ``total`` and in each
        contributing source.

        Every requested entity is present in the result, all-zero when it has no
        associations, so a caller iterating a page never hits a missing key.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        entity_ids : Sequence[uuid.UUID]
            The page of entities to count.

        Returns
        -------
        dict[uuid.UUID, AssociationCount]
            One entry per requested entity.
        """
        ids = list(entity_ids)

        def _zero() -> AssociationCount:
            return AssociationCount(
                total=0,
                by_source=AssociationSourceBreakdown(
                    manual=0, transcript=0, title=0, description=0, tag=0
                ),
            )

        counts: dict[uuid.UUID, AssociationCount] = {eid: _zero() for eid in ids}
        if not ids:
            return counts

        # The distinct-video counting happens in Postgres, not Python: the two
        # SQL paths and the Python-derived alias pairs are UNION ALLed and the
        # totals computed with COUNT(DISTINCT video_id) — so a heavy entity's
        # thousands of association rows never cross into Python (only the one
        # aggregated row per entity does). `total` is the union across all
        # sources; each `by_source` part is that source's distinct videos, so
        # the parts need not sum to `total` (a video reached two ways counts
        # once in each and once in the total).
        arms: list[Any] = [
            self._mention_assoc_stmt(ids),
            self._canonical_tag_assoc_stmt(ids),
        ]
        alias_pairs = await self._alias_tag_pairs(session, ids)
        if alias_pairs:
            # Inject the Python-derived alias pairs via two array binds and
            # ``unnest``, NOT a row-per-pair VALUES literal: a heavy page yields
            # tens of thousands of pairs, and three binds each would blow past
            # asyncpg's 32,767 bind-parameter ceiling. Two arrays is two binds
            # regardless of pair count. Expressed as text() because SQLAlchemy's
            # table_valued() does not render the column-alias list for a
            # multi-argument unnest (unnest(a, b) AS t(col1, col2)).
            alias_arm = (
                text(
                    "SELECT e AS entity_id, v AS video_id, 'tag' AS source "
                    "FROM unnest(:alias_entity_ids, :alias_video_ids) AS t(e, v)"
                )
                .bindparams(
                    bindparam(
                        "alias_entity_ids",
                        value=[eid for eid, _ in alias_pairs],
                        type_=ARRAY(Uuid),
                    ),
                    bindparam(
                        "alias_video_ids",
                        value=[vid for _, vid in alias_pairs],
                        type_=ARRAY(String),
                    ),
                )
                .columns(entity_id=Uuid, video_id=String, source=String)
            )
            arms.append(alias_arm)

        assoc = union_all(*arms).subquery("assoc")
        count_stmt = select(
            assoc.c.entity_id,
            func.count(distinct(assoc.c.video_id)).label("total"),
            *[
                func.count(distinct(assoc.c.video_id))
                .filter(assoc.c.source == src)
                .label(src)
                for src in self._PROVENANCE_SOURCES
            ],
        ).group_by(assoc.c.entity_id)

        for row in (await session.execute(count_stmt)).all():
            counts[row.entity_id] = AssociationCount(
                total=row.total,
                by_source=AssociationSourceBreakdown(
                    manual=row.manual,
                    transcript=row.transcript,
                    title=row.title,
                    description=row.description,
                    tag=row.tag,
                ),
            )
        return counts

    async def get_channel_entity_rankings(
        self,
        session: AsyncSession,
        channel_id: str,
    ) -> list[ChannelEntityRankingRow]:
        """Entities on a channel, ranked by distinctiveness (Feature 070 / #171).

        Returns one :class:`ChannelEntityRankingRow` per entity associated with
        any of the channel's videos, ordered: the share-ranked group
        (``channel_video_count >= 2``) by ``share`` descending — tie-broken by
        ``channel_video_count`` desc, then ``corpus_video_count`` asc (rarer
        wins), then display name — followed by the "also appears" group
        (``channel_video_count == 1``) by display name (FR-002/FR-008).

        "Associated" is the **single** Feature 066 definition: a mention (the
        visible-name / manual rule, #89) or a tag (canonical-tag or alias-tag) at
        ``ANY`` scope. Both the channel count and the corpus denominator are
        derived from that one definition — the shared association arms
        (:meth:`_tag_inclusive_association_arms`) — so the corpus denominator
        equals ``get_association_counts(...).total`` by construction and the panel
        cannot drift from the pinned ``/videos?channel_id=&entity_id=`` filter
        (which reuses the same arms since #260) (FR-004/FR-007).

        Query shape (research R2): channel video ids are resolved once; a superset
        of candidate entity ids is discovered through the three association paths
        (over-inclusion is safe — an entity that does not actually appear on the
        channel gets ``channel_video_count == 0`` and is dropped). The channel
        count and the corpus denominator are then computed in **one** set-based
        pass over the arms via a conditional aggregate
        (``COUNT(DISTINCT video_id) FILTER (WHERE <on this channel>)`` for the
        channel count, plain ``COUNT(DISTINCT video_id)`` for the corpus) — no
        second corpus-wide counts query, no correlated subquery, no
        join-before-paginate. The small per-entity result set is scored and
        sorted in Python. (The separate ``get_association_counts`` call this
        previously made dominated latency on entity-dense channels; folding it
        into the same aggregate is the SC-007 optimization — see research R4.)

        Parameters
        ----------
        session : AsyncSession
            The database session.
        channel_id : str
            The channel whose entities to rank.

        Returns
        -------
        list[ChannelEntityRankingRow]
            Ranked rows; empty when the channel has no videos or no associated
            entities. The caller (endpoint) handles the unknown-channel 404.
        """
        # 1. Resolve the channel's video ids (all-videos basis — no availability
        #    filter; FR-003).
        channel_video_ids = list(
            (
                await session.execute(
                    select(VideoDB.video_id).where(VideoDB.channel_id == channel_id)
                )
            ).scalars()
        )
        if not channel_video_ids:
            return []

        # Bind the channel's video-id list as a single Postgres array + ``unnest``
        # rather than one bind per id. Mirrors the arms' own workaround
        # (:meth:`_tag_inclusive_association_arms`) so even a very large channel
        # stays a single bind and never approaches asyncpg's 32,767
        # bind-parameter ceiling. Used at all four channel-video filter sites.
        # ``col`` is a video-id column expression (an ORM attribute or a subquery
        # column); typed ``Any`` to accept both, matching this file's convention
        # for SQLAlchemy expression internals.
        def _in_channel_videos(col: Any) -> Any:
            return col.in_(
                select(
                    func.unnest(
                        bindparam(
                            "channel_video_ids",
                            value=channel_video_ids,
                            type_=ARRAY(String),
                            unique=True,
                        )
                    )
                )
            )

        # 2. Discover a SUPERSET of the entity ids associated with those videos,
        #    via the same three association paths the resolver uses. Over-inclusion
        #    is safe: step 3 recomputes the exact channel count through the shared
        #    arms and drops anything that does not actually qualify.
        candidate_ids: set[uuid.UUID] = set()

        # 2a. mention-path candidates. The visible-name rule (#89) is applied for
        #     real in step 3; this any-mention scan is deliberately a superset.
        candidate_ids.update(
            (
                await session.execute(
                    select(distinct(EntityMentionDB.entity_id)).where(
                        _in_channel_videos(EntityMentionDB.video_id)
                    )
                )
            ).scalars()
        )

        # 2b. canonical-tag-path candidates. ``CanonicalTag.entity_id`` is nullable
        #     (unlinked tags), so drop NULLs even though the WHERE excludes them.
        candidate_ids.update(
            eid
            for eid in (
                await session.execute(
                    select(distinct(CanonicalTagDB.entity_id))
                    .join(TagAliasDB, TagAliasDB.canonical_tag_id == CanonicalTagDB.id)
                    .join(VideoTagDB, VideoTagDB.tag == TagAliasDB.raw_form)
                    .where(
                        _in_channel_videos(VideoTagDB.video_id),
                        CanonicalTagDB.entity_id.is_not(None),
                    )
                )
            ).scalars()
            if eid is not None
        )

        # 2c. alias-tag-path candidates. Normalisation is Python-side (the #207
        #     duplicate-normaliser trap — the stored ``alias_name_normalized`` is
        #     the ENTITY normaliser's output, not the TAG normaliser's, so it must
        #     not be relied on here). Collect the channel's tag normalized_forms,
        #     then keep entities whose non-ASR alias normalises into that set.
        #     Note: the channel_forms query IS channel-scoped, but the alias fetch
        #     below scans the whole (non-ASR) entity_aliases table — its cost is
        #     O(total aliases), not O(channel size). Cheap at current corpus size
        #     (~1.7k rows); revisit if the alias table grows large (perf T019).
        channel_forms = set(
            (
                await session.execute(
                    select(distinct(TagAliasDB.normalized_form))
                    .join(VideoTagDB, VideoTagDB.tag == TagAliasDB.raw_form)
                    .where(_in_channel_videos(VideoTagDB.video_id))
                )
            ).scalars()
        )
        if channel_forms:
            normalizer = TagNormalizationService()
            alias_rows = (
                await session.execute(
                    select(EntityAliasDB.entity_id, EntityAliasDB.alias_name).where(
                        EntityAliasDB.alias_type != EntityAliasType.ASR_ERROR
                    )
                )
            ).all()
            for entity_id, alias_name in alias_rows:
                normalized = normalizer.normalize(alias_name)
                if normalized is not None and normalized in channel_forms:
                    candidate_ids.add(entity_id)

        if not candidate_ids:
            return []

        # 3. Compute BOTH the channel count and the corpus denominator in ONE pass
        #    over the shared association arms. The arms hold every candidate's
        #    associations corpus-wide (they are filtered by entity_id, NOT by
        #    channel), so a conditional aggregate yields the channel count (rows
        #    restricted to the channel's videos) and the corpus count (all rows) at
        #    once — the corpus count equals ``get_association_counts(...).total`` by
        #    construction (same arms, same COUNT(DISTINCT video_id)), so FR-004 and
        #    the ``corpus >= channel`` invariant hold, and the separate, corpus-wide
        #    counts query is avoided (it dominated the latency on large channels).
        assoc = await self._tag_inclusive_association_arms(
            session, list(candidate_ids), EvidenceScope.ANY
        )
        channel_pred = _in_channel_videos(assoc.c.video_id)
        counts_stmt = select(
            assoc.c.entity_id.label("entity_id"),
            func.count(distinct(assoc.c.video_id))
            .filter(channel_pred)
            .label("channel_video_count"),
            func.count(distinct(assoc.c.video_id)).label("corpus_video_count"),
        ).group_by(assoc.c.entity_id)
        # (entity_id -> (channel_count, corpus_count)); keep only entities that
        # actually appear on the channel (discovery over-includes by design).
        counts: dict[uuid.UUID, tuple[int, int]] = {
            row.entity_id: (row.channel_video_count, row.corpus_video_count)
            for row in (await session.execute(counts_stmt)).all()
            if row.channel_video_count > 0
        }
        if not counts:
            return []

        surviving_ids = list(counts)

        # 4. Display fields for the surviving entities.
        display: dict[uuid.UUID, tuple[str, str]] = {
            row.id: (row.canonical_name, row.entity_type)
            for row in (
                await session.execute(
                    select(
                        NamedEntityDB.id,
                        NamedEntityDB.canonical_name,
                        NamedEntityDB.entity_type,
                    ).where(NamedEntityDB.id.in_(surviving_ids))
                )
            ).all()
        }

        # 5. Build rows + share; floor + tie-break in Python over the small set.
        rows: list[ChannelEntityRankingRow] = []
        for eid, (ch_count, corpus_total) in counts.items():
            name, etype = display[eid]
            rows.append(
                ChannelEntityRankingRow(
                    entity_id=eid,
                    display_name=name,
                    entity_type=etype,
                    channel_video_count=ch_count,
                    corpus_video_count=corpus_total,
                    share=ch_count / corpus_total,
                    is_ranked=ch_count >= 2,
                )
            )

        # Ordering (data-model): ranked group first, by share desc, tie-break
        # channel desc -> corpus asc -> display name; then the "also appears"
        # group (channel == 1), by display name. The uniform key keeps the
        # also-appears constants (share/corpus terms) from perturbing its order.
        def _sort_key(r: ChannelEntityRankingRow) -> tuple[int, float, int, int, str]:
            return (
                0 if r.is_ranked else 1,
                -r.share if r.is_ranked else 0.0,
                -r.channel_video_count,
                r.corpus_video_count if r.is_ranked else 0,
                r.display_name,
            )

        rows.sort(key=_sort_key)
        return rows

    async def _visible_name_mention_entity_ids(
        self,
        session: AsyncSession,
        video_id: str,
        language_code: str | None = None,
    ) -> set[uuid.UUID]:
        """Entities with a *visible-name* (or manual) mention on this video.

        Mirrors the entity-detail membership rule (``get_entity_video_list``): a
        non-manual mention counts only where its text matches one of the entity's
        visible names — canonical name or non-ASR alias, the #89 rule — while a
        manual mention always counts. Applying the identical rule here is what
        makes the video panel and the entity detail agree on membership by
        construction (FR-006 / data-model I2). The language filter narrows
        transcript-derived mentions; manual mentions (``language_code`` NULL)
        always pass, exactly as on the entity side.
        """
        visible_names = union(
            select(
                NamedEntityDB.id.label("entity_id"),
                _folded(NamedEntityDB.canonical_name).label("name_lower"),
            ),
            select(
                EntityAliasDB.entity_id.label("entity_id"),
                _folded(EntityAliasDB.alias_name).label("name_lower"),
            ).where(EntityAliasDB.alias_type != EntityAliasType.ASR_ERROR),
        ).subquery()

        stmt = (
            select(distinct(EntityMentionDB.entity_id))
            .outerjoin(
                visible_names,
                and_(
                    visible_names.c.entity_id == EntityMentionDB.entity_id,
                    _folded(EntityMentionDB.mention_text) == visible_names.c.name_lower,
                ),
            )
            .where(
                EntityMentionDB.video_id == video_id,
                or_(
                    visible_names.c.name_lower.is_not(None),
                    EntityMentionDB.detection_method == "manual",
                ),
            )
        )
        if language_code is not None:
            stmt = stmt.where(
                or_(
                    EntityMentionDB.language_code == language_code,
                    EntityMentionDB.detection_method == "manual",
                )
            )
        return set((await session.execute(stmt)).scalars().all())

    async def _video_tag_entity_ids(
        self, session: AsyncSession, video_id: str
    ) -> set[uuid.UUID]:
        """Entity IDs tag-associated with a video (canonical + alias-matched paths).

        The video-keyed inverse of ``_get_tag_associated_video_ids`` and
        ``_get_alias_matched_tag_video_ids``, using the identical joins and the
        identical Python normalisation, so the video panel and the entity detail
        agree on tag membership by construction (FR-006 / I2). Normalisation runs
        in Python because expressing ``TagNormalizationService`` in SQL is the
        duplicate-definition trap of #207. Tags carry no language.
        """
        # Canonical path: video_tags.tag -> tag_aliases.raw_form ->
        # canonical_tags.entity_id.
        canonical_stmt = (
            select(CanonicalTagDB.entity_id)
            .select_from(VideoTagDB)
            .join(TagAliasDB, TagAliasDB.raw_form == VideoTagDB.tag)
            .join(CanonicalTagDB, CanonicalTagDB.id == TagAliasDB.canonical_tag_id)
            .where(
                VideoTagDB.video_id == video_id,
                CanonicalTagDB.entity_id.is_not(None),
            )
            .distinct()
        )
        entity_ids: set[uuid.UUID] = {
            row[0]
            for row in (await session.execute(canonical_stmt)).all()
            if row[0] is not None
        }

        # Alias-matched path: the normalised forms of this video's tags, matched
        # against each entity alias normalised by the SAME service.
        video_forms_stmt = (
            select(TagAliasDB.normalized_form)
            .select_from(VideoTagDB)
            .join(TagAliasDB, TagAliasDB.raw_form == VideoTagDB.tag)
            .where(VideoTagDB.video_id == video_id)
            .distinct()
        )
        video_forms = {
            f
            for f in (await session.execute(video_forms_stmt)).scalars().all()
            if f is not None
        }
        if video_forms:
            alias_rows = (
                await session.execute(
                    select(EntityAliasDB.entity_id, EntityAliasDB.alias_name).where(
                        EntityAliasDB.alias_type != EntityAliasType.ASR_ERROR
                    )
                )
            ).all()
            normalizer = TagNormalizationService()
            for entity_id, alias_name in alias_rows:
                normalized = normalizer.normalize(alias_name)
                if normalized is not None and normalized in video_forms:
                    entity_ids.add(entity_id)
        return entity_ids

    async def get_video_entity_associations(
        self,
        session: AsyncSession,
        video_id: str,
        language_code: str | None = None,
    ) -> list[dict[str, Any]]:
        """Entities associated with a video through **any** source (US2).

        The video panel's read model: the mention-only ``get_video_entity_summary``
        made tag-only and manual-only associations invisible on the video side
        while the entity side listed them (#240). This composes the shared
        membership rules so the two views cannot disagree (FR-005/FR-006 / I2):

        - **Membership** is the strict association set — visible-name/manual
          mentions (``_visible_name_mention_entity_ids``) unioned with tag
          associations (``_video_tag_entity_ids``) — the same rules the entity
          detail applies. A pair supported only by a non-visible-name mention is
          excluded here just as it is there.
        - **Count fields** (``mention_count``, ``first_mention_time``,
          ``has_manual``) come unchanged from ``get_video_entity_summary``; its
          ``mention_count`` still excludes manual, so a manual-only entity reads
          0 — the live optimistic-removal contract the web client relies on.
        - **``sources``** adds ``tag`` to the mention-derived set where the entity
          is tag-associated; tag-only entities report ``["tag"]``.

        Returns dicts matching ``VideoEntitySummary``, sorted by ``mention_count``
        descending then name.
        """
        summary = await self.get_video_entity_summary(session, video_id, language_code)
        summary_by_id = {uuid.UUID(row["entity_id"]): row for row in summary}

        strict_mention_ids = await self._visible_name_mention_entity_ids(
            session, video_id, language_code
        )
        tag_ids = await self._video_tag_entity_ids(session, video_id)

        members = strict_mention_ids | tag_ids
        if not members:
            return []

        # Names for tag-only members — they have no mention row to borrow from.
        missing = [eid for eid in members if eid not in summary_by_id]
        names: dict[uuid.UUID, tuple[str, str, str | None]] = {}
        if missing:
            name_rows = (
                await session.execute(
                    select(
                        NamedEntityDB.id,
                        NamedEntityDB.canonical_name,
                        NamedEntityDB.entity_type,
                        NamedEntityDB.description,
                    ).where(NamedEntityDB.id.in_(missing))
                )
            ).all()
            names = {
                r.id: (r.canonical_name, r.entity_type, r.description)
                for r in name_rows
            }

        out: list[dict[str, Any]] = []
        for eid in members:
            base = summary_by_id.get(eid)
            if base is not None:
                sources = set(base["sources"])
                if eid in tag_ids:
                    sources.add("tag")
                out.append({**base, "sources": sorted(sources)})
            else:
                canonical_name, entity_type, description = names.get(
                    eid, ("", "", None)
                )
                out.append(
                    {
                        "entity_id": str(eid),
                        "canonical_name": canonical_name,
                        "entity_type": entity_type,
                        "description": description,
                        "mention_count": 0,
                        "first_mention_time": None,
                        "sources": ["tag"],
                        "has_manual": False,
                    }
                )

        out.sort(key=lambda r: (-r["mention_count"], r["canonical_name"].lower()))
        return out

    async def get_combined_video_count(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
    ) -> int:
        """Get the combined deduplicated video count for an entity.

        Computes the total number of unique videos associated with an entity
        across all three sources (transcript mentions, canonical tag
        associations, alias-matched tag associations) without fetching
        full video details.

        This is a lightweight alternative to ``get_entity_video_list()``
        for use cases that only need the count (e.g., entity detail header
        video_count field per FR-007 / T030).

        Parameters
        ----------
        session : AsyncSession
            The database session.
        entity_id : uuid.UUID
            The named entity UUID.

        Returns
        -------
        int
            The deduplicated count of distinct video IDs from all sources.
        """
        # Step 1: Fetch transcript-mention video IDs (no language filter —
        # the header count should reflect all languages).
        canonical_names = select(
            _folded(NamedEntityDB.canonical_name).label("name_lower"),
        ).where(NamedEntityDB.id == entity_id)

        non_asr_aliases = select(
            _folded(EntityAliasDB.alias_name).label("name_lower"),
        ).where(
            EntityAliasDB.entity_id == entity_id,
            EntityAliasDB.alias_type != EntityAliasType.ASR_ERROR,
        )

        visible_names = union(canonical_names, non_asr_aliases).subquery()

        mention_filter = and_(
            EntityMentionDB.entity_id == entity_id,
            or_(
                _folded(EntityMentionDB.mention_text) == visible_names.c.name_lower,
                EntityMentionDB.detection_method == "manual",
            ),
        )

        transcript_vid_stmt = (
            select(distinct(EntityMentionDB.video_id))
            .outerjoin(
                visible_names,
                _folded(EntityMentionDB.mention_text) == visible_names.c.name_lower,
            )
            .where(mention_filter)
        )
        transcript_vid_result = await session.execute(transcript_vid_stmt)
        transcript_video_ids: set[str] = set(transcript_vid_result.scalars().all())

        # Step 2: Fetch tag-associated video IDs
        canonical_tag_video_ids = await self._get_tag_associated_video_ids(
            session, entity_id
        )
        alias_tag_video_ids = await self._get_alias_matched_tag_video_ids(
            session, entity_id
        )
        tag_video_ids = canonical_tag_video_ids | alias_tag_video_ids

        # Deduplicated union
        all_video_ids = transcript_video_ids | tag_video_ids
        return len(all_video_ids)

    async def get_statistics(
        self,
        session: AsyncSession,
        entity_type: str | None = None,
    ) -> dict[str, Any]:
        """Get aggregate statistics about entity mentions.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        entity_type : str | None
            Optional filter by entity type.

        Returns
        -------
        dict[str, Any]
            Dictionary with total_mentions, unique_entities_with_mentions,
            unique_videos_with_mentions, total_entities, coverage_pct,
            type_breakdown, and top_entities.
        """
        mention_filters: list[Any] = []
        entity_filters: list[Any] = []

        if entity_type is not None:
            # Filter mentions to only those for entities of this type
            entity_ids_subq = (
                select(NamedEntityDB.id)
                .where(NamedEntityDB.entity_type == entity_type)
                .scalar_subquery()
            )
            mention_filters.append(EntityMentionDB.entity_id.in_(entity_ids_subq))
            entity_filters.append(NamedEntityDB.entity_type == entity_type)

        # Total mentions
        total_mentions_stmt = select(func.count()).select_from(EntityMentionDB)
        if mention_filters:
            total_mentions_stmt = total_mentions_stmt.where(*mention_filters)
        total_mentions = (await session.execute(total_mentions_stmt)).scalar() or 0

        # Unique entities with mentions
        unique_entities_stmt = select(func.count(distinct(EntityMentionDB.entity_id)))
        if mention_filters:
            unique_entities_stmt = unique_entities_stmt.where(*mention_filters)
        unique_entities = (await session.execute(unique_entities_stmt)).scalar() or 0

        # Unique videos with mentions
        unique_videos_stmt = select(func.count(distinct(EntityMentionDB.video_id)))
        if mention_filters:
            unique_videos_stmt = unique_videos_stmt.where(*mention_filters)
        unique_videos = (await session.execute(unique_videos_stmt)).scalar() or 0

        # Total entities (all, regardless of mentions)
        total_entities_stmt = select(func.count()).select_from(NamedEntityDB)
        if entity_filters:
            total_entities_stmt = total_entities_stmt.where(*entity_filters)
        total_entities = (await session.execute(total_entities_stmt)).scalar() or 0

        # Coverage percentage
        coverage_pct = (
            round((unique_entities / total_entities) * 100, 2)
            if total_entities > 0
            else 0.0
        )

        # Type breakdown: count mentions per entity_type
        type_breakdown_stmt = (
            select(
                NamedEntityDB.entity_type,
                func.count().label("mention_count"),
                func.count(distinct(EntityMentionDB.entity_id)).label("entity_count"),
            )
            .join(NamedEntityDB, EntityMentionDB.entity_id == NamedEntityDB.id)
            .group_by(NamedEntityDB.entity_type)
            .order_by(func.count().desc())
        )
        if mention_filters:
            type_breakdown_stmt = type_breakdown_stmt.where(*mention_filters)
        type_rows = (await session.execute(type_breakdown_stmt)).all()
        type_breakdown = [
            {
                "entity_type": row.entity_type,
                "mention_count": row.mention_count,
                "entity_count": row.entity_count,
            }
            for row in type_rows
        ]

        # Top entities by video_count
        top_entities_stmt = (
            select(
                EntityMentionDB.entity_id,
                NamedEntityDB.canonical_name,
                NamedEntityDB.entity_type,
                func.count().label("mention_count"),
                func.count(distinct(EntityMentionDB.video_id)).label("video_count"),
            )
            .join(NamedEntityDB, EntityMentionDB.entity_id == NamedEntityDB.id)
            .group_by(
                EntityMentionDB.entity_id,
                NamedEntityDB.canonical_name,
                NamedEntityDB.entity_type,
            )
            .order_by(func.count(distinct(EntityMentionDB.video_id)).desc())
            .limit(20)
        )
        if mention_filters:
            top_entities_stmt = top_entities_stmt.where(*mention_filters)
        top_rows = (await session.execute(top_entities_stmt)).all()
        top_entities = [
            {
                "entity_id": str(row.entity_id),
                "canonical_name": row.canonical_name,
                "entity_type": row.entity_type,
                "mention_count": row.mention_count,
                "video_count": row.video_count,
            }
            for row in top_rows
        ]

        return {
            "total_mentions": total_mentions,
            "unique_entities_with_mentions": unique_entities,
            "unique_videos_with_mentions": unique_videos,
            "total_entities": total_entities,
            "coverage_pct": coverage_pct,
            "type_breakdown": type_breakdown,
            "top_entities": top_entities,
        }

    async def get_entity_video_ids(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
    ) -> set[str]:
        """Return all video IDs associated with an entity via two paths.

        Path 1: Direct entity mentions — ``entity_mentions.video_id``
        where ``entity_id`` matches.

        Path 2: Tag-based — canonical tags linked to the entity, through
        ``canonical_tags`` -> ``tag_aliases`` -> ``video_tags``.

        The union of both paths ensures forward-compatibility: any new
        association type adding rows to ``entity_mentions`` automatically
        expands scope.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        entity_id : uuid.UUID
            The named entity UUID.

        Returns
        -------
        set[str]
            Unique video IDs associated with the entity.
        """
        # Path 1: direct entity mentions
        path1 = select(distinct(EntityMentionDB.video_id).label("video_id")).where(
            EntityMentionDB.entity_id == entity_id
        )

        # Path 2: tag-based — canonical_tags → tag_aliases → video_tags
        path2 = (
            select(distinct(VideoTagDB.video_id).label("video_id"))
            .join(
                TagAliasDB,
                VideoTagDB.tag == TagAliasDB.raw_form,
            )
            .join(
                CanonicalTagDB,
                TagAliasDB.canonical_tag_id == CanonicalTagDB.id,
            )
            .where(CanonicalTagDB.entity_id == entity_id)
        )

        combined = union(path1, path2)
        result = await session.execute(combined)
        return set(result.scalars().all())

    async def search_entities(
        self,
        session: AsyncSession,
        query: str,
        video_id: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Search named entities by canonical name or alias for autocomplete.

        Performs ILIKE prefix search on ``named_entities.canonical_name`` and
        ``entity_aliases.alias_name``, deduplicates by entity_id, and
        optionally checks whether each entity is already linked to a video.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        query : str
            Search query (minimum 2 characters).
        video_id : str | None
            Optional video ID; when provided, each result includes
            ``is_linked`` and ``link_sources`` fields.
        limit : int
            Maximum number of results to return (default 10).

        Returns
        -------
        list[dict[str, Any]]
            List of entity dicts matching EntitySearchResult schema.

        Raises
        ------
        ValueError
            If query is shorter than 2 characters.
        """
        if len(query) < 2:
            raise ValueError("Search query must be at least 2 characters")

        pattern = f"{query}%"

        # Canonical name matches
        canonical_stmt = select(
            NamedEntityDB.id.label("entity_id"),
            NamedEntityDB.canonical_name,
            NamedEntityDB.entity_type,
            NamedEntityDB.description,
            NamedEntityDB.status,
            type_coerce(literal(None), String).label("matched_alias"),
        ).where(NamedEntityDB.canonical_name.ilike(pattern))

        # Alias matches — only include if canonical name did NOT match
        alias_stmt = (
            select(
                NamedEntityDB.id.label("entity_id"),
                NamedEntityDB.canonical_name,
                NamedEntityDB.entity_type,
                NamedEntityDB.description,
                NamedEntityDB.status,
                EntityAliasDB.alias_name.label("matched_alias"),
            )
            .join(EntityAliasDB, NamedEntityDB.id == EntityAliasDB.entity_id)
            .where(
                EntityAliasDB.alias_name.ilike(pattern),
                ~NamedEntityDB.canonical_name.ilike(pattern),
            )
        )

        combined = union(canonical_stmt, alias_stmt).subquery()
        outer_stmt = select(combined)
        result = await session.execute(outer_stmt)
        rows = result.all()

        # Deduplicate by entity_id (keep first occurrence — canonical match
        # appears first from UNION which removes exact duplicates)
        seen: set[uuid.UUID] = set()
        unique_rows: list[Any] = []
        for row in rows:
            eid = row.entity_id
            if eid not in seen:
                seen.add(eid)
                unique_rows.append(row)

        # Sort by relevance tiers:
        # 1. Exact canonical match (canonical_name ILIKE query exactly)
        # 2. Prefix canonical match (matched_alias is None)
        # 3. Alias match (matched_alias is not None)
        # Within each tier: alphabetical by canonical_name
        query_lower = query.lower()

        def sort_key(row: Any) -> tuple[int, str]:
            if row.matched_alias is None:
                # Canonical name matched
                if row.canonical_name.lower() == query_lower:
                    return (0, row.canonical_name.lower())
                return (1, row.canonical_name.lower())
            return (2, row.canonical_name.lower())

        unique_rows.sort(key=sort_key)
        unique_rows = unique_rows[:limit]

        # Build is_linked / link_sources if video_id provided
        linked_map: dict[uuid.UUID, list[str]] = {}
        if video_id is not None:
            entity_ids = [r.entity_id for r in unique_rows]
            if entity_ids:
                link_stmt = select(
                    EntityMentionDB.entity_id,
                    EntityMentionDB.detection_method,
                ).where(
                    EntityMentionDB.entity_id.in_(entity_ids),
                    EntityMentionDB.video_id == video_id,
                )
                link_result = await session.execute(link_stmt)
                for link_row in link_result.all():
                    eid = link_row.entity_id
                    if eid not in linked_map:
                        linked_map[eid] = []
                    method = link_row.detection_method
                    if method not in linked_map[eid]:
                        linked_map[eid].append(method)

        results: list[dict[str, Any]] = []
        for row in unique_rows:
            entry: dict[str, Any] = {
                "entity_id": str(row.entity_id),
                "canonical_name": row.canonical_name,
                "entity_type": row.entity_type,
                "description": row.description,
                "status": row.status,
                "matched_alias": row.matched_alias,
            }
            if video_id is not None:
                sources = linked_map.get(row.entity_id, [])
                entry["is_linked"] = len(sources) > 0
                entry["link_sources"] = sorted(sources)
            else:
                entry["is_linked"] = None
                entry["link_sources"] = None
            results.append(entry)

        return results

    async def create_manual_association(
        self,
        session: AsyncSession,
        video_id: str,
        entity_id: uuid.UUID,
    ) -> EntityMentionDB:
        """Create a manual entity-video association.

        Validates that the video and entity exist, the entity is not
        deprecated, and no duplicate manual association exists before
        creating a new ``entity_mentions`` row with
        ``detection_method='manual'``.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        video_id : str
            YouTube video ID.
        entity_id : uuid.UUID
            Named entity UUID.

        Returns
        -------
        EntityMentionDB
            The created entity mention row.

        Raises
        ------
        NotFoundError
            If the video or entity does not exist.
        APIValidationError
            If the entity is deprecated.
        ConflictError
            If a manual association already exists for this entity+video.
        """
        # 1. Check video exists
        video_result = await session.execute(
            select(VideoDB.video_id).where(VideoDB.video_id == video_id)
        )
        if video_result.scalar_one_or_none() is None:
            raise NotFoundError(resource_type="Video", identifier=video_id)

        # 2. Check entity exists
        entity_result = await session.execute(
            select(NamedEntityDB).where(NamedEntityDB.id == entity_id)
        )
        entity = entity_result.scalar_one_or_none()
        if entity is None:
            raise NotFoundError(resource_type="Entity", identifier=str(entity_id))

        # 3. Check entity not deprecated
        if entity.status == "deprecated":
            raise APIValidationError(
                message=(
                    f"Entity '{entity.canonical_name}' has been deprecated "
                    f"and cannot be manually associated"
                ),
                details={
                    "entity_id": str(entity_id),
                    "status": entity.status,
                },
            )

        # 4. Check no existing manual association
        existing_result = await session.execute(
            select(EntityMentionDB).where(
                EntityMentionDB.entity_id == entity_id,
                EntityMentionDB.video_id == video_id,
                EntityMentionDB.detection_method == "manual",
            )
        )
        if existing_result.scalar_one_or_none() is not None:
            raise ConflictError(
                message=(
                    f"Manual association already exists for entity "
                    f"'{entity.canonical_name}' on video '{video_id}'"
                ),
                details={
                    "entity_id": str(entity_id),
                    "video_id": video_id,
                },
            )

        # 5. Create the mention. A manual assertion has no text anchor, so its
        # provenance is honestly 'manual' — not 'transcript' (Feature 066 US4).
        mention = EntityMentionDB(
            id=uuid.UUID(bytes=uuid7().bytes),
            entity_id=entity_id,
            segment_id=None,
            video_id=video_id,
            language_code=None,
            mention_text=entity.canonical_name,
            mention_source=MentionSource.MANUAL.value,
            detection_method="manual",
            confidence=None,
            match_start=None,
            match_end=None,
        )
        session.add(mention)
        await session.flush()

        # 6. Update entity counters
        await self.update_entity_counters(session, [entity_id])

        return mention

    async def delete_manual_association(
        self,
        session: AsyncSession,
        video_id: str,
        entity_id: uuid.UUID,
    ) -> None:
        """Delete a manual entity-video association.

        Finds and removes the ``entity_mentions`` row with
        ``detection_method='manual'`` for the given video and entity,
        then updates the entity counters within the same transaction.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        video_id : str
            YouTube video ID.
        entity_id : uuid.UUID
            Named entity UUID.

        Raises
        ------
        NotFoundError
            If no manual association exists for this entity+video.
        """
        result = await session.execute(
            select(EntityMentionDB).where(
                EntityMentionDB.entity_id == entity_id,
                EntityMentionDB.video_id == video_id,
                EntityMentionDB.detection_method == "manual",
            )
        )
        mention = result.scalar_one_or_none()
        if mention is None:
            raise NotFoundError(
                resource_type="ManualAssociation",
                identifier=f"entity={entity_id}, video={video_id}",
            )

        await session.delete(mention)
        await session.flush()

        await self.update_entity_counters(session, [entity_id])

    async def _get_tag_associated_video_ids(
        self, session: AsyncSession, entity_id: uuid.UUID
    ) -> set[str]:
        """Get video IDs associated with an entity via canonical tag linkage.

        Follows the query path: canonical_tags (entity_id) -> tag_aliases
        (canonical_tag_id) -> video_tags (tag = raw_form).

        Does NOT filter by canonical_tags.status -- deprecated tags still
        return their associated videos (Decision 8).

        Parameters
        ----------
        session : AsyncSession
            The database session.
        entity_id : uuid.UUID
            The named entity UUID.

        Returns
        -------
        set[str]
            Set of video_id strings from the tag association path.
            Empty set if the entity has no linked canonical tags.
        """
        stmt = (
            select(VideoTagDB.video_id)
            .select_from(CanonicalTagDB)
            .join(
                TagAliasDB,
                TagAliasDB.canonical_tag_id == CanonicalTagDB.id,
            )
            .join(
                VideoTagDB,
                VideoTagDB.tag == TagAliasDB.raw_form,
            )
            .where(CanonicalTagDB.entity_id == entity_id)
            .distinct()
        )
        result = await session.execute(stmt)
        return set(result.scalars().all())

    async def _get_alias_matched_tag_video_ids(
        self, session: AsyncSession, entity_id: uuid.UUID
    ) -> set[str]:
        """Get video IDs by matching entity aliases against tag normalized forms.

        For each entity alias, normalizes the alias_name using
        TagNormalizationService, then matches against tag_aliases.normalized_form
        to find associated videos via video_tags.

        ASR error aliases (alias_type='asr_error') are excluded because they are
        transcript-specific patterns (e.g., "Emile", "edsger") that produce false
        positives when matched against YouTube tags.

        Aliases whose normalized form is None are silently skipped (Decision 7).
        Uses exact equality matching, not ILIKE (Decision 10).

        Parameters
        ----------
        session : AsyncSession
            The database session.
        entity_id : uuid.UUID
            The named entity UUID.

        Returns
        -------
        set[str]
            Set of video_id strings from the alias-matched tag path.
            Empty set if the entity has no aliases or no aliases match tags.
        """
        # Fetch non-ASR aliases for this entity (ASR error aliases are
        # transcript-specific patterns that produce false positives against tags)
        alias_stmt = select(EntityAliasDB.alias_name).where(
            EntityAliasDB.entity_id == entity_id,
            EntityAliasDB.alias_type != EntityAliasType.ASR_ERROR,
        )
        alias_result = await session.execute(alias_stmt)
        alias_names: list[str] = list(alias_result.scalars().all())

        if not alias_names:
            return set()

        # Normalize each alias using the tag normalization pipeline
        normalizer = TagNormalizationService()
        normalized_forms: list[str] = []
        for alias_name in alias_names:
            normalized = normalizer.normalize(alias_name)
            if normalized is not None:
                normalized_forms.append(normalized)

        if not normalized_forms:
            return set()

        # Query: tag_aliases WHERE normalized_form IN (...) -> video_tags
        stmt = (
            select(VideoTagDB.video_id)
            .select_from(TagAliasDB)
            .join(
                VideoTagDB,
                VideoTagDB.tag == TagAliasDB.raw_form,
            )
            .where(TagAliasDB.normalized_form.in_(normalized_forms))
            .distinct()
        )
        result = await session.execute(stmt)
        return set(result.scalars().all())
