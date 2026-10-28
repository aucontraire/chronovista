"""
Candidate suggestion service for seed-and-grow entity discovery (Feature 096).

Generates reviewable entity candidates from grounded entities' stored Wikidata
relationship targets: emit (offline, from stored properties) → ground against the
local corpus with the SHARED detector rule → score (Decision 2b) → triage → upsert.
Approving a candidate creates a grounded entity through the EXISTING creation +
enrichment path; rejecting records the verdict. No auto-creation (FR-013); a
single-token name only ever becomes an entity via an explicit human ``approve``.
"""

from __future__ import annotations

import math
import re
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from chronovista.models.candidate_suggestion import (
    CandidateSuggestionCreate,
    RelationCandidateRow,
)
from chronovista.models.entity_alias import EntityAliasCreate
from chronovista.models.entity_enrichment import ExternalIdentifier
from chronovista.models.enums import (
    DiscoveryMethod,
    EntityAliasType,
    EntityType,
    ReviewStatus,
    SourceChannel,
    TagStatus,
    TriageCategory,
)
from chronovista.models.named_entity import NamedEntityCreate
from chronovista.repositories.candidate_suggestion_repository import (
    CandidateSuggestionRepository,
)
from chronovista.repositories.entity_alias_repository import EntityAliasRepository
from chronovista.repositories.named_entity_repository import NamedEntityRepository
from chronovista.repositories.video_repository import VideoRepository
from chronovista.services.entity_enrichment_service import EntityEnrichmentService
from chronovista.services.entity_mention_scan_service import (
    _build_entity_pattern,
    _compile_entity_regex,
    _fold_diacritics,
)
from chronovista.services.tag_normalization import TagNormalizationService
from chronovista.services.wikidata_properties import RELATIONS

# Tokens for the inverted index (drops punctuation and underscores), matching the
# word-boundary the detector regex uses.
_WORD = re.compile(r"[^\W_]+", re.UNICODE)

# Stable namespace so a candidate QID maps to the same synthetic pattern entity_id.
_PATTERN_NS = uuid.UUID("00000000-0000-0000-0000-00000000ca11")

# Which EntityType a relation implies for its TARGET (authored; none exists in the
# codebase — see research.md). Only entity-valid types (no topic/descriptor, which
# named_entities.entity_type forbids). Relations not listed default to OTHER.
_RELATION_TARGET_TYPE: dict[str, EntityType] = {
    # person
    "father": EntityType.PERSON,
    "mother": EntityType.PERSON,
    "spouse": EntityType.PERSON,
    "child": EntityType.PERSON,
    "sibling": EntityType.PERSON,
    "unmarried_partner": EntityType.PERSON,
    "significant_person": EntityType.PERSON,
    "founder": EntityType.PERSON,
    "cast_member": EntityType.PERSON,
    "director": EntityType.PERSON,
    "producer": EntityType.PERSON,
    "screenwriter": EntityType.PERSON,
    "composer": EntityType.PERSON,
    "chairperson": EntityType.PERSON,
    "ceo": EntityType.PERSON,
    "creator": EntityType.PERSON,
    # organization
    "employer": EntityType.ORGANIZATION,
    "educated_at": EntityType.ORGANIZATION,
    "member_of": EntityType.ORGANIZATION,
    "political_party": EntityType.ORGANIZATION,
    "parent_organization": EntityType.ORGANIZATION,
    "child_organization": EntityType.ORGANIZATION,
    "owned_by": EntityType.ORGANIZATION,
    "affiliation": EntityType.ORGANIZATION,
    "production_company": EntityType.ORGANIZATION,
    "original_broadcaster": EntityType.ORGANIZATION,
    # place
    "place_of_birth": EntityType.PLACE,
    "place_of_death": EntityType.PLACE,
    # work / event / concept
    "notable_work": EntityType.WORK,
    "participant_in": EntityType.EVENT,
    "field_of_work": EntityType.CONCEPT,
    "subclass_of": EntityType.CONCEPT,
    # ambiguous → OTHER (position_held, part_of, award_received)
}


class GenerationSummary(BaseModel):
    """Outcome of a generation run (Feature 096)."""

    model_config = ConfigDict(frozen=True)

    seeds_grounded: int = Field(..., description="Grounded seed entities available")
    candidates_discovered: int = Field(
        ..., description="Distinct not-yet-library targets"
    )
    candidates_upserted: int = Field(
        ..., description="Candidates inserted or refreshed"
    )
    superseded: int = Field(
        ..., description="Pending candidates retired (now grounded)"
    )
    pending_total: int = Field(
        ..., description="Total pending candidates after the run"
    )
    by_triage: dict[str, int] = Field(
        ..., description="Pending counts per triage bucket"
    )
    empty_reason: str | None = Field(
        default=None,
        description="Set when the queue is empty for a stated reason (FR-018)",
    )


class VerdictResult(BaseModel):
    """Outcome of an approve/reject action (Feature 096)."""

    model_config = ConfigDict(frozen=True)

    outcome: str = Field(
        ..., description="approved | rejected | superseded | failed | not_found"
    )
    candidate_id: uuid.UUID = Field(..., description="The candidate acted on")
    created_entity_id: uuid.UUID | None = Field(
        default=None, description="Entity created or linked, when applicable"
    )
    detail: str | None = Field(default=None, description="Human-readable note")


def _derive_type_hint(relations: list[str]) -> EntityType:
    """Infer the target's coarse type from the relations that produced it.

    Drops OTHER-mapped relations; if exactly one distinct entity-valid type remains
    it wins, otherwise (none, or a conflict between relations) the hint is OTHER
    (spec Assumption: ambiguous or conflicting → the catch-all type).
    """
    distinct = {
        _RELATION_TARGET_TYPE[r] for r in relations if r in _RELATION_TARGET_TYPE
    }
    if len(distinct) == 1:
        return next(iter(distinct))
    return EntityType.OTHER


def _score(
    salience: int, specificity: float, token_count: int, corroboration: int
) -> float:
    """Decision-2b plausibility score (ranking only, never auto-rejects).

    Salience divided by name commonness (specificity is the inverse-document-frequency
    of the name's tokens — a rarer name is more specific), times a mild
    corroboration boost. A one-token common word that hits everywhere scores low;
    a specific, present, well-corroborated name scores high.
    """
    toks = max(1, token_count)
    return salience * (specificity / toks) * (1 + math.log10(max(1, corroboration)))


def _triage(salience: int, token_count: int, specificity: float) -> TriageCategory:
    """Advisory triage bucket (FR-005): grounds-nowhere / likely-eliminable / worth-review.

    ``likely_eliminable`` is the low-specificity/high-commonness profile; it is a
    ranking signal only — Phase-1 verdicts kept most of these, so it never eliminates.
    """
    if salience == 0:
        return TriageCategory.GROUNDS_NOWHERE
    if (token_count == 1 and salience >= 10) or (salience >= 30 and specificity < 8.0):
        return TriageCategory.LIKELY_ELIMINABLE
    return TriageCategory.WORTH_REVIEW


class _CorpusIndex:
    """Inverted token index over the folded corpus, for grounding pre-filtering."""

    def __init__(self, corpus: list[tuple[str, str, str | None]]) -> None:
        # Fold title+description once per video; keep aligned by position.
        self._folded: list[str] = [
            _fold_diacritics(f"{title} {description or ''}")[0]
            for _vid, title, description in corpus
        ]
        self._n = len(self._folded)
        self._token_vids: dict[str, set[int]] = defaultdict(set)
        for i, folded in enumerate(self._folded):
            for tok in {m.group(0).lower() for m in _WORD.finditer(folded)}:
                self._token_vids[tok].add(i)

    @property
    def size(self) -> int:
        return self._n

    def specificity(self, tokens: list[str]) -> float:
        """Sum of token inverse-document-frequency — the name's specificity.

        ``max(1, self._n)`` keeps the log defined on an empty corpus (specificity 0), so
        grounding degrades to salience 0 rather than raising ``math domain error``.
        """
        denom = max(1, self._n)
        return sum(
            math.log(denom / max(1, len(self._token_vids.get(t, ())))) for t in tokens
        )

    def salience(self, qid: str, name: str, type_hint: str) -> tuple[int, float]:
        """Return ``(distinct video hits, specificity)`` for a candidate name.

        Uses the SHARED detector rule (``_build_entity_pattern`` + ``_compile_entity_regex``
        + ``_fold_diacritics``), pre-filtered to videos containing all the name's tokens.
        """
        folded_name = _fold_diacritics(name)[0]
        tokens = [m.group(0).lower() for m in _WORD.finditer(folded_name)]
        specificity = round(self.specificity(tokens), 4)
        if self._n == 0 or not tokens or any(t not in self._token_vids for t in tokens):
            return 0, specificity
        pattern = _build_entity_pattern(
            entity_id=uuid.uuid5(_PATTERN_NS, qid),
            canonical_name=name,
            entity_type=type_hint,
            names=[name],
            case_sensitive_names=set(),
            exclusion_patterns=[],
        )
        if not pattern.pg_pattern:
            return 0, specificity
        regex = _compile_entity_regex(pattern)
        candidate_vids = set.intersection(*(self._token_vids[t] for t in tokens))
        hits = sum(1 for i in candidate_vids if regex.search(self._folded[i]))
        return hits, specificity


class CandidateSuggestionService:
    """Generate, review, and approve/reject candidate suggestions (Feature 096)."""

    def __init__(
        self,
        *,
        candidate_repo: CandidateSuggestionRepository,
        entity_repo: NamedEntityRepository,
        video_repo: VideoRepository,
        alias_repo: EntityAliasRepository,
        normalizer: TagNormalizationService | None = None,
        enrichment: EntityEnrichmentService | None = None,
    ) -> None:
        self._candidates = candidate_repo
        self._entities = entity_repo
        self._videos = video_repo
        self._aliases = alias_repo
        self._normalizer = normalizer or TagNormalizationService()
        # Optional: when None, approval skips enrichment (best-effort, FR-009) — the
        # test and no-network paths pass None; the CLI passes a real service.
        self._enrichment = enrichment
        self._channel = SourceChannel.RELATION

    async def generate(
        self,
        session: AsyncSession,
        *,
        dry_run: bool = False,
        progress: Callable[[int, int], Awaitable[None]] | None = None,
    ) -> GenerationSummary:
        """Discover, ground, score, triage, and upsert candidates (FR-001..FR-005, FR-014).

        ``dry_run`` computes and summarizes without writing (no upsert, no supersede);
        the triage tally is then projected from the freshly built candidates.

        ``progress`` (Feature 097) is an optional async callback invoked as
        ``progress(done, total)`` through the candidate-build loop — the dominant
        cost — so a UI-triggered run can report a determinate percentage (FR-023a).
        It is called at roughly 1% granularity; the CLI and tests pass ``None``.
        """
        grounded_qids = await self._entities.get_grounded_qids(session)
        if not grounded_qids:
            # No grounded seeds — nothing to grow from (FR-018).
            return GenerationSummary(
                seeds_grounded=0,
                candidates_discovered=0,
                candidates_upserted=0,
                superseded=0,
                pending_total=0,
                by_triage={t.value: 0 for t in TriageCategory},
                empty_reason=(
                    "No grounded seed entities yet — ground some entities first, "
                    "then re-run generation."
                ),
            )

        rows = await self._candidates.emit_relation_candidates(
            session, relation_fields=sorted(set(RELATIONS.values()))
        )
        corpus = await self._videos.get_all_title_description(session)
        index = _CorpusIndex(corpus)
        ungrounded = await self._entities.get_ungrounded_normalized_map(session)

        total = len(rows)
        step = max(1, total // 100)
        creates = []
        for i, row in enumerate(rows):
            create = self._build_create(row, index, ungrounded)
            if create is not None:
                creates.append(create)
            # Report progress through the build loop at ~1% granularity (FR-023a).
            if (
                progress is not None
                and total
                and ((i + 1) % step == 0 or i + 1 == total)
            ):
                await progress(i + 1, total)

        if dry_run:
            dry_triage: dict[str, int] = {t.value: 0 for t in TriageCategory}
            for create in creates:
                dry_triage[create.triage.value] += 1
            return GenerationSummary(
                seeds_grounded=len(grounded_qids),
                candidates_discovered=len(rows),
                candidates_upserted=len(creates),
                superseded=0,
                # Dry-run figures describe THIS run's candidates only (not the whole
                # existing queue, which the real run's counts reflect).
                pending_total=len(creates),
                by_triage=dry_triage,
                empty_reason="dry run — nothing written (figures are this run only)",
            )

        for create in creates:
            await self._candidates.upsert_generated(session, candidate=create)

        superseded = await self._candidates.supersede_grounded(
            session, source_channel=self._channel.value, grounded_qids=grounded_qids
        )
        counts = await self._candidates.counts_by_status(
            session, source_channel=self._channel.value
        )
        return GenerationSummary(
            seeds_grounded=len(grounded_qids),
            candidates_discovered=len(rows),
            candidates_upserted=len(creates),
            superseded=superseded,
            pending_total=counts.get(ReviewStatus.PENDING.value, 0),
            by_triage={t.value: counts.get(t.value, 0) for t in TriageCategory},
        )

    def _build_create(
        self,
        row: RelationCandidateRow,
        index: _CorpusIndex,
        ungrounded: dict[str, uuid.UUID],
    ) -> CandidateSuggestionCreate | None:
        """Turn an emitted row into a persistable candidate, or ``None`` to skip it."""
        normalized = self._normalizer.normalize(row.label)
        if not normalized:
            return None  # cannot satisfy token_count >= 1 / NOT NULL
        token_count = len(normalized.split())
        if token_count < 1:
            return None
        type_hint = _derive_type_hint(row.relations)
        salience, specificity = index.salience(
            row.wikidata_qid, row.label, type_hint.value
        )
        return CandidateSuggestionCreate(
            source_channel=self._channel,
            wikidata_qid=row.wikidata_qid,
            label=row.label,
            label_normalized=normalized,
            type_hint=type_hint,
            token_count=token_count,
            corroboration_count=row.corroboration_count,
            dangling_edge_count=row.dangling_edge_count,
            salience=salience,
            score=round(
                _score(salience, specificity, token_count, row.corroboration_count), 4
            ),
            triage=_triage(salience, token_count, specificity),
            provenance={
                "seed_entity_ids": [str(s) for s in row.seed_entity_ids],
                "relations": row.relations,
            },
            possible_duplicate_of_id=ungrounded.get(normalized),
        )

    async def approve(
        self, session: AsyncSession, *, candidate_id: uuid.UUID, reviewed_by: str
    ) -> VerdictResult:
        """Create a grounded entity from a candidate via the existing path (FR-009).

        Reuses ``NamedEntityRepository.create`` + canonical alias + (best-effort)
        ``enrich_on_approval``. Guards against duplicates (QID already grounded or a
        name+type collision → superseded, no new entity). On creation failure the
        candidate stays reviewable (FR-015).
        """
        candidate = await self._candidates.get(session, candidate_id)
        if candidate is None:
            return VerdictResult(
                outcome="not_found",
                candidate_id=candidate_id,
                detail="No such candidate",
            )
        if candidate.review_status != ReviewStatus.PENDING.value:
            return VerdictResult(
                outcome="failed",
                candidate_id=candidate_id,
                detail=f"Candidate is already {candidate.review_status}",
            )

        qid = candidate.wikidata_qid
        now = datetime.now(UTC)

        # Already grounded by other means → supersede, no duplicate (FR-011b).
        grounded = await self._entities.get_by_wikidata_qids(session, [qid])
        if qid in grounded:
            existing_id, _name = grounded[qid]
            await self._candidates.set_verdict(
                session,
                candidate_id=candidate_id,
                review_status=ReviewStatus.SUPERSEDED,
                reviewed_by=reviewed_by,
                reviewed_at=now,
                created_entity_id=existing_id,
            )
            return VerdictResult(
                outcome="superseded",
                candidate_id=candidate_id,
                created_entity_id=existing_id,
                detail="Identity already grounded to an existing entity",
            )

        normalized = (
            self._normalizer.normalize(candidate.label) or candidate.label_normalized
        )
        type_value = candidate.type_hint
        # Name+type collision with ANY existing entity (uq_named_entity_canonical is
        # global across statuses) → supersede, never attempt a create that would raise
        # IntegrityError and dead-end the candidate (adversarial M1).
        existing = await self._entities.find_by_normalized_and_type(
            session, normalized, type_value
        )
        if existing is not None:
            await self._candidates.set_verdict(
                session,
                candidate_id=candidate_id,
                review_status=ReviewStatus.SUPERSEDED,
                reviewed_by=reviewed_by,
                reviewed_at=now,
                created_entity_id=existing.id,
            )
            return VerdictResult(
                outcome="superseded",
                candidate_id=candidate_id,
                created_entity_id=existing.id,
                detail="An entity with this name and type already exists",
            )

        try:
            external_ids = {
                "wikidata": ExternalIdentifier(
                    id=qid, verified=True, status="verified"
                ).model_dump()
            }
            db_entity = await self._entities.create(
                session,
                obj_in=NamedEntityCreate(
                    canonical_name=candidate.label,
                    canonical_name_normalized=normalized,
                    entity_type=EntityType(type_value),
                    status=TagStatus.ACTIVE,
                    discovery_method=DiscoveryMethod.USER_CREATED,
                    confidence=1.0,
                    external_ids=external_ids,
                ),
            )
            await self._aliases.create(
                session,
                obj_in=EntityAliasCreate(
                    entity_id=db_entity.id,
                    alias_name=candidate.label,
                    alias_name_normalized=normalized,
                    alias_type=EntityAliasType.NAME_VARIANT,
                    occurrence_count=0,
                ),
            )
            await session.commit()
        except Exception as exc:  # noqa: BLE001 - surfaced to the operator (FR-015)
            await session.rollback()
            return VerdictResult(
                outcome="failed",
                candidate_id=candidate_id,
                detail=f"Entity creation failed; candidate left pending: {exc}",
            )

        # Enrichment is best-effort and never rolls back the creation (FR-009). Guard
        # locally so the "best-effort" contract does not depend on the collaborator
        # never raising — a failure here leaves the created entity intact.
        if self._enrichment is not None:
            try:
                await self._enrichment.enrich_on_approval(db_entity.id, qid)
            except Exception:  # noqa: BLE001 - enrichment is best-effort; retried later
                pass

        verdict = await self._candidates.set_verdict(
            session,
            candidate_id=candidate_id,
            review_status=ReviewStatus.APPROVED,
            reviewed_by=reviewed_by,
            reviewed_at=datetime.now(UTC),
            created_entity_id=db_entity.id,
        )
        await session.commit()
        if verdict is None:
            # A concurrent verdict won the compare-and-set after the entity was
            # created+committed. The entity is grounded; report it honestly rather
            # than claiming a clean approval.
            return VerdictResult(
                outcome="approved",
                candidate_id=candidate_id,
                created_entity_id=db_entity.id,
                detail="Entity created, but the candidate was concurrently decided",
            )
        return VerdictResult(
            outcome="approved",
            candidate_id=candidate_id,
            created_entity_id=db_entity.id,
            detail="Grounded entity created",
        )

    async def reject(
        self, session: AsyncSession, *, candidate_id: uuid.UUID, reviewed_by: str
    ) -> VerdictResult:
        """Record a rejection; the QID is not re-offered on later runs (FR-010).

        Distinguishes a missing candidate (``not_found`` → HTTP 404) from an
        already-decided one (``failed``), mirroring ``approve`` — the existence
        check precedes the compare-and-set, which still guards the race where the
        candidate is decided between the read and the write.
        """
        candidate = await self._candidates.get(session, candidate_id)
        if candidate is None:
            return VerdictResult(
                outcome="not_found",
                candidate_id=candidate_id,
                detail="No such candidate",
            )
        updated = await self._candidates.set_verdict(
            session,
            candidate_id=candidate_id,
            review_status=ReviewStatus.REJECTED,
            reviewed_by=reviewed_by,
            reviewed_at=datetime.now(UTC),
        )
        if updated is None:
            return VerdictResult(
                outcome="failed",
                candidate_id=candidate_id,
                detail="Candidate is already decided",
            )
        return VerdictResult(outcome="rejected", candidate_id=candidate_id)
