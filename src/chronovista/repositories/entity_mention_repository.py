"""
Entity mention repository for tracking named entity occurrences in transcripts.

Handles bulk insert, scoped deletion, aggregation queries, and counter updates
for the entity_mentions table.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

from sqlalchemy import (
    and_,
    delete,
    distinct,
    func,
    select,
    union,
    union_all,
    update,
)

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.db.models import (
    CanonicalTag as CanonicalTagDB,
    Channel,
    EntityAlias as EntityAliasDB,
    EntityMention as EntityMentionDB,
    NamedEntity as NamedEntityDB,
    TagAlias as TagAliasDB,
    TranscriptSegment as TranscriptSegmentDB,
    Video as VideoDB,
    VideoTag as VideoTagDB,
)
from chronovista.models.entity_mention import EntityMentionCreate
from chronovista.models.enums import EntityAliasType
from chronovista.repositories.base import BaseSQLAlchemyRepository


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
    ) -> Optional[EntityMentionDB]:
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

        Uses INSERT ... ON CONFLICT (entity_id, segment_id, match_start) DO NOTHING
        for efficient bulk insertion with automatic deduplication.

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
        # Convert detection_method enum to its string value
        for v in values:
            if hasattr(v["detection_method"], "value"):
                v["detection_method"] = v["detection_method"].value

        stmt = (
            insert(EntityMentionDB)
            .values(values)
            .on_conflict_do_nothing(
                constraint="uq_entity_mention_entity_segment_position"
            )
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
    ) -> int:
        """Delete mentions matching the given scope filters.

        Used by --full rescan to clear existing mentions before re-detection.

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

        visible_names = union_all(canonical_names, non_asr_aliases).subquery()

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

    async def get_video_entity_summary(
        self,
        session: AsyncSession,
        video_id: str,
        language_code: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get entity summary for a video.

        GROUP BY entity_id with COUNT(distinct segment_id) as mention_count,
        MIN(start_time) as first_mention_time. JOINs named_entities for
        canonical_name, entity_type, description. Sorted by mention_count DESC.

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
            List of dicts matching VideoEntitySummary schema.
        """
        stmt = (
            select(
                EntityMentionDB.entity_id,
                NamedEntityDB.canonical_name,
                NamedEntityDB.entity_type,
                NamedEntityDB.description,
                func.count(distinct(EntityMentionDB.segment_id)).label("mention_count"),
                func.min(TranscriptSegmentDB.start_time).label("first_mention_time"),
            )
            .join(
                NamedEntityDB,
                EntityMentionDB.entity_id == NamedEntityDB.id,
            )
            .join(
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
            .order_by(func.count(distinct(EntityMentionDB.segment_id)).desc())
        )

        if language_code is not None:
            stmt = stmt.where(EntityMentionDB.language_code == language_code)

        result = await session.execute(stmt)
        rows = result.all()

        return [
            {
                "entity_id": str(row.entity_id),
                "canonical_name": row.canonical_name,
                "entity_type": row.entity_type,
                "description": row.description,
                "mention_count": row.mention_count,
                "first_mention_time": row.first_mention_time,
            }
            for row in rows
        ]

    async def get_entity_video_list(
        self,
        session: AsyncSession,
        entity_id: uuid.UUID,
        language_code: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Get paginated list of videos where an entity is mentioned.

        GROUP BY video_id with COUNT as mention_count. JOINs videos for title,
        channels for channel_name. Each result includes up to 5 mention previews.

        Parameters
        ----------
        session : AsyncSession
            The database session.
        entity_id : uuid.UUID
            The named entity UUID.
        language_code : str | None
            Optional language filter.
        limit : int
            Maximum results per page.
        offset : int
            Pagination offset.

        Returns
        -------
        tuple[list[dict[str, Any]], int]
            Tuple of (results list, total count of distinct videos).
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

        visible_names = union_all(canonical_names, non_asr_aliases).subquery()

        # Base filter: entity match + visible-name match
        base_filters = [
            EntityMentionDB.entity_id == entity_id,
            func.lower(EntityMentionDB.mention_text) == visible_names.c.name_lower,
        ]
        if language_code is not None:
            base_filters.append(EntityMentionDB.language_code == language_code)

        # Total count of distinct videos
        count_stmt = (
            select(func.count(distinct(EntityMentionDB.video_id)))
            .join(
                visible_names,
                func.lower(EntityMentionDB.mention_text)
                == visible_names.c.name_lower,
            )
            .where(
                EntityMentionDB.entity_id == entity_id,
                *(
                    [EntityMentionDB.language_code == language_code]
                    if language_code is not None
                    else []
                ),
            )
        )
        total_result = await session.execute(count_stmt)
        total_count = total_result.scalar() or 0

        if total_count == 0:
            return [], 0

        # Main query: group by video_id with mention count
        main_stmt = (
            select(
                EntityMentionDB.video_id,
                VideoDB.title.label("video_title"),
                func.coalesce(Channel.title, VideoDB.channel_name_hint, "Unknown").label(
                    "channel_name"
                ),
                func.count().label("mention_count"),
            )
            .join(
                visible_names,
                func.lower(EntityMentionDB.mention_text)
                == visible_names.c.name_lower,
            )
            .join(VideoDB, EntityMentionDB.video_id == VideoDB.video_id)
            .outerjoin(Channel, VideoDB.channel_id == Channel.channel_id)
            .where(
                EntityMentionDB.entity_id == entity_id,
                *(
                    [EntityMentionDB.language_code == language_code]
                    if language_code is not None
                    else []
                ),
            )
            .group_by(
                EntityMentionDB.video_id,
                VideoDB.title,
                Channel.title,
                VideoDB.channel_name_hint,
            )
            .order_by(func.count().desc())
            .offset(offset)
            .limit(limit)
        )

        main_result = await session.execute(main_stmt)
        video_rows = main_result.all()

        results: list[dict[str, Any]] = []
        for row in video_rows:
            # Fetch up to 5 mention previews for this video (visible names only)
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
                .join(
                    visible_names,
                    func.lower(EntityMentionDB.mention_text)
                    == visible_names.c.name_lower,
                )
                .where(
                    EntityMentionDB.entity_id == entity_id,
                    EntityMentionDB.video_id == row.video_id,
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

            results.append(
                {
                    "video_id": row.video_id,
                    "video_title": row.video_title,
                    "channel_name": row.channel_name,
                    "mention_count": row.mention_count,
                    "mentions": previews,
                }
            )

        return results, total_count

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
