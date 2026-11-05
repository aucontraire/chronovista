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

from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.models.candidate_suggestion import (
    CandidateSuggestionCreate,
    RelationCandidateRow,
)
from chronovista.models.enums import (
    DiscoveryMethod,
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
from chronovista.services.entity_creation import (
    build_grounding,
    create_and_ground_entity,
)
from chronovista.services.entity_enrichment_service import EntityEnrichmentService
from chronovista.services.entity_mention_scan_service import (
    _build_entity_pattern,
    _compile_entity_regex,
    _fold_diacritics,
)
from chronovista.services.tag_normalization import TagNormalizationService
from chronovista.services.wikidata_client import WikidataClient, WikidataUnavailable
from chronovista.services.wikidata_taxonomy import suggest_entity_type

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


# Relations whose TARGETS are categorically untypeable: awards and offices have no EntityType slot,
# and under the OntoNotes contract never will (there is no AWARD/TITLE type). They are still mined
# as relation FACTS (RELATIONS, via backfill_entity_relations) but must NOT seed candidates —
# seeding them minted ~3,000 unfilable `other` candidates (0.03% approval). `part_of` is deliberately
# NOT here: its targets are heterogeneous and P31-first now types its event targets (v0.110.0).
# This is a pinned denylist, not the general mechanism (Rule of Three not yet met). Computable form
# if a third such relation recurs: an integration check that no seeded relation exceeds ~50% `other`
# — the empty middle of the observed bimodal split (every mapped relation <=1.5%, these two ~99%).
# Candidate SEEDING is governed by an EXPLICIT allowlist (Feature 105, ADR 014): a relation seeds
# review candidates only if it is named here. Capture-only is the safe default — adding a field to
# ``RELATIONS`` (capture / fact-mining) does NOT seed it unless it is also listed below. This
# replaced the prior opt-out ``RELATIONS − denylist`` derivation, which would have seeded every
# newly-captured relation by default. Two permanent, mutation-verified fitness guards
# (``tests/unit/architecture/test_seed_allowlist_fitness.py``) protect it: baseline-containment
# (the originally-effective relations never silently drop out and strand their candidates) and
# subset (every entry is a real ``RELATIONS`` value; no competing denylist governs seeding).
# REVERSAL (demote a seeded relation): remove it here (stops future minting) + policy-reject its
# existing rows with a ``reviewed_by`` marker distinct from a human verdict (v0.112.0 precedent,
# ADR 014 D2) — the upsert never deletes, so existing rows persist until that sweep.
SEED_ALLOWLIST: frozenset[str] = frozenset(
    {
        # 33 baseline relations — exactly those that seeded before the opt-out→allowlist flip
        # (every ``RELATIONS`` value except the categorically-untypeable ``award_received`` /
        # ``position_held``, whose targets have no ``EntityType`` slot — v0.112.0).
        "employer",
        "educated_at",
        "member_of",
        "place_of_birth",
        "place_of_death",
        "father",
        "mother",
        "spouse",
        "child",
        "sibling",
        "political_party",
        "part_of",
        "subclass_of",
        "founder",
        "cast_member",
        "director",
        "producer",
        "screenwriter",
        "composer",
        "significant_person",
        "unmarried_partner",
        "field_of_work",
        "notable_work",
        "participant_in",
        "parent_organization",
        "child_organization",
        "owned_by",
        "chairperson",
        "ceo",
        "affiliation",
        "creator",
        "production_company",
        "original_broadcaster",
        # Feature 105 "seed-now" set (US2): the reviewed cheap, high-signal edges (each measured
        # NET-NEW <= ~25). Captured in RELATIONS (US1); promoted to seeding here. The expensive /
        # held edges and place-institution edges stay captured-but-not-seeded (re-priced before any
        # future promotion, ADR 014 D6).
        "perpetrator",
        "named_by",
        "used_by",
        "film_editor",
        "practiced_by",
        "director_of_photography",
        "discoverer_or_inventor",
        "opposite_of",
        "investigated_by",
        "has_effect",
        "contributing_factor_of",
        "has_cause",
        "funder",
        "based_on",
        "operator",
        "distributed_by",
        "location_of_formation",
        "editor",
        "editor_in_chief",
        "in_opposition_to",
        "executive_producer",
        "narrative_location",
        "has_goal",
        "partnership_with",
        "main_subject",
        "participant",
    }
)


def _seed_relation_fields() -> list[str]:
    """Relations that seed candidates — the explicit ``SEED_ALLOWLIST`` (Feature 105).

    Capture (``RELATIONS``) and seeding are decoupled: a relation is always mined/captured, but
    seeds review candidates only if it is named in ``SEED_ALLOWLIST``.
    """
    return sorted(SEED_ALLOWLIST)


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

    def salience(
        self, qid: str, name: str, type_hint: str, aliases: list[str]
    ) -> tuple[int, float]:
        """Return ``(distinct video hits, specificity)`` for a candidate's full name set.

        Matches the candidate's canonical label **plus its Wikidata aliases** against the
        corpus with the SHARED detector rule (``_build_entity_pattern`` +
        ``_compile_entity_regex`` + ``_fold_diacritics``) — the same canonical+alias name set
        the scanner matches for a library entity. Scoring the label alone undercounts salience
        for entities whose corpus mentions use a short form or acronym (the measured
        institution 3.8%-vs-17.5% spread): the label-only name grounds nowhere while the alias
        matches plainly.

        ``specificity`` stays the *canonical name's* specificity (aliases do not change how
        specific the primary name is). The token pre-filter, however, is per-ALTERNATIVE: a
        video matching one alternative of ``name|alias1|...`` must contain every token of THAT
        alternative, so the candidate set is the UNION over alternatives of each alternative's
        token intersection. Pre-filtering on the primary name's tokens alone (the old shape)
        would starve any alias whose tokens the label lacks — exactly the acronym case this
        fixes — so the ``names=[name]`` fix is incomplete without this.
        """
        folded_primary = _fold_diacritics(name)[0]
        primary_tokens = [m.group(0).lower() for m in _WORD.finditer(folded_primary)]
        specificity = round(self.specificity(primary_tokens), 4)
        if self._n == 0:
            return 0, specificity

        candidate_vids: set[int] = set()
        for alt in (name, *aliases):
            folded_alt = _fold_diacritics(alt)[0]
            alt_tokens = [m.group(0).lower() for m in _WORD.finditer(folded_alt)]
            if not alt_tokens or any(t not in self._token_vids for t in alt_tokens):
                continue  # an alternative with a corpus-absent token can never match
            candidate_vids |= set.intersection(
                *(self._token_vids[t] for t in alt_tokens)
            )
        if not candidate_vids:
            return 0, specificity

        pattern = _build_entity_pattern(
            entity_id=uuid.uuid5(_PATTERN_NS, qid),
            canonical_name=name,
            entity_type=type_hint,
            names=[name, *aliases],
            case_sensitive_names=set(),
            exclusion_patterns=[],
        )
        if not pattern.pg_pattern:
            return 0, specificity
        regex = _compile_entity_regex(pattern)
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
        wikidata_client: WikidataClient | None = None,
    ) -> None:
        self._candidates = candidate_repo
        self._entities = entity_repo
        self._videos = video_repo
        self._aliases = alias_repo
        self._normalizer = normalizer or TagNormalizationService()
        # Optional: when None, approval skips enrichment (best-effort, FR-009) — the
        # test and no-network paths pass None; the CLI passes a real service.
        self._enrichment = enrichment
        # Optional Wikidata client for authoritative P31-based typing (Feature 098).
        # When None (no-network/test paths), generation and approval fall back to the
        # relation-name heuristic / the candidate's stored type (FR-011).
        self._wikidata = wikidata_client
        self._channel = SourceChannel.RELATION

    async def generate(
        self,
        session: AsyncSession,
        *,
        dry_run: bool = False,
        progress: Callable[[int, int], Awaitable[None]] | None = None,
        instance_of_map: dict[str, list[str]] | None = None,
        aliases_map: dict[str, list[str]] | None = None,
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
            session, relation_fields=_seed_relation_fields()
        )
        corpus = await self._videos.get_all_title_description(session)
        index = _CorpusIndex(corpus)
        ungrounded = await self._entities.get_ungrounded_normalized_map(session)
        # Authoritative P31 types for every discovered QID (Feature 098). The detached runner
        # pre-fetches these OUTSIDE this session (via discover_target_qids → fetch) and passes
        # them in, so a DB transaction is never held idle across the minutes-long Wikidata batch
        # (the Feature 094 held-session class). The CLI/tests omit the map and fetch inline — a
        # short, single-user or faked call. {} → each candidate falls back to the relation
        # heuristic (FR-004/FR-011).
        p31_by_qid = (
            instance_of_map
            if instance_of_map is not None
            else await self._fetch_instance_of_for_rows(rows)
        )
        # Wikidata aliases for every discovered QID, so salience matches a candidate's full name
        # set (label + aliases), not the label alone (the institution 3.8%-vs-17.5% spread). Like
        # instance_of_map, the detached runner pre-fetches these OUTSIDE the session; the CLI/tests
        # fetch inline. ``None`` (fetch unavailable) is kept distinct from ``{}`` (fetched, nobody
        # had aliases) so each candidate records which salience branch ran.
        aliases_by_qid = (
            aliases_map
            if aliases_map is not None
            else await self._fetch_aliases_for_rows(rows)
        )

        total = len(rows)
        step = max(1, total // 100)
        creates = []
        for i, row in enumerate(rows):
            create = self._build_create(
                row, index, ungrounded, p31_by_qid, aliases_by_qid
            )
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

    async def _fetch_instance_of_for_rows(
        self, rows: list[RelationCandidateRow]
    ) -> dict[str, list[str]]:
        """Batch-fetch P31 (``instance_of``) for the discovered QIDs (Feature 098, FR-001/004).

        Returns ``{qid: [p31...]}``; ``{}`` when no Wikidata client is wired or the knowledge
        base is unreachable, so generation degrades to the relation heuristic (FR-011).
        """
        if self._wikidata is None:
            return {}
        qids = sorted({row.wikidata_qid for row in rows})
        if not qids:
            return {}
        try:
            return await self._wikidata.fetch_instance_of(qids)
        except WikidataUnavailable:
            return {}

    async def _fetch_aliases_for_rows(
        self, rows: list[RelationCandidateRow]
    ) -> dict[str, list[str]] | None:
        """Batch-fetch Wikidata aliases for the discovered QIDs (salience grounding).

        Twin of :meth:`_fetch_instance_of_for_rows`, with one deliberate difference: it returns
        ``None`` (not ``{}``) when the fetch was skipped or failed — no Wikidata client wired, or
        ``WikidataUnavailable`` — so each candidate's provenance can distinguish "salience was
        label-only because the alias fetch was unavailable" from "the entity genuinely has no
        aliases" (the record-which-fallback-ran rule). A successful fetch returns a dict whose
        absent keys mean that known QID has no aliases.
        """
        if self._wikidata is None:
            return None
        qids = sorted({row.wikidata_qid for row in rows})
        if not qids:
            return {}
        try:
            return await self._wikidata.fetch_aliases(qids)
        except WikidataUnavailable:
            return None

    async def discover_target_qids(self, session: AsyncSession) -> list[str]:
        """Distinct target QIDs for the current relation candidates (Feature 098).

        Lets the detached runner read QIDs in a SHORT session it closes BEFORE the Wikidata
        batch, so no DB transaction is held across the network call (the Feature 094 held-session
        class). ``generate`` then receives the pre-fetched ``instance_of_map``.
        """
        rows = await self._candidates.emit_relation_candidates(
            session, relation_fields=_seed_relation_fields()
        )
        return sorted({row.wikidata_qid for row in rows})

    def _build_create(
        self,
        row: RelationCandidateRow,
        index: _CorpusIndex,
        ungrounded: dict[str, uuid.UUID],
        p31_by_qid: dict[str, list[str]],
        aliases_by_qid: dict[str, list[str]] | None,
    ) -> CandidateSuggestionCreate | None:
        """Turn an emitted row into a persistable candidate, or ``None`` to skip it."""
        normalized = self._normalizer.normalize(row.label)
        if not normalized:
            return None  # cannot satisfy token_count >= 1 / NOT NULL
        token_count = len(normalized.split())
        if token_count < 1:
            return None
        # Authoritative type from the candidate's own Wikidata P31 when available; fall back to the
        # relation-name heuristic when there is no usable P31 (QID unknown/unreachable or no
        # instance_of) OR the P31 classifies only to the catch-all OTHER — a catch-all is evidence
        # the classifier could not place it, not positive evidence of type OTHER (Feature 098,
        # FR-001/004/011; the Direction-A rule shared with reverify_type and backfill_candidate_types
        # via suggest_entity_type, which returns None for the OTHER case). ``type_source`` records
        # which path set the type, so a heuristic guess is never silently indistinguishable from an
        # authoritative classification (nor from a P31 fetch that quietly failed).
        p31 = p31_by_qid.get(row.wikidata_qid)
        suggested = suggest_entity_type(p31) if p31 else None
        if suggested is not None:
            type_hint = EntityType(suggested)
            type_source = "p31"
        else:
            type_hint = _derive_type_hint(row.relations)
            type_source = "relation_heuristic"
        # Full name set for salience: label + Wikidata aliases. ``aliases_by_qid is None`` means
        # the alias fetch was unavailable, so salience fell back to label-only — recorded as
        # ``unavailable`` to keep it distinct from an entity that genuinely has no aliases
        # (``none``), per the record-which-fallback-ran rule.
        if aliases_by_qid is None:
            aliases: list[str] = []
            salience_aliases = "unavailable"
        else:
            aliases = aliases_by_qid.get(row.wikidata_qid, [])
            salience_aliases = "used" if aliases else "none"
        salience, specificity = index.salience(
            row.wikidata_qid, row.label, type_hint.value, aliases
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
                "type_source": type_source,
                "salience_aliases": salience_aliases,
            },
            possible_duplicate_of_id=ungrounded.get(normalized),
        )

    async def reverify_type(self, qid: str, stored_type: str) -> str:
        """Re-verify an entity's type from its own Wikidata P31 at approval (Feature 098, FR-006).

        Overrides the stored type ONLY with positive, determinate P31 evidence; with no usable P31
        (QID unknown/absent, no instance_of, or a P31 that classifies only to the catch-all OTHER)
        it keeps the stored type — consistent with generation's heuristic-on-no-P31 (FR-004) and
        with ``backfill_candidate_types``' Direction-A rule, so a reviewer never approves one type
        and gets another. Best-effort: any Wikidata failure keeps the stored type, so approval never
        fails for this reason (FR-011).

        Held-session trade-off: called inside ``approve`` for a PENDING candidate only, so the
        request's DB connection is held across one Wikidata lookup. Accepted as bounded for this
        single-user local app (interactive, one approval at a time; NOT the Feature-094
        background-task-across-cancellable-await deadlock). If this ever becomes multi-user or
        batched, move the re-verify off the request session. An external pre-fetch was tried and
        reverted — using a second ``db_manager`` session mid-request breaks under the test harness's
        event loop (asyncpg "Future attached to a different loop").
        """
        if self._wikidata is None:
            return stored_type
        try:
            p31_by_qid = await self._wikidata.fetch_instance_of([qid])
        except (
            Exception
        ):  # noqa: BLE001 - best-effort; any failure keeps the stored type (FR-011)
            return stored_type
        p31 = p31_by_qid.get(qid)
        if not p31:
            return stored_type
        # A P31 that classifies only to the catch-all OTHER is NOT positive evidence of type OTHER;
        # keep the more specific stored type (Direction A / FR-006). suggest_entity_type returns
        # None for the OTHER case, which is exactly the "keep stored" signal.
        return suggest_entity_type(p31) or stored_type

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
        # Re-verify the type against Wikidata at the write moment (Feature 098, FR-006): a
        # candidate's stored type_hint may be a transient heuristic fallback (Wikidata was down
        # at generation) or stale. The re-verified value drives BOTH the collision check below
        # and the created entity's type, so they cannot disagree. Only reached for a PENDING
        # candidate (the not-pending paths return above), so no wasted lookup on a decided one.
        type_value = await self.reverify_type(qid, candidate.type_hint)
        # Route creation through the shared core (Feature 101, FR-002/005). The core owns the
        # all-status duplicate lookup; approve's policy on a collision is SUPERSEDE — record the
        # colliding entity (uq_named_entity_canonical is global across statuses) and finalize a
        # SUPERSEDED verdict below, never attempting a create that would IntegrityError and
        # dead-end the candidate (adversarial M1). Grounding uses the one sanctioned builder
        # (FR-003).
        entity_create = NamedEntityCreate(
            canonical_name=candidate.label,
            canonical_name_normalized=normalized,
            entity_type=EntityType(type_value),
            status=TagStatus.ACTIVE,
            discovery_method=DiscoveryMethod.USER_CREATED,
            confidence=1.0,
            external_ids=build_grounding(
                "wikidata", qid, verified=True, status="verified"
            ),
        )
        collision: NamedEntityDB | None = None

        async def _supersede(found: NamedEntityDB) -> NamedEntityDB | None:
            nonlocal collision
            collision = found
            return found

        try:
            created = await create_and_ground_entity(
                session,
                entity_create,
                on_conflict=_supersede,
                entity_repo=self._entities,
                alias_repo=self._aliases,
            )
            if collision is None:
                await session.commit()
        except Exception as exc:  # noqa: BLE001 - surfaced to the operator (FR-015)
            await session.rollback()
            return VerdictResult(
                outcome="failed",
                candidate_id=candidate_id,
                detail=f"Entity creation failed; candidate left pending: {exc}",
            )

        if collision is not None:
            await self._candidates.set_verdict(
                session,
                candidate_id=candidate_id,
                review_status=ReviewStatus.SUPERSEDED,
                reviewed_by=reviewed_by,
                reviewed_at=now,
                created_entity_id=collision.id,
            )
            return VerdictResult(
                outcome="superseded",
                candidate_id=candidate_id,
                created_entity_id=collision.id,
                detail="An entity with this name and type already exists",
            )

        assert created is not None  # create path: the core returns the new entity
        db_entity = created

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
