"""
Novel-relationship candidate generator (Feature 107).

Computes pairs of existing library entities that co-occur strongly on the
title+description channel (lift >= 5 AND support >= 5) with no typed Wikidata tie,
and persists them as a read-only, lift-ranked queue. The heavy logic
(:func:`compute_candidates`) is a pure function over already-loaded rows, so the
measured contracts can be unit-tested and mutation-verified without a database.

Measured contracts carried here (see specs/107 research + notes 016/018):
- **No support floor** beyond ``support >= 5``: the minimum-support/high-lift cell
  is the highest-precision cell (variance, not bias). Never add a floor here.
- **Three-arm novelty filter**, all required: direct edge over the full ``RELATIONS``
  set (derived, never a hand list), shared co-membership (5 tie fields, hub-capped),
  and shared attribute referent ``{country, place_of_birth, headquarters}``
  (hub-capped). The attribute arm is load-bearing (removes ~24% false person-place
  novelty).
- **Channel = title+description only**; never union channels.
"""

from __future__ import annotations

import itertools
import uuid
from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any

from chronovista.config.database import db_manager
from chronovista.models.relationship_candidate import RelationshipCandidateCreate
from chronovista.repositories.relationship_candidate_repository import (
    RelationshipCandidateRepository,
)
from chronovista.services.wikidata_properties import RELATIONS

# Bump when the novelty filter or the lift metric changes, so a row's provenance
# records which generator produced it (a lift is uninterpretable without this).
GENERATOR_VERSION = "107.1"

CHANNEL = "title_description"
CHANNEL_SOURCES: tuple[str, ...] = ("title", "description")

# Novelty-filter field sets. The direct-edge arm uses the full RELATIONS set
# (single source — never enumerate). Co-membership uses the 5 measured tie fields;
# the attribute arm uses these three (includes headquarters, the org analogue of
# place_of_birth — matching the calibrated filter).
_RELATION_FIELDS: frozenset[str] = frozenset(RELATIONS.values())
TIE_FIELDS: tuple[str, ...] = (
    "educated_at",
    "employer",
    "member_of",
    "political_party",
    "position_held",
)
ATTR_FIELDS: tuple[str, ...] = ("country", "place_of_birth", "headquarters")
HUB_CAP = 20
SUPPORT_MIN = 5
LIFT_MIN = 5.0

# Corroboration is counted over captured shared-referent fields. These exclusions
# are the issue-10 LIVE-PROBE negatives (P5008 "on focus list", P1343 "described by
# source"); they are NOT in the captured RELATIONS set, so excluding them here is a
# forward-defensive no-op, not a live filter. The curated positive-signal list is
# deferred to the confirm/reject stage (FR-007).
CORROBORATION_EXCLUDE: frozenset[str] = frozenset({"P5008", "P1343"})
# Fields over which a shared referent counts as corroboration (all captured
# item-valued fields minus the deferred exclusions).
_CORROBORATION_FIELDS: frozenset[str] = (
    _RELATION_FIELDS | frozenset(ATTR_FIELDS)
) - CORROBORATION_EXCLUDE


def _qids(properties: dict[str, Any], field: str) -> list[str]:
    """QID targets stored for ``field`` on an entity's ``properties`` JSONB, or []."""
    slot = properties.get(field)
    if not isinstance(slot, dict):
        return []
    qids = slot.get("qids")
    return [q for q in qids if isinstance(q, str)] if isinstance(qids, list) else []


def _shared_referent_pairs(
    properties_by_entity: dict[uuid.UUID, dict[str, Any]], fields: tuple[str, ...]
) -> set[tuple[uuid.UUID, uuid.UUID]]:
    """Canonically-ordered pairs that share a hub-capped referent on any of ``fields``."""
    pairs: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for field in fields:
        by_ref: dict[str, set[uuid.UUID]] = defaultdict(set)
        for eid, props in properties_by_entity.items():
            for qid in _qids(props, field):
                by_ref[qid].add(eid)
        for members in by_ref.values():
            if 2 <= len(members) <= HUB_CAP:
                for a, b in itertools.combinations(sorted(members), 2):
                    pairs.add((a, b))
    return pairs


def compute_candidates(
    *,
    mention_rows: list[tuple[uuid.UUID, str]],
    entity_rows: list[tuple[uuid.UUID, dict[str, Any], dict[str, Any]]],
    run_id: uuid.UUID,
) -> tuple[list[RelationshipCandidateCreate], int]:
    """Pure core: compute novel-relationship candidates from loaded rows.

    Parameters
    ----------
    mention_rows
        ``(entity_id, video_id)`` for every title/description mention.
    entity_rows
        ``(entity_id, external_ids, properties)`` for every library entity.
    run_id
        The generation-run id, recorded in each candidate's provenance.

    Returns
    -------
    (candidates, channel_video_universe)
        The qualifying novel pairs (canonically ordered, ranked later by lift) and
        ``N`` = the number of videos with >=1 channel mention.
    """
    properties_by_entity: dict[uuid.UUID, dict[str, Any]] = {
        eid: (props or {}) for eid, _ext, props in entity_rows
    }
    qid_of: dict[uuid.UUID, str] = {}
    entity_of_qid: dict[str, uuid.UUID] = {}
    for eid, ext, _props in entity_rows:
        wd = ext.get("wikidata") if isinstance(ext, dict) else None
        qid = wd.get("id") if isinstance(wd, dict) else None
        if isinstance(qid, str) and qid:
            qid_of[eid] = qid
            entity_of_qid[qid] = eid

    # Co-occurrence over the channel.
    videos_to_entities: dict[str, set[uuid.UUID]] = defaultdict(set)
    for eid, video_id in mention_rows:
        videos_to_entities[video_id].add(eid)
    channel_video_universe = len(videos_to_entities)
    entity_video_count: Counter[uuid.UUID] = Counter()
    for entities in videos_to_entities.values():
        for eid in entities:
            entity_video_count[eid] += 1
    shared: Counter[tuple[uuid.UUID, uuid.UUID]] = Counter()
    for entities in videos_to_entities.values():
        if len(entities) < 2:
            continue
        for a, b in itertools.combinations(sorted(entities), 2):
            shared[(a, b)] += 1

    # Novelty-filter sets.
    direct_edges: set[tuple[uuid.UUID, uuid.UUID]] = set()
    for eid, props in properties_by_entity.items():
        for field in _RELATION_FIELDS:
            for qid in _qids(props, field):
                target = entity_of_qid.get(qid)
                if target is not None and target != eid:
                    direct_edges.add(tuple(sorted((eid, target))))  # type: ignore[arg-type]
    shared_tie = _shared_referent_pairs(properties_by_entity, TIE_FIELDS)
    shared_attr = _shared_referent_pairs(properties_by_entity, ATTR_FIELDS)

    # Typed-eligible = has >=1 tie/attribute property populated.
    eligible: set[uuid.UUID] = set()
    for eid, props in properties_by_entity.items():
        if any(_qids(props, f) for f in TIE_FIELDS + ATTR_FIELDS):
            eligible.add(eid)

    candidates: list[RelationshipCandidateCreate] = []
    for (a, b), support in shared.items():
        if support < SUPPORT_MIN:
            continue
        key = (a, b)
        if key in direct_edges or key in shared_tie or key in shared_attr:
            continue  # not novel
        count_a = entity_video_count[a]
        count_b = entity_video_count[b]
        expected = (
            (count_a * count_b) / channel_video_universe
            if channel_video_universe
            else 0.0
        )
        lift = support / expected if expected else 0.0
        if lift < LIFT_MIN:
            continue

        detail = _corroboration_detail(
            properties_by_entity.get(a, {}), properties_by_entity.get(b, {})
        )
        candidates.append(
            RelationshipCandidateCreate(
                entity_a_id=a,
                entity_b_id=b,
                channel=CHANNEL,
                shared_video_count=support,
                lift=lift,
                entity_a_video_count=count_a,
                entity_b_video_count=count_b,
                channel_video_universe=channel_video_universe,
                both_typed_eligible=(a in eligible and b in eligible),
                kb_corroboration_count=len(detail),
                kb_corroboration_detail={"fields": detail},
                provenance={
                    "channel": CHANNEL,
                    "N": channel_video_universe,
                    "corpus_size": len(entity_rows),
                    "generator_version": GENERATOR_VERSION,
                    "generated_run_id": str(run_id),
                },
            )
        )
    return candidates, channel_video_universe


def _corroboration_detail(
    props_a: dict[str, Any], props_b: dict[str, Any]
) -> list[str]:
    """Captured fields on which both entities share a referent QID (excl. deferred set)."""
    detail: list[str] = []
    for field in _CORROBORATION_FIELDS:
        if set(_qids(props_a, field)) & set(_qids(props_b, field)):
            detail.append(field)
    return sorted(detail)


async def generate_relationship_candidates(*, dry_run: bool = False) -> dict[str, int]:
    """Run a generation: compute, upsert, reconcile stale, record the run.

    Captures ``run_started_at`` BEFORE any upsert so delete-if-absent only removes
    pairs not re-emitted this run. ``dry_run`` rolls back (writes nothing) — the
    session autocommits on scope exit, so dry-run must not commit.
    """
    repo = RelationshipCandidateRepository()
    # Capture BEFORE any upsert so delete-if-absent only removes pairs not
    # re-emitted this run (a pair upserted this run is stamped later than this).
    run_started_at = datetime.now(UTC)
    summary: dict[str, int] = {"written": 0, "removed": 0, "channel_video_universe": 0}

    async with db_manager.session() as session:
        run = await repo.start_run(
            session, channel=CHANNEL, generator_version=GENERATOR_VERSION
        )
        if run is None:
            raise RuntimeError(
                "a relationship-candidate generation is already running for this channel"
            )
        mention_rows = await repo.fetch_cooccurrence_inputs(
            session, sources=CHANNEL_SOURCES
        )
        entity_rows = await repo.fetch_entity_property_rows(session)
        candidates, universe = compute_candidates(
            mention_rows=mention_rows, entity_rows=entity_rows, run_id=run.id
        )
        written = await repo.upsert_many(session, candidates=candidates)
        # Empty-run guard: delete-if-absent on an empty/degraded read (no mentions,
        # or zero qualifying candidates) would wipe every unverdicted row. Only
        # reconcile after a genuinely non-empty generation.
        removed = 0
        if mention_rows and candidates:
            removed = await repo.delete_stale(session, run_started_at=run_started_at)
        await repo.finish_run(
            session,
            run_id=run.id,
            status="completed",
            channel_video_universe=universe,
            corpus_size=len(entity_rows),
            candidates_written=written,
            candidates_removed=removed,
        )
        summary = {
            "written": written,
            "removed": removed,
            "channel_video_universe": universe,
            "corpus_size": len(entity_rows),
        }
        # dry_run rolls back EVERYTHING — the run row included — so a trial leaves no
        # trace and no lingering 'running' lock. (On a real exception the session's
        # rollback does the same, so a failed run never leaves a stuck lock.)
        if dry_run:
            await session.rollback()

    return summary
