"""
Entity mention repository for tracking named entity occurrences in transcripts.

Handles bulk insert, scoped deletion, aggregation queries, and counter updates
for the entity_mentions table.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import (
    String,
    and_,
    delete,
    distinct,
    func,
    literal,
    or_,
    select,
    type_coerce,
    union,
    update,
)
from sqlalchemy.dialects.postgresql import insert
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
from chronovista.models.entity_mention import EntityMentionCreate
from chronovista.models.enums import EntityAliasType
from chronovista.repositories.base import BaseSQLAlchemyRepository
from chronovista.services.tag_normalization import TagNormalizationService


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

    async def get(
        self, session: AsyncSession, id: uuid.UUID
    ) -> EntityMentionDB | None:
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

        stmt = (
            insert(EntityMentionDB)
            .values(values)
            .on_conflict_do_nothing()
        )
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

        stmt = (
            select(distinct(EntityMentionDB.entity_id))
            .where(EntityMentionDB.correction_id.in_(correction_ids))
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
        mentioned_subq = (
            select(distinct(EntityMentionDB.entity_id))
            .scalar_subquery()
        )

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
            func.lower(NamedEntityDB.canonical_name).label("name_lower"),
        ).where(NamedEntityDB.id.in_(entity_ids))

        non_asr_aliases = select(
            EntityAliasDB.entity_id,
            func.lower(EntityAliasDB.alias_name).label("name_lower"),
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
                    func.lower(EntityMentionDB.mention_text)
                    == visible_names.c.name_lower,
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
        entities_with_visible_mentions = (
            select(agg_subq.c.entity_id).scalar_subquery()
        )
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
                func.lower(EntityMentionDB.mention_text).label("mention_lower"),
                func.count().label("cnt"),
            )
            .where(EntityMentionDB.entity_id.in_(entity_ids))
            .group_by(
                EntityMentionDB.entity_id,
                func.lower(EntityMentionDB.mention_text),
            )
            .subquery()
        )

        # Join aliases to mention counts on (entity_id, lower(alias_name))
        # and update occurrence_count
        update_stmt = (
            update(EntityAliasDB)
            .where(
                EntityAliasDB.entity_id == mention_counts_subq.c.entity_id,
                func.lower(EntityAliasDB.alias_name)
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
                    func.lower(EntityAliasDB.alias_name)
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

    # Category mapping for detection methods → source categories
    _SOURCE_CATEGORY_MAP: dict[str, str] = {
        "rule_match": "transcript",
        "spacy_ner": "transcript",
        "llm_extraction": "transcript",
        "manual": "manual",
        "user_correction": "transcript",
    }

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
        # Use array_agg to collect distinct detection methods per entity
        stmt = (
            select(
                EntityMentionDB.entity_id,
                NamedEntityDB.canonical_name,
                NamedEntityDB.entity_type,
                NamedEntityDB.description,
                func.count(
                    distinct(EntityMentionDB.segment_id)
                ).label("mention_count"),
                func.min(TranscriptSegmentDB.start_time).label(
                    "first_mention_time"
                ),
                func.array_agg(
                    distinct(EntityMentionDB.detection_method)
                ).label("detection_methods"),
                func.bool_or(
                    EntityMentionDB.detection_method == "manual"
                ).label("has_manual"),
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
            .order_by(
                func.count(distinct(EntityMentionDB.segment_id)).desc()
            )
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
                "sources": sorted(
                    {
                        self._SOURCE_CATEGORY_MAP.get(dm, dm)
                        for dm in (row.detection_methods or [])
                    }
                ),
                "has_manual": bool(row.has_manual),
            }
            for row in rows
        ]

    # Transcript-derived detection methods (excludes manual).
    _TRANSCRIPT_METHODS = {"rule_match", "spacy_ner", "llm_extraction", "user_correction"}

    async def get_entity_video_list(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        language_code: str | None = None,
        source_filter: str | None = None,
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
        source_filter : str | None
            Optional source filter: ``"transcript"``, ``"title"``,
            ``"description"``, ``"tag"``, or ``"manual"``.  When provided,
            only videos whose ``sources`` list contains the given value are
            returned. Affects both the result set and the total count.
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
            func.lower(NamedEntityDB.canonical_name).label("name_lower"),
        ).where(NamedEntityDB.id == entity_id)

        non_asr_aliases = select(
            func.lower(EntityAliasDB.alias_name).label("name_lower"),
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
                func.lower(EntityMentionDB.mention_text)
                == visible_names.c.name_lower,
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
                func.lower(EntityMentionDB.mention_text)
                == visible_names.c.name_lower,
            )
            .where(mention_filter)
        )
        if lang_filter is not None:
            transcript_vid_stmt = transcript_vid_stmt.where(lang_filter)

        transcript_vid_result = await session.execute(transcript_vid_stmt)
        transcript_video_ids: set[str] = set(
            transcript_vid_result.scalars().all()
        )

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
                        EntityMentionDB.detection_method.in_(
                            self._TRANSCRIPT_METHODS
                        ),
                        EntityMentionDB.mention_source == "transcript",
                    )
                    .label("mention_count"),
                    # Collect distinct detection methods for source mapping
                    func.array_agg(
                        distinct(EntityMentionDB.detection_method)
                    ).label("detection_methods"),
                    # Collect distinct mention sources
                    func.array_agg(
                        distinct(EntityMentionDB.mention_source)
                    ).label("mention_sources"),
                    # Has manual flag
                    func.bool_or(
                        EntityMentionDB.detection_method == "manual"
                    ).label("has_manual"),
                    # First mention time from transcript segments (LEFT JOIN)
                    func.min(TranscriptSegmentDB.start_time).label(
                        "first_mention_time"
                    ),
                    # Upload date for sorting
                    VideoDB.upload_date,
                )
                .outerjoin(
                    visible_names,
                    func.lower(EntityMentionDB.mention_text)
                    == visible_names.c.name_lower,
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
                # Map detection methods to source categories
                sources_set: set[str] = {
                    self._SOURCE_CATEGORY_MAP.get(dm, dm)
                    for dm in (row.detection_methods or [])
                }
                # Add mention_source values directly (title, description)
                for ms in (row.mention_sources or []):
                    if ms in ("title", "description"):
                        sources_set.add(ms)
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
                        func.lower(EntityMentionDB.mention_text)
                        == visible_names.c.name_lower,
                    )
                    .where(
                        EntityMentionDB.entity_id == entity_id,
                        EntityMentionDB.video_id == row.video_id,
                        EntityMentionDB.detection_method != "manual",
                        or_(
                            func.lower(EntityMentionDB.mention_text)
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
            has_transcript = 1 if item["mention_count"] > 0 or any(
                s in ("transcript", "manual") for s in item["sources"]
            ) else 0
            return (
                has_transcript,
                item["mention_count"],
                item["upload_date"] or "",
            )

        sorted_results = sorted(
            results_dict.values(), key=_sort_key, reverse=True
        )

        # ------------------------------------------------------------------
        # Step 5b: Apply source_filter if provided (T064, FR-031)
        # ------------------------------------------------------------------
        if source_filter is not None:
            sorted_results = [
                item
                for item in sorted_results
                if source_filter in item["sources"]
            ]

        # ------------------------------------------------------------------
        # Step 6: Apply pagination to the merged, sorted results (T015)
        # ------------------------------------------------------------------
        filtered_total = len(sorted_results)
        paginated = sorted_results[offset : offset + limit]

        return paginated, filtered_total if source_filter is not None else total_count

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
            func.lower(NamedEntityDB.canonical_name).label("name_lower"),
        ).where(NamedEntityDB.id == entity_id)

        non_asr_aliases = select(
            func.lower(EntityAliasDB.alias_name).label("name_lower"),
        ).where(
            EntityAliasDB.entity_id == entity_id,
            EntityAliasDB.alias_type != EntityAliasType.ASR_ERROR,
        )

        visible_names = union(canonical_names, non_asr_aliases).subquery()

        mention_filter = and_(
            EntityMentionDB.entity_id == entity_id,
            or_(
                func.lower(EntityMentionDB.mention_text)
                == visible_names.c.name_lower,
                EntityMentionDB.detection_method == "manual",
            ),
        )

        transcript_vid_stmt = (
            select(distinct(EntityMentionDB.video_id))
            .outerjoin(
                visible_names,
                func.lower(EntityMentionDB.mention_text)
                == visible_names.c.name_lower,
            )
            .where(mention_filter)
        )
        transcript_vid_result = await session.execute(transcript_vid_stmt)
        transcript_video_ids: set[str] = set(
            transcript_vid_result.scalars().all()
        )

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
        unique_entities_stmt = select(
            func.count(distinct(EntityMentionDB.entity_id))
        )
        if mention_filters:
            unique_entities_stmt = unique_entities_stmt.where(*mention_filters)
        unique_entities = (await session.execute(unique_entities_stmt)).scalar() or 0

        # Unique videos with mentions
        unique_videos_stmt = select(
            func.count(distinct(EntityMentionDB.video_id))
        )
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
        path1 = (
            select(distinct(EntityMentionDB.video_id).label("video_id"))
            .where(EntityMentionDB.entity_id == entity_id)
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
        canonical_stmt = (
            select(
                NamedEntityDB.id.label("entity_id"),
                NamedEntityDB.canonical_name,
                NamedEntityDB.entity_type,
                NamedEntityDB.description,
                NamedEntityDB.status,
                type_coerce(literal(None), String).label("matched_alias"),
            )
            .where(NamedEntityDB.canonical_name.ilike(pattern))
        )

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
                link_stmt = (
                    select(
                        EntityMentionDB.entity_id,
                        EntityMentionDB.detection_method,
                    )
                    .where(
                        EntityMentionDB.entity_id.in_(entity_ids),
                        EntityMentionDB.video_id == video_id,
                    )
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
            raise NotFoundError(
                resource_type="Entity", identifier=str(entity_id)
            )

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

        # 5. Create the mention
        mention = EntityMentionDB(
            id=uuid.UUID(bytes=uuid7().bytes),
            entity_id=entity_id,
            segment_id=None,
            video_id=video_id,
            language_code=None,
            mention_text=entity.canonical_name,
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
        transcript-specific patterns (e.g., "Andres", "elon") that produce false
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
