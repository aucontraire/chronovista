"""Before/after audit of what transcript mentions count.

A change to mention data (a repair, a full rescan, a batch correction) can pass every
check of its own and still leave an entity uncounted where it was counted before:
the #426 repair kept a disfluency-gap match, which does not count, over the clean
name inside it. This compares what users see instead of what the tool measures. A
snapshot records every ``(entity, segment)`` a counted mention covers and every
``(entity, video)`` a transcript mention links; comparing a later snapshot lists
what was lost.

Places are compared per segment, so a lost place is something to look at, not proof of a
loss. Two cases appear although nothing that should count was lost: a split name whose
occurrence was also recorded from its next segment, where that record was kept; and a
mention whose words a correction removed (stale, which a repair may remove).

Snapshots hold library ids, so keep them out of the repository (``backups/`` is
gitignored).
"""

from __future__ import annotations

import uuid
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.repositories.entity_mention_repository import (
    EntityMentionRepository,
)


class MentionAuditSnapshot(BaseModel):
    """What transcript mentions count at one moment."""

    counted_segments: set[tuple[uuid.UUID, int]]
    associations: set[tuple[uuid.UUID, str]]

    def save(self, path: Path) -> None:
        path.write_text(self.model_dump_json())

    @classmethod
    def load(cls, path: Path) -> MentionAuditSnapshot:
        return cls.model_validate_json(path.read_text())


class MentionAuditComparison(BaseModel):
    """What a later snapshot lost and gained against an earlier one."""

    counted_segments_lost: set[tuple[uuid.UUID, int]]
    counted_segments_gained: int
    associations_lost: set[tuple[uuid.UUID, str]]
    associations_gained: int

    @property
    def entities_losing_counts(self) -> set[uuid.UUID]:
        return {entity_id for entity_id, _ in self.counted_segments_lost}

    @property
    def holds(self) -> bool:
        """True when nothing that counted stopped counting."""
        return not self.counted_segments_lost and not self.associations_lost


async def take_snapshot(session: AsyncSession) -> MentionAuditSnapshot:
    """Read what transcript mentions count now; writes nothing."""
    mentions = EntityMentionRepository()
    return MentionAuditSnapshot(
        counted_segments=await mentions.counted_mention_segments(session),
        associations=await mentions.transcript_associations(session),
    )


def compare(
    before: MentionAuditSnapshot, after: MentionAuditSnapshot
) -> MentionAuditComparison:
    """What ``after`` lost and gained relative to ``before``."""
    return MentionAuditComparison(
        counted_segments_lost=before.counted_segments - after.counted_segments,
        counted_segments_gained=len(after.counted_segments - before.counted_segments),
        associations_lost=before.associations - after.associations,
        associations_gained=len(after.associations - before.associations),
    )
