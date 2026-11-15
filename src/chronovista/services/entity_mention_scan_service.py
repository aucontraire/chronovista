"""
Entity mention scan service for detecting named entity occurrences in transcripts.

Scans transcript segments for mentions of named entities using PostgreSQL regex
matching with word-boundary support. Supports incremental and full-rescan modes,
batch processing, dry-run previews, and progress reporting.

Feature 038 -- Entity Mention Detection
"""

from __future__ import annotations

import logging
import re
import time
import unicodedata
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cached_property
from types import SimpleNamespace
from typing import Any

from sqlalchemy import Select, func, literal_column, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from chronovista.db.models import EntityAlias as EntityAliasDB
from chronovista.db.models import EntityMention as EntityMentionDB
from chronovista.db.models import NamedEntity as NamedEntityDB
from chronovista.db.models import TranscriptSegment as TranscriptSegmentDB
from chronovista.db.models import Video as VideoDB
from chronovista.db.models import VideoTranscript as VideoTranscriptDB
from chronovista.models.entity_mention import EntityMentionCreate
from chronovista.models.enums import (
    SCAN_DETECTION_METHODS,
    DetectionMethod,
    MentionSource,
)
from chronovista.repositories.entity_asr_error_repository import (
    EntityAsrErrorRepository,
)
from chronovista.repositories.entity_mention_repository import (
    EntityMentionRepository,
)
from chronovista.services.cross_segment_discovery import (
    _STOPWORDS,
)
from chronovista.services.transcript_text_index import (
    SEGMENT_SEPARATOR,
    SegmentInput,
    TranscriptTextIndex,
)

logger = logging.getLogger(__name__)

# Minimum alias length before a warning is emitted.
_MIN_ALIAS_LENGTH = 3

# Consecutive failed fetches at the same cursor before a scan gives up. Keyset
# pagination cannot skip a batch it never received, so the choice is retry or
# stop; this bounds the retry.
_MAX_FETCH_RETRIES = 3

# Zero-width / invisible formatting code points stripped by the match fold: they
# are not whitespace (so ``str.isspace()`` misses them) but would break a
# contiguous match. Zero-width space, ZWNJ, ZWJ, BOM/ZWNBSP, and soft hyphen.
_MATCH_INVISIBLE_CPS = frozenset({0x200B, 0x200C, 0x200D, 0xFEFF, 0x00AD})

# Spanish high-frequency words for the ASR-form admission gate (FR-003). The gate
# excludes a multi-word ASR form only when EVERY token is a common word — i.e. the
# form carries no distinctive token to anchor it to a name. ``_STOPWORDS`` (imported
# above) is English-only, which left the gate INERT on this bilingual corpus: it
# rejected zero registered forms. These are the Spanish closed-class function words
# (determiners, prepositions, pronouns, conjunctions, copulas) plus ``fe`` ("faith")
# — the single open-class word needed, because an ASR mis-split of a nickname can
# produce an all-common two-word form ("faith of") that is ordinary Spanish prose
# and would otherwise be admitted and tag every occurrence as a person. This is a
# curated closed-class list, deliberately NOT a dictionary: the dictionary-wide noun
# extension was rejected because it excludes genuine recoveries (a first name beside
# an ordinary-word surname, e.g. a mis-hearing that happens to spell common words).
# Measured collateral of this exact set over the live corpus: exactly one form
# excluded, zero genuine recoveries lost. A per-form reviewer override (FR-011)
# remains the lever for forms the gate cannot catch (a distinctive first name beside
# an English preposition — all-common never fires, so only an override excludes it).
_ES_COMMON_WORDS: frozenset[str] = frozenset(
    {
        "de",
        "del",
        "la",
        "el",
        "los",
        "las",
        "un",
        "una",
        "unos",
        "unas",
        "lo",
        "al",
        "a",
        "en",
        "y",
        "o",
        "u",
        "que",
        "con",
        "por",
        "para",
        "su",
        "sus",
        "mi",
        "mis",
        "tu",
        "tus",
        "se",
        "le",
        "les",
        "me",
        "te",
        "nos",
        "es",
        "son",
        "era",
        "eran",
        "ser",
        "estar",
        "esta",
        "este",
        "esto",
        "esa",
        "ese",
        "eso",
        "como",
        "pero",
        "porque",
        "si",
        "no",
        "ya",
        "muy",
        "mas",
        "sin",
        "sobre",
        "entre",
        "cuando",
        "donde",
        "quien",
        "desde",
        "hasta",
        "hay",
        "todo",
        "toda",
        "todos",
        "todas",
        "otro",
        "otra",
        "cada",
        "ni",
        "e",
        "fe",
    }
)

# The gate's common-word set: English stopwords ∪ the Spanish high-frequency set.
# Single-sourced here; the admission gate (_asr_form_admissible) is its only reader.
_COMMON_WORDS: frozenset[str] = _STOPWORDS | _ES_COMMON_WORDS


# Word-run tokenizer for the cross-segment candidate pre-filter. Matches how the
# ``\b``-anchored entity regex delimits a token (a maximal run of word chars),
# so a transcript word carrying adjacent punctuation ("bravo,") still yields
# the bare token ("bravo") the regex would match — a plain whitespace split
# would not, and would wrongly prune the entity.
_TOKEN_RE = re.compile(r"\w+")


def _fold_diacritics(raw: str) -> tuple[str, list[int]]:
    """Fold a string for matching and map folded positions back to raw ones.

    The fold does three things, all so an alias written with normal spaces and
    no accents can match segment text that differs only in those respects:

    1. **Diacritics** — decomposes each character with canonical (NFD)
       normalization and drops non-spacing combining marks (Unicode category
       ``Mn``), so ``"Perú"`` folds to ``"Peru"``. Case is intentionally left
       untouched — callers keep handling case with ``re.IGNORECASE``.
       Compatibility decomposition (NFKD) is deliberately avoided so ``"½"`` or
       the ``"ﬁ"`` ligature are not expanded, which keeps the fold conservative.
    2. **Whitespace** — collapses every run of whitespace (newlines, tabs,
       non-breaking and other Unicode spaces) to a single regular space, so a
       multi-word alias matches a name a caption split across a line break or an
       ``nbsp`` (bug #293). A whitespace run maps to the raw index of its first
       character.
    3. **Invisibles** — drops zero-width characters and the soft hyphen
       (U+200B/U+200C/U+200D/U+FEFF/U+00AD), which are not whitespace but would
       otherwise break a contiguous match.

    The fold is not length-preserving: a pre-composed character may decompose,
    a combining mark or invisible disappears, and a whitespace run shrinks to
    one space. The returned offset map records, for every folded position, the
    index of the RAW character that produced it, so a match found in folded
    space can be sliced back out of the raw text with correct offsets.

    Parameters
    ----------
    raw : str
        The original (possibly accented / oddly-spaced) string.

    Returns
    -------
    tuple[str, list[int]]
        A ``(folded_text, offset_map)`` pair.  ``offset_map`` has the same
        length as ``folded_text``; ``offset_map[i]`` is the index in ``raw`` of
        the character that produced ``folded_text[i]``.  A folded match spanning
        ``[f_start, f_end)`` maps to raw ``[offset_map[f_start],
        offset_map[f_end - 1] + 1)``.
    """
    folded_chars: list[str] = []
    offset_map: list[int] = []
    prev_was_space = False
    for raw_index, char in enumerate(raw):
        if ord(char) in _MATCH_INVISIBLE_CPS:
            continue
        if char.isspace():
            if not prev_was_space:
                folded_chars.append(" ")
                offset_map.append(raw_index)
                prev_was_space = True
            continue
        prev_was_space = False
        for decomposed in unicodedata.normalize("NFD", char):
            if unicodedata.category(decomposed) == "Mn":
                continue
            folded_chars.append(decomposed)
            offset_map.append(raw_index)
    return "".join(folded_chars), offset_map


def _tokens(form: str) -> list[str]:
    """Return the fold+casefold word-run tokens of a name *form*.

    Folds the form with :func:`_fold_diacritics` (dropping accents, collapsing
    whitespace, stripping invisibles), casefolds it, and splits it into maximal
    word-char runs with :data:`_TOKEN_RE`. This mirrors how the ``\\b``-anchored
    entity regex delimits a token, so a form carrying adjacent punctuation
    (``"bravo,"``) yields the bare token (``"bravo"``) the regex would match; a
    plain whitespace split would not.

    Parameters
    ----------
    form : str
        A name form (canonical name or alias), possibly accented or punctuated.

    Returns
    -------
    list[str]
        The fold+casefold word-run tokens, in order; empty for a form with no
        word characters.
    """
    return _TOKEN_RE.findall(_fold_diacritics(form)[0].casefold())


# Per-language disfluency / filler phrases (Feature 111 US3, FR-010). At match
# time a single interrupting token between two adjacent tokens of an entity name
# is tolerated when it is one of these (compared fold+casefolded, the same space
# the matcher works in). Multi-word fillers (e.g. Spanish "o sea") are a closed,
# enumerated exception to the one-token rule and are stored as token tuples; the
# open-ended false-start / repeat tolerances stay strictly single-token. This is
# a MATCH-TIME tolerance ONLY: no filler is ever written into a stored name,
# alias, or ASR-error form -- it merely lets the matcher span an interruption.
_FILLER_PHRASES_BY_LANG: dict[str, tuple[str, ...]] = {
    "en": ("uh", "um", "er", "hmm", "uhh"),
    "es": ("este", "pues", "eh", "o sea"),
}

# Each filler phrase pre-tokenised with the same fold the matcher uses, so a
# membership test compares like with like. Single-word fillers become 1-tuples.
_FILLER_TOKENS_BY_LANG: dict[str, frozenset[tuple[str, ...]]] = {
    lang: frozenset(tuple(toks) for phrase in phrases if (toks := _tokens(phrase)))
    for lang, phrases in _FILLER_PHRASES_BY_LANG.items()
}


def _filler_tokens_for_language(
    language: str | None,
) -> frozenset[tuple[str, ...]]:
    """Return the filler token tuples for a transcript *language* code.

    The language code is matched on its primary subtag (``"en-US"`` -> ``"en"``),
    case-insensitively. An unknown or missing language yields an empty set, so the
    gap pass then applies only the language-independent false-start / repeat
    tolerances -- never a filler word from another language.

    Parameters
    ----------
    language : str | None
        A BCP-47-ish language code (e.g. ``"en"``, ``"es-MX"``) or ``None``.

    Returns
    -------
    frozenset[tuple[str, ...]]
        The fold+casefold token tuples of the language's filler phrases.
    """
    if not language:
        return frozenset()
    return _FILLER_TOKENS_BY_LANG.get(language.split("-")[0].lower(), frozenset())


def _find_gap_spans(
    seg_tokens: list[str],
    form_tokens: tuple[str, ...],
    filler_tokens: frozenset[tuple[str, ...]],
    max_filler_len: int,
) -> list[tuple[int, int]]:
    """Find gap-tolerant occurrences of *form_tokens* in a token stream.

    Scans ``seg_tokens`` left to right for the ordered token sequence
    ``form_tokens``, allowing between each pair of adjacent name tokens AT MOST
    ONE interrupting token that qualifies as either (a) a member of a per-language
    filler set, (b) a fold-prefix of length >= 2 of the immediately following name
    token (a false start), or (c) a repeat of the immediately preceding name token.
    A closed set of enumerated multi-word filler phrases (``filler_tokens`` entries
    longer than one token) is the only case where more than one interrupting token
    is admitted. A gap of more than one token that is not such a phrase, or a
    non-qualifying token, aborts the match.

    Only matches that actually used at least one gap are returned: a purely
    contiguous occurrence is already produced by the ``\\b``-anchored entity regex,
    so re-emitting it here would duplicate it. Matches are leftmost and
    non-overlapping (the scan resumes past a match), mirroring ``finditer``.

    Parameters
    ----------
    seg_tokens : list[str]
        The segment's fold+casefold word-run tokens, in order.
    form_tokens : tuple[str, ...]
        The entity form's fold+casefold tokens; must have length >= 2.
    filler_tokens : frozenset[tuple[str, ...]]
        Admissible filler phrases as fold+casefold token tuples.
    max_filler_len : int
        The largest token count across ``filler_tokens`` (>= 1).

    Returns
    -------
    list[tuple[int, int]]
        ``(start_index, end_index)`` inclusive token-index pairs, one per
        gap-using match.
    """
    spans: list[tuple[int, int]] = []
    n = len(seg_tokens)
    flen = len(form_tokens)
    i = 0
    while i < n:
        if seg_tokens[i] != form_tokens[0]:
            i += 1
            continue
        si = i + 1
        used_gap = False
        ok = True
        for fi in range(1, flen):
            following = form_tokens[fi]
            preceding = form_tokens[fi - 1]
            # Contiguous continuation is always preferred and never a gap.
            if si < n and seg_tokens[si] == following:
                si += 1
                continue
            # Single interrupting token: filler word, false-start prefix, or
            # a repeat of the preceding name token.
            if si + 1 < n and seg_tokens[si + 1] == following:
                interrupter = seg_tokens[si]
                if (
                    (interrupter,) in filler_tokens
                    or (len(interrupter) >= 2 and following.startswith(interrupter))
                    or interrupter == preceding
                ):
                    si += 2
                    used_gap = True
                    continue
            # Enumerated multi-word filler phrase (the only >1-token gap).
            matched_phrase = False
            for k in range(2, max_filler_len + 1):
                if (
                    si + k < n
                    and seg_tokens[si + k] == following
                    and tuple(seg_tokens[si : si + k]) in filler_tokens
                ):
                    si += k + 1
                    used_gap = True
                    matched_phrase = True
                    break
            if matched_phrase:
                continue
            ok = False
            break
        if ok and used_gap:
            spans.append((i, si - 1))
            i = si
        else:
            i += 1
    return spans


def _asr_form_admissible(form: str) -> bool:
    """Return True if an ASR-error *form* may be admitted as a match pattern.

    Three conjunctive gates (Feature 111, FR-002/FR-002a/FR-003) decide whether a
    registered ASR-error form is safe to match on:

    - **multiword** (FR-002): a single-word form is never admissible. A form is
      multiword iff it contains whitespace, matching the ``entity_asr_errors``
      multiword-candidate filter, so a single-word form can never reach the
      match-pattern builder.
    - **no one-char token** (FR-002a): a form with a ``<= 1``-char token (a stray
      single-letter token) is junk and is excluded.
    - **not all-common** (FR-003): a form whose *every* token is a common word
      (:data:`_COMMON_WORDS`) carries no distinctive name token and is excluded; a
      form that keeps a distinctive token (a surname beside a particle like ``de``
      / ``al``) stays admissible.

    This is the sole admission decision. A per-form reviewer override
    (``usable_as_match_pattern``) is a future *conjunctive* restriction — it can
    only further exclude, never re-admit a gate-excluded form.

    Notes
    -----
    ``_COMMON_WORDS`` is the function-word set for the transcript languages —
    English stopwords plus the Spanish closed-class set (:data:`_ES_COMMON_WORDS`).
    English-only left this gate inert on the bilingual corpus (it rejected zero
    forms); the Spanish set is what makes it do any work, excluding an all-common
    two-word Spanish mis-split ("faith of") with measured zero collateral. The set is
    deliberately closed-class, NOT a dictionary: a dictionary-wide *noun* extension
    was rejected because it excludes genuine recoveries (a first name beside an
    ordinary-word surname). A form that keeps a distinctive token but still mis-fires
    (a distinctive first name beside an English preposition) is outside this gate's
    reach by design — the FR-011 ``usable_as_match_pattern`` override is the lever for
    those.

    Parameters
    ----------
    form : str
        The raw ASR-error form.

    Returns
    -------
    bool
        True iff the form passes all three gates.
    """
    if " " not in form.strip():
        return False
    tokens = _tokens(form)
    if not tokens:
        return False
    if any(len(token) <= 1 for token in tokens):
        return False
    # Admissible iff at least one token is distinctive (not a common word).
    return not all(token in _COMMON_WORDS for token in tokens)


@dataclass
class ScanResult:
    """Aggregate statistics returned after a scan completes.

    Parameters
    ----------
    segments_scanned : int
        Total number of transcript segments examined.
    mentions_found : int
        Number of new entity mention rows inserted (or previewed).
    mentions_skipped : int
        Number of mention matches that were already present (incremental mode).
    unique_entities : int
        Count of distinct entities that produced at least one mention.
    unique_videos : int
        Count of distinct videos that contained at least one mention.
    duration_seconds : float
        Wall-clock time spent on the scan.
    dry_run : bool
        Whether this was a dry-run (no writes).
    failed_batches : int
        Number of segment batches that raised an exception.
    dry_run_matches : list[dict] | None
        Preview match data when ``dry_run=True``, else ``None``.
    skipped_longest_match : int
        Number of matches suppressed by longest-match-wins disambiguation.
    skipped_exclusion_pattern : int
        Number of matches suppressed by exclusion pattern overlap.
    """

    segments_scanned: int = 0
    mentions_found: int = 0
    mentions_skipped: int = 0
    unique_entities: int = 0
    unique_videos: int = 0
    duration_seconds: float = 0.0
    dry_run: bool = False
    failed_batches: int = 0
    dry_run_matches: list[dict[str, Any]] | None = None
    skipped_longest_match: int = 0
    skipped_exclusion_pattern: int = 0
    # Resumability (#291): the last committed keyset position, and whether the
    # scan reached the end of its scope. `last_processed_id` is the transcript
    # segment id; `last_processed_video_id` is the metadata video id. A caller
    # (the CLI) persists these per batch to enable `--resume`.
    last_processed_id: int | None = None
    last_processed_video_id: str | None = None
    completed: bool = False


@dataclass
class _EntityPattern:
    """Pre-compiled pattern data for a single named entity."""

    entity_id: uuid.UUID
    canonical_name: str
    entity_type: str
    pg_pattern: str  # diacritic-folded, re.escaped alias alternation (no \b)
    alias_names: list[str]  # all raw names contributing to pattern
    # Provenance (#298): diacritic-folded alias name -> alias id, for folds that
    # map to exactly ONE alias. A matched span is attributed to an alias by
    # folding it and looking it up here; a fold shared by two aliases
    # (e.g. "pena"/"peña") is absent, so such spans record NULL — the matcher
    # can't tell them apart either, so we don't guess.
    alias_id_by_fold: dict[str, uuid.UUID] = field(default_factory=dict)
    # Provenance (#279/Feature 111): fold+casefold values that are ASR-sourced
    # (registered in ``entity_asr_errors``), keyed the same way as
    # ``alias_id_by_fold`` so a matched span's folded key tells the writer which
    # provenance to record. A fold that also maps to a real name (canonical or
    # alias) is NOT here — real names win provenance — so such a span keeps
    # ``rule_match`` and its alias id.
    asr_folds: frozenset[str] = frozenset()
    exclusion_patterns: list[str] = field(default_factory=list)
    # True when at least one alias opted into case-sensitive matching (#177).
    # The pattern then carries per-alternative `(?i:...)` scopes and MUST be
    # compiled without the global IGNORECASE flag, which would override them.
    has_case_sensitive_alias: bool = False

    @cached_property
    def gap_form_seqs(self) -> frozenset[tuple[str, ...]]:
        """Multi-token token sequences the disfluency-gap matcher scans for.

        A pure function of this entity's own names and ASR folds -- it reads
        nothing about any segment -- so it is computed once per pattern and
        cached here, hoisted out of ``_collect_gap_matches``'s per-segment loop
        (Feature 111 US3). Previously this set was rebuilt for every pattern on
        every scanned segment; because the value depends only on the pattern,
        that was ~segments x patterns reconstructions of ~patterns distinct
        results. Names fold+tokenise via ``_tokens``; ``asr_folds`` are already
        fold+casefold so they tokenise directly. Single-token forms are dropped:
        a one-token name has no interior boundary for a gap.
        """
        seqs: set[tuple[str, ...]] = set()
        for name in (self.canonical_name, *self.alias_names):
            toks = tuple(_tokens(name))
            if len(toks) >= 2:
                seqs.add(toks)
        for fold in self.asr_folds:
            toks = tuple(_TOKEN_RE.findall(fold))
            if len(toks) >= 2:
                seqs.add(toks)
        return frozenset(seqs)


def _compile_entity_regex(pattern: _EntityPattern) -> re.Pattern[str]:
    """Compile an entity's alias alternation with the right case behaviour.

    Transcript and metadata scanning compile the same pattern independently.
    Setting the flag in one and not the other would silently make an alias
    case-sensitive in transcripts but not in titles — a divergence no test
    asserting counts would notice — so both call this.

    The global ``IGNORECASE`` is dropped only when an alias opted in, because
    a global flag overrides the per-alternative ``(?i:...)`` scopes that carry
    the distinction.
    """
    flags = re.NOFLAG if pattern.has_case_sensitive_alias else re.IGNORECASE
    return re.compile(r"\b(" + pattern.pg_pattern + r")\b", flags)


def _build_entity_pattern(
    *,
    entity_id: uuid.UUID,
    canonical_name: str,
    entity_type: str,
    names: list[str],
    case_sensitive_names: set[str],
    exclusion_patterns: list[str],
    alias_id_by_fold: dict[str, uuid.UUID] | None = None,
    asr_forms: list[str] | None = None,
) -> _EntityPattern:
    """Build an :class:`_EntityPattern` from a name set.

    The ONE place the match pattern is constructed, shared by DB loading
    (:meth:`EntityMentionScanService._load_entity_patterns`) and any caller that
    must match provisional names with the *exact same rule* (e.g. candidate
    discovery grounding a not-yet-created entity). Forking this logic would
    silently diverge the two matchers.

    Builds the diacritic-folded alternation ``alias1|alias2|...``: names are folded
    (accents stripped) so the pattern matches accented occurrences in folded text
    (alias "Cafe" matches "Café"); case is handled by ``re.IGNORECASE`` at compile
    time. Names that fold to empty (pure combining marks) are dropped. Case
    sensitivity is per ALIAS but the alternation is per ENTITY, and Python picks the
    first matching alternative — so the list is sorted longest-first and each
    case-sensitive alternative carries its own ``(?i:...)`` scope rather than
    splitting the group (which would break the length ordering). When nothing opts
    in, the pattern and the global ``IGNORECASE`` are built exactly as before.

    ``asr_forms`` (Feature 111 US1b) are registered ASR-error strings, already
    gated for admissibility by the caller. They are folded and added to the
    alternation exactly like names (always case-insensitive), so they match
    transcript text, and their fold+casefold values populate
    :attr:`_EntityPattern.asr_folds` for provenance. **Collision precedence:** a
    folded value that also belongs to a real name (canonical or any alias) is kept
    out of ``asr_folds`` — real names win provenance — so a garble that coincides
    with a real name still records ``rule_match`` and its alias id.
    """
    folded_pairs = [
        (folded, n in case_sensitive_names)
        for n, folded in ((n, _fold_diacritics(n)[0]) for n in names)
        if folded
    ]

    # ASR-error forms join the alternation as always-case-insensitive
    # alternatives; their fold+casefold values seed asr_folds (same keying as
    # alias_id_by_fold). The collision subtraction below ensures a fold shared
    # with a real name does not claim ASR provenance.
    asr_fold_values: set[str] = set()
    for form in asr_forms or []:
        folded = _fold_diacritics(form)[0]
        if folded:
            folded_pairs.append((folded, False))
            asr_fold_values.add(folded.casefold())

    name_folds = {
        folded.casefold()
        for folded in (_fold_diacritics(n)[0] for n in names)
        if folded
    }
    asr_folds = frozenset(asr_fold_values - name_folds)

    folded_pairs.sort(key=lambda p: len(p[0]), reverse=True)

    any_case_sensitive = any(cs for _, cs in folded_pairs)
    if any_case_sensitive:
        pg_pattern = "|".join(
            re.escape(f) if cs else f"(?i:{re.escape(f)})" for f, cs in folded_pairs
        )
    else:
        pg_pattern = "|".join(re.escape(f) for f, _ in folded_pairs)

    return _EntityPattern(
        entity_id=entity_id,
        canonical_name=canonical_name,
        entity_type=entity_type,
        pg_pattern=pg_pattern,
        alias_names=names,
        alias_id_by_fold=alias_id_by_fold or {},
        asr_folds=asr_folds,
        exclusion_patterns=exclusion_patterns,
        has_case_sensitive_alias=any_case_sensitive,
    )


class EntityMentionScanService:
    """Service for scanning transcript segments for named entity mentions.

    Uses PostgreSQL ``~*`` (case-insensitive regex) with ``\\m`` / ``\\M``
    word-boundary markers for accurate detection.  Supports incremental
    scanning (skip segments already matched for a given entity) and full
    rescan (delete + re-detect).

    Parameters
    ----------
    session_factory : async_sessionmaker[AsyncSession]
        Factory for creating database sessions.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._mention_repo = EntityMentionRepository()
        self._asr_error_repo = EntityAsrErrorRepository()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def scan(
        self,
        entity_type: str | None = None,
        video_ids: list[str] | None = None,
        language_code: str | None = None,
        batch_size: int = 500,
        dry_run: bool = False,
        full_rescan: bool = False,
        new_entities_only: bool = False,
        limit: int | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
        entity_ids: list[uuid.UUID] | None = None,
        resume_from: int | None = None,
        should_continue: Callable[[], bool] | None = None,
        checkpoint_callback: Callable[[int], None] | None = None,
    ) -> ScanResult:
        """Scan transcript segments for entity mentions.

        Parameters
        ----------
        entity_type : str | None
            Restrict scanning to entities of this type.
        video_ids : list[str] | None
            Restrict scanning to segments from these videos.
        language_code : str | None
            Restrict scanning to segments in this language.
        batch_size : int
            Number of segments fetched per batch (default 500).
        dry_run : bool
            If ``True``, collect preview data without writing.
        full_rescan : bool
            If ``True``, delete existing ``rule_match`` mentions in scope
            before scanning.
        new_entities_only : bool
            If ``True``, only scan entities that have zero existing mentions.
        limit : int | None
            Cap the number of dry-run preview rows collected.
        progress_callback : Callable[[int, int], None] | None
            Called after each batch with ``(segments_scanned, mentions_found)``.
        entity_ids : list[uuid.UUID] | None
            Restrict scanning to these specific entity IDs.  Applied as an
            AND filter together with ``entity_type`` when both are provided.

        Returns
        -------
        ScanResult
            Aggregate statistics about the scan.
        """
        t0 = time.monotonic()

        logger.info(
            "Scan starting: entity_ids=%s, video_ids=%s, dry_run=%s, "
            "entity_type=%s, full_rescan=%s, new_entities_only=%s",
            entity_ids,
            video_ids,
            dry_run,
            entity_type,
            full_rescan,
            new_entities_only,
        )

        async with self._session_factory() as session:
            # 1. Load entity patterns
            patterns = await self._load_entity_patterns(
                session,
                entity_type=entity_type,
                new_entities_only=new_entities_only,
                entity_ids=entity_ids,
            )

            if not patterns:
                logger.info("No active entities matched the filter criteria")
                return ScanResult(
                    dry_run=dry_run, duration_seconds=time.monotonic() - t0
                )

            scoped_entity_ids = [p.entity_id for p in patterns]

            # NOTE 020 §2/§5: the WRITE set is scoped_entity_ids, but when the
            # scan is scoped the MATCH set must be WIDER so cross-entity
            # longest-match-wins can arbitrate. Patterns compile
            # word-boundary-anchored, so two names can produce overlapping
            # matches iff they share a whole name token (shared-token, NOT
            # containment — see _shared_token_neighbour_ids). Load those
            # neighbours too, match with the union, then discard survivors
            # whose entity is not in the write scope (per-segment batch path
            # only; _scan_cross_segment keeps the narrow patterns — #279).
            write_scope = set(scoped_entity_ids)
            match_patterns = patterns
            if entity_ids is not None or entity_type is not None or new_entities_only:
                neighbour_ids = await self._shared_token_neighbour_ids(
                    session, patterns
                )
                extra_ids = [nid for nid in neighbour_ids if nid not in write_scope]
                if extra_ids:
                    neighbour_patterns = await self._load_entity_patterns(
                        session,
                        entity_type=None,
                        new_entities_only=False,
                        entity_ids=extra_ids,
                    )
                    match_patterns = patterns + neighbour_patterns

            # 2. (#291) Under --full, the delete of existing transcript mentions
            #    is done PER BATCH (scoped to that batch's segment ids) and
            #    committed together with the batch's re-inserts — see the loop
            #    below — so an interrupt never leaves segments deleted-but-not-
            #    re-detected. No global upfront delete.

            # 3. Process segments in batches
            result = ScanResult(dry_run=dry_run)
            if dry_run:
                result.dry_run_matches = []

            matched_entity_ids: set[uuid.UUID] = set()
            matched_video_ids: set[str] = set()

            last_id = resume_from or 0
            fetch_failures_at_cursor = 0
            stopped_early = False
            exhausted = False
            while True:
                try:
                    batch_rows = await self._fetch_segment_batch(
                        session,
                        video_ids=video_ids,
                        language_code=language_code,
                        batch_size=batch_size,
                        after_id=last_id,
                    )
                except Exception:
                    # Under OFFSET pagination a failed fetch could be skipped by
                    # advancing the offset. A cursor has no such fixed stride:
                    # the ids to skip are exactly the ones the failed query did
                    # not return. Retrying is the only way forward, so bound it
                    # rather than spin.
                    logger.warning(
                        "Failed to fetch segment batch after id=%d",
                        last_id,
                        exc_info=True,
                    )
                    result.failed_batches += 1
                    fetch_failures_at_cursor += 1
                    # Clear any aborted transaction before retrying the fetch.
                    await session.rollback()
                    if fetch_failures_at_cursor >= _MAX_FETCH_RETRIES:
                        logger.error(
                            "Aborting scan: %d consecutive fetch failures after "
                            "id=%d. Scanned %d segments before stopping.",
                            fetch_failures_at_cursor,
                            last_id,
                            result.segments_scanned,
                        )
                        break
                    continue
                fetch_failures_at_cursor = 0

                if not batch_rows:
                    exhausted = True
                    break

                result.segments_scanned += len(batch_rows)

                try:
                    (
                        batch_mentions,
                        batch_skipped,
                        batch_previews,
                        batch_lmw_skips,
                        batch_ep_skips,
                    ) = await self._scan_batch(
                        session,
                        batch_rows=batch_rows,
                        patterns=match_patterns,
                        full_rescan=full_rescan,
                        dry_run=dry_run,
                        limit=limit,
                        current_preview_count=(
                            len(result.dry_run_matches)
                            if result.dry_run_matches is not None
                            else 0
                        ),
                        # NOTE 020 §2: when the MATCH set was widened to
                        # shared-token neighbours, drop their matches inside the
                        # batch (after longest-match-wins arbitrates) so counters,
                        # dedup, and the preview cap all see only the write scope.
                        write_scope=(
                            write_scope if match_patterns is not patterns else None
                        ),
                    )
                except Exception:
                    logger.warning(
                        "Failed to process segment batch after id=%d",
                        last_id,
                        exc_info=True,
                    )
                    result.failed_batches += 1
                    # Clear any aborted transaction from the failed batch so the
                    # next fetch/commit starts clean (prior committed batches are
                    # untouched by this rollback).
                    await session.rollback()
                    # (#291/FR-016) Isolate the bad batch: prior batches are
                    # already committed and are NOT rolled back. Advance past the
                    # poisoned rows and persist that position so a resume skips
                    # them instead of re-hitting the same failure forever.
                    last_id = batch_rows[-1].id
                    result.last_processed_id = last_id
                    if progress_callback:
                        progress_callback(
                            result.segments_scanned, result.mentions_found
                        )
                    if checkpoint_callback and not dry_run:
                        checkpoint_callback(last_id)
                    continue

                # Accumulate results
                for m in batch_mentions:
                    matched_entity_ids.add(m.entity_id)
                    matched_video_ids.add(m.video_id)

                if not dry_run:
                    # (#291) Per-batch, resumable-unit write: under --full, delete
                    # this batch's existing transcript mentions and re-insert the
                    # freshly detected ones, then recompute counters for every
                    # entity this batch changed, and COMMIT — all together. The
                    # entities whose counts change are those matched now PLUS any
                    # whose mentions this batch deletes (so an entity that matched
                    # nothing new but lost mentions is still made consistent).
                    batch_segment_ids = [r.id for r in batch_rows]
                    batch_touched: set[uuid.UUID] = {
                        m.entity_id for m in batch_mentions
                    }
                    if full_rescan:
                        delete_affected = await self._mention_repo.entities_with_transcript_mentions_in_segments(
                            session,
                            segment_ids=batch_segment_ids,
                            entity_ids=scoped_entity_ids,
                        )
                        batch_touched.update(delete_affected)
                        await self._mention_repo.delete_transcript_mentions_by_segments(
                            session,
                            segment_ids=batch_segment_ids,
                            entity_ids=scoped_entity_ids,
                        )

                    if batch_mentions:
                        inserted = (
                            await self._mention_repo.bulk_create_with_conflict_skip(
                                session, batch_mentions
                            )
                        )
                        result.mentions_found += inserted
                        result.mentions_skipped += len(batch_mentions) - inserted

                    if batch_touched:
                        await self._mention_repo.update_entity_counters(
                            session, list(batch_touched)
                        )
                        await self._mention_repo.update_alias_counters(
                            session, list(batch_touched)
                        )

                    # Commit this batch's work as one durable unit (#291).
                    await session.commit()
                else:
                    result.mentions_found += len(batch_mentions)
                    if result.dry_run_matches is not None and batch_previews:
                        result.dry_run_matches.extend(batch_previews)

                result.mentions_skipped += batch_skipped
                result.skipped_longest_match += batch_lmw_skips
                result.skipped_exclusion_pattern += batch_ep_skips

                last_id = batch_rows[-1].id
                result.last_processed_id = last_id

                if progress_callback:
                    progress_callback(result.segments_scanned, result.mentions_found)
                # Persist the resume position only AFTER the batch commit, so the
                # saved cursor is never ahead of durable data (#291 SEAM-1).
                if checkpoint_callback and not dry_run:
                    checkpoint_callback(last_id)

                # If dry-run and we have reached the limit, stop early
                if (
                    dry_run
                    and limit is not None
                    and result.dry_run_matches is not None
                    and len(result.dry_run_matches) >= limit
                ):
                    # Trim to limit
                    result.dry_run_matches = result.dry_run_matches[:limit]
                    break

                # Cooperative graceful stop (e.g. Ctrl+C via the CLI): the just-
                # committed batch is durable; stop before fetching more (#291).
                if should_continue is not None and not should_continue():
                    stopped_early = True
                    break

            result.unique_entities = len(matched_entity_ids)
            result.unique_videos = len(matched_video_ids)

            # Feature 081 + 111 US4: per-transcript cross-segment pass. Detects names
            # split across segment boundaries and writes ONE spanning mention per
            # occurrence (segment_id=first, end_segment_id=last). It owns spanning
            # mentions end-to-end (its own per-transcript --full delete/reinsert).
            # FR-005/FR-006: spanning and in-segment matches now arbitrate in ONE
            # longest-match-wins pool, so a surviving spanning match SUPPRESSES any
            # in-segment mention it overlaps (that the per-segment pass wrote in its
            # own pool); non-overlapping in-segment mentions are left untouched. Runs
            # before the final --full recompute below so that covers both changes.
            await self._scan_cross_segment(
                session,
                patterns,
                video_ids=video_ids,
                language_code=language_code,
                scoped_entity_ids=scoped_entity_ids,
                full_rescan=full_rescan,
                dry_run=dry_run,
                limit=limit,
                result=result,
            )

            # 4/5. (#291) Counter recompute and commit are now per batch (see the
            # loop). Under --full, each batch recomputes counters for the entities
            # it matched OR whose mentions it deleted, so an entity that loses all
            # its mentions is zeroed in the batch that deleted them — no separate
            # end-of-run pass is needed, and counters stay consistent with the
            # mentions committed so far. Record whether the scan reached the end
            # of its scope (vs stopped early by a cooperative interrupt or a
            # fetch-failure abort) so a caller can clear/keep its resume position.
            result.completed = exhausted and not stopped_early

            # Under --full, a COMPLETED run recomputes counters for ALL scoped
            # entities: per-batch recompute only covers entities a batch matched
            # or whose mentions it deleted, so an entity that lost every mention
            # (or carried a stale count with no rows in any scanned segment) would
            # otherwise keep a wrong count. On an interrupted run this is skipped
            # and the eventual resume-to-completion performs it. (FR-008 holds
            # during the run for entities the run actually touched.)
            if full_rescan and not dry_run and result.completed and scoped_entity_ids:
                await self._mention_repo.update_entity_counters(
                    session, scoped_entity_ids
                )
                await self._mention_repo.update_alias_counters(
                    session, scoped_entity_ids
                )
                await session.commit()

            result.duration_seconds = time.monotonic() - t0

            logger.info(
                "Scan complete: segments_scanned=%d, mentions_found=%d, "
                "mentions_skipped=%d, unique_entities=%d, unique_videos=%d, "
                "duration=%.2fs, dry_run=%s, failed_batches=%d, "
                "skipped_longest_match=%d, skipped_exclusion_pattern=%d",
                result.segments_scanned,
                result.mentions_found,
                result.mentions_skipped,
                result.unique_entities,
                result.unique_videos,
                result.duration_seconds,
                result.dry_run,
                result.failed_batches,
                result.skipped_longest_match,
                result.skipped_exclusion_pattern,
            )

            return result

    async def _fetch_transcripts_in_scope(
        self,
        session: AsyncSession,
        video_ids: list[str] | None,
        language_code: str | None,
    ) -> list[tuple[str, str]]:
        """List the ``(video_id, language_code)`` transcripts to cross-segment scan."""
        stmt: Select[tuple[str, str]] = select(
            VideoTranscriptDB.video_id, VideoTranscriptDB.language_code
        )
        if video_ids is not None:
            stmt = stmt.where(VideoTranscriptDB.video_id.in_(video_ids))
        if language_code is not None:
            stmt = stmt.where(VideoTranscriptDB.language_code == language_code)
        stmt = stmt.order_by(
            VideoTranscriptDB.video_id.asc(), VideoTranscriptDB.language_code.asc()
        )
        result = await session.execute(stmt)
        return [(r.video_id, r.language_code) for r in result.all()]

    async def _fetch_transcript_segments(
        self, session: AsyncSession, video_id: str, language_code: str
    ) -> list[Any]:
        """Fetch one transcript's segments ordered by ``sequence_number``.

        Returns raw ``text``/``corrected_text``/``has_correction`` so the shared
        ``TranscriptTextIndex`` applies the single effective-text rule; ordered by
        ``sequence_number`` so the assembled text matches playback order.
        """
        stmt: Select[tuple[Any, ...]] = (
            select(
                TranscriptSegmentDB.id,
                TranscriptSegmentDB.text,
                TranscriptSegmentDB.corrected_text,
                TranscriptSegmentDB.has_correction,
                TranscriptSegmentDB.start_time,
            )
            .where(
                TranscriptSegmentDB.video_id == video_id,
                TranscriptSegmentDB.language_code == language_code,
            )
            .order_by(TranscriptSegmentDB.sequence_number.asc())
        )
        result = await session.execute(stmt)
        return list(result.all())

    async def _scan_cross_segment(
        self,
        session: AsyncSession,
        patterns: list[_EntityPattern],
        *,
        video_ids: list[str] | None,
        language_code: str | None,
        scoped_entity_ids: list[uuid.UUID],
        full_rescan: bool,
        dry_run: bool,
        limit: int | None,
        result: ScanResult,
    ) -> None:
        """Per-transcript pass detecting names split across segments (081 + 111 US4).

        Assembles each transcript's segments into one string via the shared
        ``TranscriptTextIndex``, runs the same entity patterns over it, and writes
        one spanning mention per boundary-crossing occurrence (anchor at the first
        segment, ``end_segment_id`` at the last). Single-segment survivors are not
        written here (the per-segment pass owns those).

        Feature 111 US4 (FR-005/FR-006): spanning and single-segment matches
        arbitrate in ONE longest-match-wins pool over the concatenated text, so a
        surviving spanning match out-competes every in-segment match it overlaps.
        Because the per-segment pass wrote those overlapping in-segment mentions in
        its own separate pool, this pass deletes exactly the suppressed in-segment
        rows (by their ``(segment_id, entity_id, match_start, match_end)``
        coordinates). A non-overlapping in-segment mention overlaps no spanning span
        and is always kept. Under ``full_rescan`` it also deletes and re-inserts
        spanning mentions per transcript (FR-012 scoping).
        """
        compiled_patterns: list[tuple[_EntityPattern, re.Pattern[str]]] = []
        for pattern in patterns:
            try:
                compiled_patterns.append((pattern, _compile_entity_regex(pattern)))
            except re.error:
                continue
        if not compiled_patterns:
            return
        pattern_by_entity = {p.entity_id: p for p in patterns}

        # Candidate-token pre-filter (perf). Running every entity's regex over
        # every transcript's full text is O(transcripts x patterns x len) and
        # dominates the scan (~53 min on the full corpus). Instead, index each
        # entity by the word tokens of its name forms; per transcript, run only
        # the regexes of entities sharing at least one token with the text. An
        # entity sharing no token cannot match (every token of a matched form
        # must appear for the \b-anchored regex to hit), so this skips only
        # guaranteed non-matches and leaves the spanning-match set byte-identical.
        #
        # LOAD-BEARING INVARIANT: ``TranscriptTextIndex.SEGMENT_SEPARATOR`` is a
        # single space. A name split at a token boundary across segments
        # ("Alfa" | "Bravo") joins to "alfa bravo" with both tokens whole,
        # so the present-token test keeps the entity. A name split MID-token
        # ("Fox" | "trot") joins to "fox trot", which the \b regex cannot match
        # anyway, so pruning it loses nothing. If SEGMENT_SEPARATOR is ever
        # changed to join WITHOUT a space (to catch mid-token breaks), a real
        # match could have an absent token and this pre-filter would wrongly
        # prune it — this code MUST be revisited if that constant changes.
        if SEGMENT_SEPARATOR != " ":  # pragma: no cover - guards the invariant
            raise RuntimeError(
                "cross-segment token pre-filter assumes a single-space segment "
                "separator; revisit it before changing SEGMENT_SEPARATOR"
            )
        token_to_entities: dict[str, set[uuid.UUID]] = {}
        always_run: set[uuid.UUID] = set()
        for pattern in patterns:
            form_tokens: set[str] = set()
            tokenless_form = False
            for form in (pattern.canonical_name, *pattern.alias_names):
                toks = _tokens(form)
                if toks:
                    form_tokens.update(toks)
                else:
                    tokenless_form = True
            # A form with no word tokens (e.g. a punctuation-only alias) can't be
            # gated by token presence, so such an entity always runs.
            if tokenless_form or not form_tokens:
                always_run.add(pattern.entity_id)
            else:
                for tok in form_tokens:
                    token_to_entities.setdefault(tok, set()).add(pattern.entity_id)

        for video_id, lang in await self._fetch_transcripts_in_scope(
            session, video_ids, language_code
        ):
            segs = await self._fetch_transcript_segments(session, video_id, lang)
            if len(segs) < 2:
                continue  # no boundary to span
            index = TranscriptTextIndex.from_segments(
                [
                    SegmentInput(
                        segment_id=s.id,
                        text=s.text,
                        corrected_text=s.corrected_text,
                        has_correction=s.has_correction,
                    )
                    for s in segs
                ]
            )
            folded_text, offset_map = _fold_diacritics(index.text)
            # Only entities sharing a token with this transcript can match.
            present_tokens = set(_TOKEN_RE.findall(folded_text.casefold()))
            candidates = set(always_run)
            for tok in present_tokens:
                ents = token_to_entities.get(tok)
                if ents:
                    candidates.update(ents)
            raw_matches: list[tuple[uuid.UUID, int, int, str, _EntityPattern]] = []
            for pattern, py_regex in compiled_patterns:
                if pattern.entity_id not in candidates:
                    continue
                for match in py_regex.finditer(folded_text):
                    f_start, f_end = match.start(), match.end()
                    if f_end <= f_start:
                        continue
                    raw_start = offset_map[f_start]
                    raw_end = offset_map[f_end - 1] + 1
                    raw_matches.append(
                        (
                            pattern.entity_id,
                            raw_start,
                            raw_end,
                            index.text[raw_start:raw_end],
                            pattern,
                        )
                    )
            # Feature 111 US3 (FR-010): additively add disfluency-gap matches,
            # scoped to the same per-transcript candidate entities as the regex.
            raw_matches.extend(
                self._collect_gap_matches(
                    folded_text,
                    offset_map,
                    index.text,
                    [p for p, _ in compiled_patterns if p.entity_id in candidates],
                    lang,
                )
            )
            if not raw_matches:
                # A transcript that matches NOTHING skips the per-transcript --full
                # delete below. A spanning mention only disappears here if its
                # transcript now matches no entity at all (rare); such a stale span
                # is cleared by the next rescan where the transcript matches. Running
                # a delete+recount on every empty transcript would not be worth the
                # per-transcript cost. (The common disappear case — the transcript
                # still matches something — IS handled, via delete_affected below.)
                continue

            log_row = SimpleNamespace(
                id=segs[0].id,
                video_id=video_id,
                language_code=lang,
                start_time=segs[0].start_time,
            )
            surviving, lmw_skips = self._apply_longest_match_wins(
                raw_matches, log_row, dry_run
            )
            result.skipped_longest_match += lmw_skips
            final_matches, ep_skips = self._apply_exclusion_patterns(
                surviving, index.text, pattern_by_entity, log_row, dry_run
            )
            result.skipped_exclusion_pattern += ep_skips

            # Feature 111 US4 (FR-005/FR-006): single longest-match-wins pool per
            # transcript. ``_apply_longest_match_wins`` above arbitrated spanning
            # and single-segment matches TOGETHER over the concatenated text, so a
            # surviving spanning match has already out-competed every in-segment
            # match it overlaps. The per-segment pass wrote those overlapping
            # in-segment mentions in its OWN pool (it never saw the spanning span),
            # so they must now be deleted — but ONLY the ones that overlap a
            # surviving spanning match. A non-overlapping in-segment match (e.g. a
            # far, same-name occurrence) overlaps no spanning span and is kept.
            spanning_spans = [
                (m_start, m_end)
                for _eid, m_start, m_end, _txt, _pat in final_matches
                if index.resolve_span(m_start, m_end).end_segment_id is not None
            ]
            suppression_targets: list[tuple[int, uuid.UUID, int, int]] = []
            if spanning_spans:
                for entity_id, m_start, m_end, _txt, _pat in raw_matches:
                    anchor = index.resolve_span(m_start, m_end)
                    if anchor.end_segment_id is not None:
                        continue  # a spanning match is not a per-segment-pass row
                    if any(
                        s_start < m_end and s_end > m_start
                        for s_start, s_end in spanning_spans
                    ):
                        suppression_targets.append(
                            (
                                anchor.segment_id,
                                entity_id,
                                anchor.match_start,
                                anchor.match_end,
                            )
                        )

            mentions: list[EntityMentionCreate] = []
            for entity_id, m_start, m_end, matched_text, pat in final_matches:
                anchor = index.resolve_span(m_start, m_end)
                if anchor.end_segment_id is None:
                    continue  # single-segment; owned by the per-segment pass
                fold_key = _fold_diacritics(matched_text)[0].casefold()
                mentions.append(
                    EntityMentionCreate(
                        entity_id=entity_id,
                        segment_id=anchor.segment_id,
                        end_segment_id=anchor.end_segment_id,
                        video_id=video_id,
                        language_code=lang,
                        mention_text=matched_text,
                        # A boundary-crossing ASR-error form keeps its asr_match
                        # provenance (spanning asr_match is a valid transcript
                        # writer — see SPANNING_DETECTION_METHODS), so recovered
                        # spanning mentions stay revertible/auditable (FR-014/
                        # SC-009) instead of masquerading as rule_match. The
                        # cross-segment --full delete covers asr_match too, so the
                        # re-insert is idempotent. ``alias_id`` stays NULL for a
                        # garble fold (asr folds are excluded from alias_id_by_fold).
                        detection_method=(
                            DetectionMethod.ASR_MATCH
                            if fold_key in pat.asr_folds
                            else DetectionMethod.RULE_MATCH
                        ),
                        confidence=1.0,
                        match_start=anchor.match_start,
                        match_end=anchor.match_end,
                        mention_context=self._extract_context_snippet(
                            index.text, m_start, m_end
                        ),
                        alias_id=pat.alias_id_by_fold.get(fold_key),
                    )
                )
                if dry_run and result.dry_run_matches is not None:
                    if limit is None or len(result.dry_run_matches) < limit:
                        result.dry_run_matches.append(
                            {
                                "video_id": video_id,
                                "segment_id": anchor.segment_id,
                                "start_time": segs[0].start_time,
                                "entity_name": pat.canonical_name,
                                "entity_type": pat.entity_type,
                                "matched_text": matched_text,
                                "match_start": anchor.match_start,
                                "match_end": anchor.match_end,
                                "context": self._extract_context_snippet(
                                    index.text, m_start, m_end
                                ),
                            }
                        )

            if dry_run:
                result.mentions_found += len(mentions)
                continue
            if not mentions and not full_rescan and not suppression_targets:
                continue

            seg_ids = [s.id for s in segs]
            touched: set[uuid.UUID] = {m.entity_id for m in mentions}
            if full_rescan:
                # An entity whose spanning mention this delete removes must be
                # recomputed even if nothing new was detected for it — otherwise a
                # disappeared span leaves a stale count. Mirrors the per-segment
                # path's delete_affected handling (SC-007 convergence invariant).
                delete_affected = await self._mention_repo.entities_with_transcript_mentions_in_segments(
                    session, segment_ids=seg_ids, entity_ids=scoped_entity_ids
                )
                touched.update(delete_affected)
                await self._mention_repo.delete_spanning_mentions_by_segments(
                    session, segment_ids=seg_ids, entity_ids=scoped_entity_ids
                )
            if suppression_targets:
                # Single-pool compete (FR-005/FR-006): remove the in-segment
                # mentions the surviving spanning match out-competed. Their
                # entities' counters must be recomputed even when nothing new was
                # detected for them, so add them to ``touched``.
                await self._mention_repo.delete_in_segment_mentions_at(
                    session, targets=suppression_targets
                )
                touched.update(eid for _seg, eid, _s, _e in suppression_targets)
            if mentions:
                inserted = await self._mention_repo.bulk_create_with_conflict_skip(
                    session, mentions
                )
                result.mentions_found += inserted
                result.mentions_skipped += len(mentions) - inserted
            if touched:
                await self._mention_repo.update_entity_counters(session, list(touched))
                await self._mention_repo.update_alias_counters(session, list(touched))
            await session.commit()

    async def audit_unregistered_mentions(
        self,
    ) -> list[tuple[str, uuid.UUID, str, int]]:
        """Find user-correction mentions whose text is not registered as an alias.

        Queries all ``entity_mentions`` rows where
        ``detection_method = 'user_correction'`` for active entities, then
        LEFT JOINs against ``entity_aliases`` to find mention texts that do
        **not** match any alias (case-insensitive) and also differ from the
        entity's canonical name.

        Returns
        -------
        list[tuple[str, uuid.UUID, str, int]]
            List of ``(canonical_name, entity_id, mention_text, segment_count)``
            tuples, ordered by canonical name ascending then segment count
            descending.
        """
        async with self._session_factory() as session:
            stmt = (
                select(
                    EntityMentionDB.entity_id,
                    NamedEntityDB.canonical_name,
                    EntityMentionDB.mention_text,
                    func.count().label("segment_count"),
                )
                .join(
                    NamedEntityDB,
                    EntityMentionDB.entity_id == NamedEntityDB.id,
                )
                .outerjoin(
                    EntityAliasDB,
                    (EntityMentionDB.entity_id == EntityAliasDB.entity_id)
                    & (
                        func.lower(EntityMentionDB.mention_text)
                        == func.lower(EntityAliasDB.alias_name)
                    ),
                )
                .where(
                    EntityMentionDB.detection_method
                    == DetectionMethod.USER_CORRECTION.value,
                    NamedEntityDB.status == "active",
                    func.lower(EntityMentionDB.mention_text)
                    != func.lower(NamedEntityDB.canonical_name),
                    EntityAliasDB.id.is_(None),
                )
                .group_by(
                    EntityMentionDB.entity_id,
                    NamedEntityDB.canonical_name,
                    EntityMentionDB.mention_text,
                )
                .order_by(
                    NamedEntityDB.canonical_name.asc(),
                    text("segment_count DESC"),
                )
            )

            result = await session.execute(stmt)
            rows = result.all()

            return [
                (row.canonical_name, row.entity_id, row.mention_text, row.segment_count)
                for row in rows
            ]

    async def scan_metadata(
        self,
        sources: list[str],
        entity_type: str | None = None,
        video_ids: list[str] | None = None,
        language_code: str | None = None,
        batch_size: int = 500,
        dry_run: bool = False,
        full_rescan: bool = False,
        new_entities_only: bool = False,
        entity_ids: list[uuid.UUID] | None = None,
        limit: int | None = None,
        progress_callback: Callable[[int, int], None] | None = None,
        resume_from_video_id: str | None = None,
        should_continue: Callable[[], bool] | None = None,
        checkpoint_callback: Callable[[str], None] | None = None,
    ) -> ScanResult:
        """Scan video titles and/or descriptions for entity mentions.

        Unlike :meth:`scan` which iterates over transcript segments, this
        method iterates over the ``videos`` table and matches entity
        patterns against the ``title`` and/or ``description`` columns.

        Parameters
        ----------
        sources : list[str]
            Which metadata fields to scan. Valid values: ``"title"``,
            ``"description"``.
        entity_type : str | None
            Restrict scanning to entities of this type.
        video_ids : list[str] | None
            Restrict scanning to these videos.
        language_code : str | None
            Unused for metadata scanning but accepted for interface
            consistency with :meth:`scan`.
        batch_size : int
            Number of video rows fetched per batch (default 500).
        dry_run : bool
            If ``True``, collect preview data without writing.
        full_rescan : bool
            If ``True``, delete existing mentions of the specified source
            types before re-scanning (per FR-010).
        entity_ids : list[uuid.UUID] | None
            Restrict scanning to these specific entity IDs.
        limit : int | None
            In dry-run mode, stop scanning once this many preview matches have
            been collected (mirrors :meth:`scan`). Ignored in live mode.
        progress_callback : Callable[[int, int], None] | None
            Called after each batch with ``(items_scanned, mentions_found)``.

        Returns
        -------
        ScanResult
            Aggregate statistics about the scan.
        """
        t0 = time.monotonic()

        logger.info(
            "Metadata scan starting: sources=%s, entity_ids=%s, video_ids=%s, "
            "dry_run=%s, entity_type=%s, full_rescan=%s",
            sources,
            entity_ids,
            video_ids,
            dry_run,
            entity_type,
            full_rescan,
        )

        async with self._session_factory() as session:
            # 1. Load entity patterns
            patterns = await self._load_entity_patterns(
                session,
                entity_type=entity_type,
                new_entities_only=new_entities_only,
                entity_ids=entity_ids,
            )

            if not patterns:
                logger.info("No active entities matched the filter criteria")
                return ScanResult(
                    dry_run=dry_run, duration_seconds=time.monotonic() - t0
                )

            scoped_entity_ids = [p.entity_id for p in patterns]

            # NOTE 020 §2/§5: the same write-set=match-set collapse scan() had.
            # The WRITE set stays scoped_entity_ids, but when the scan is scoped
            # the MATCH set must be WIDER so cross-entity longest-match-wins can
            # arbitrate. Patterns compile word-boundary-anchored, so two names
            # can produce overlapping matches iff they share a whole name token
            # (shared-token, NOT containment — see _shared_token_neighbour_ids).
            # Load those neighbours too, match with the union, then discard
            # survivors whose entity is not in the write scope (inside
            # _match_text_for_video, after longest-match-wins + exclusion).
            write_scope = set(scoped_entity_ids)
            match_patterns = patterns
            if entity_ids is not None or entity_type is not None or new_entities_only:
                neighbour_ids = await self._shared_token_neighbour_ids(
                    session, patterns
                )
                extra_ids = [nid for nid in neighbour_ids if nid not in write_scope]
                if extra_ids:
                    neighbour_patterns = await self._load_entity_patterns(
                        session,
                        entity_type=None,
                        new_entities_only=False,
                        entity_ids=extra_ids,
                    )
                    match_patterns = patterns + neighbour_patterns

            # 2. (#291) Under --full, the delete of existing metadata mentions is
            #    done PER BATCH (scoped to that batch's video ids) and committed
            #    together with the batch's re-inserts — see the loop below.

            # 3. Pre-compile Python regexes (over the possibly-widened MATCH set)
            compiled_patterns: list[tuple[_EntityPattern, re.Pattern[str]]] = []
            for pattern in match_patterns:
                try:
                    py_regex = _compile_entity_regex(pattern)
                    compiled_patterns.append((pattern, py_regex))
                except re.error:
                    logger.warning(
                        "Failed to compile regex for entity %s (%s), skipping",
                        pattern.canonical_name,
                        pattern.entity_id,
                    )

            pattern_by_entity: dict[uuid.UUID, _EntityPattern] = {
                p.entity_id: p for p in match_patterns
            }

            # NOTE 020 §2: when the MATCH set was widened to shared-token
            # neighbours, drop their matches after longest-match-wins arbitrates
            # (inside _match_text_for_video) so counters, dedup, and the preview
            # cap all see only the write scope. ``None`` for an unscoped scan.
            batch_write_scope = write_scope if match_patterns is not patterns else None

            # 4. Process videos in batches
            result = ScanResult(dry_run=dry_run)
            if dry_run:
                result.dry_run_matches = []

            matched_entity_ids: set[uuid.UUID] = set()
            matched_video_ids: set[str] = set()

            last_video_id = resume_from_video_id or ""
            fetch_failures_at_cursor = 0
            stopped_early = False
            exhausted = False
            while True:
                try:
                    batch_rows = await self._fetch_video_batch(
                        session,
                        video_ids=video_ids,
                        batch_size=batch_size,
                        after_video_id=last_video_id,
                    )
                except Exception:
                    logger.warning(
                        "Failed to fetch video batch after video_id=%r",
                        last_video_id,
                        exc_info=True,
                    )
                    result.failed_batches += 1
                    fetch_failures_at_cursor += 1
                    await session.rollback()
                    if fetch_failures_at_cursor >= _MAX_FETCH_RETRIES:
                        logger.error(
                            "Aborting metadata scan: %d consecutive fetch "
                            "failures after video_id=%r. Scanned %d videos "
                            "before stopping.",
                            fetch_failures_at_cursor,
                            last_video_id,
                            result.segments_scanned,
                        )
                        break
                    continue
                fetch_failures_at_cursor = 0

                if not batch_rows:
                    exhausted = True
                    break

                result.segments_scanned += len(batch_rows)

                try:
                    batch_mentions, batch_previews = self._scan_metadata_batch(
                        batch_rows=batch_rows,
                        compiled_patterns=compiled_patterns,
                        pattern_by_entity=pattern_by_entity,
                        sources=sources,
                        dry_run=dry_run,
                        write_scope=batch_write_scope,
                    )
                except Exception:
                    logger.warning(
                        "Failed to process video batch after video_id=%r",
                        last_video_id,
                        exc_info=True,
                    )
                    result.failed_batches += 1
                    await session.rollback()
                    last_video_id = batch_rows[-1].video_id
                    result.last_processed_video_id = last_video_id
                    if progress_callback:
                        progress_callback(
                            result.segments_scanned, result.mentions_found
                        )
                    if checkpoint_callback and not dry_run:
                        checkpoint_callback(last_video_id)
                    continue

                for m in batch_mentions:
                    matched_entity_ids.add(m.entity_id)
                    matched_video_ids.add(m.video_id)

                if not dry_run:
                    # (#291) Per-batch, resumable-unit write mirroring scan():
                    # delete this batch's videos' metadata mentions (per source)
                    # and re-insert, recompute counters for matched-or-deleted
                    # entities, and COMMIT together.
                    batch_video_ids = [r.video_id for r in batch_rows]
                    batch_touched: set[uuid.UUID] = {
                        m.entity_id for m in batch_mentions
                    }
                    if full_rescan:
                        delete_affected = await self._mention_repo.entities_with_metadata_mentions_in_videos(
                            session,
                            video_ids=batch_video_ids,
                            sources=sources,
                            entity_ids=scoped_entity_ids,
                        )
                        batch_touched.update(delete_affected)
                        # Delete every scan-owned method (rule_match + asr_match),
                        # matching the write and counter sets so a recovered
                        # metadata mention is refreshed on --full rather than left
                        # stale (SCAN_DETECTION_METHODS).
                        for source in sources:
                            for method in SCAN_DETECTION_METHODS:
                                await self._mention_repo.delete_by_scope(
                                    session,
                                    entity_ids=scoped_entity_ids,
                                    video_ids=batch_video_ids,
                                    detection_method=method.value,
                                    mention_source=source,
                                )

                    if batch_mentions:
                        inserted = (
                            await self._mention_repo.bulk_create_with_conflict_skip(
                                session, batch_mentions
                            )
                        )
                        result.mentions_found += inserted
                        result.mentions_skipped += len(batch_mentions) - inserted

                    if batch_touched:
                        await self._mention_repo.update_entity_counters(
                            session, list(batch_touched)
                        )
                        await self._mention_repo.update_alias_counters(
                            session, list(batch_touched)
                        )

                    await session.commit()
                else:
                    result.mentions_found += len(batch_mentions)
                    if result.dry_run_matches is not None and batch_previews:
                        result.dry_run_matches.extend(batch_previews)

                last_video_id = batch_rows[-1].video_id
                result.last_processed_video_id = last_video_id

                if progress_callback:
                    progress_callback(result.segments_scanned, result.mentions_found)
                if checkpoint_callback and not dry_run:
                    checkpoint_callback(last_video_id)

                # If dry-run and we have reached the limit, stop early
                if (
                    dry_run
                    and limit is not None
                    and result.dry_run_matches is not None
                    and len(result.dry_run_matches) >= limit
                ):
                    # Trim to limit
                    result.dry_run_matches = result.dry_run_matches[:limit]
                    break

                if should_continue is not None and not should_continue():
                    stopped_early = True
                    break

            result.unique_entities = len(matched_entity_ids)
            result.unique_videos = len(matched_video_ids)

            result.completed = exhausted and not stopped_early

            # Under --full, a COMPLETED metadata run recomputes counters for ALL
            # scoped entities (same rationale as scan()): zero entities that lost
            # every mention or carried a stale count.
            if full_rescan and not dry_run and result.completed and scoped_entity_ids:
                await self._mention_repo.update_entity_counters(
                    session, scoped_entity_ids
                )
                await self._mention_repo.update_alias_counters(
                    session, scoped_entity_ids
                )
                await session.commit()

            result.duration_seconds = time.monotonic() - t0

            logger.info(
                "Metadata scan complete: items_scanned=%d, mentions_found=%d, "
                "mentions_skipped=%d, unique_entities=%d, unique_videos=%d, "
                "duration=%.2fs, dry_run=%s, failed_batches=%d",
                result.segments_scanned,
                result.mentions_found,
                result.mentions_skipped,
                result.unique_entities,
                result.unique_videos,
                result.duration_seconds,
                result.dry_run,
                result.failed_batches,
            )

            return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _fetch_video_batch(
        self,
        session: AsyncSession,
        video_ids: list[str] | None,
        batch_size: int,
        after_video_id: str,
    ) -> list[Any]:
        """Fetch a batch of video rows for metadata scanning.

        Keyset-paginated on ``video_id`` for the same reason as
        :meth:`_fetch_segment_batch` — see that method for the measurements.
        The videos table is far smaller than transcript_segments, so the win
        here is small today; it is fixed alongside because it is the identical
        defect and grows the same way.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        video_ids : list[str] | None
            Optional video ID filter.
        batch_size : int
            Maximum videos per batch.
        after_video_id : str
            Exclusive lower bound on video_id; pass ``""`` to start. Ordering
            and seeking use the same collation, so the comparison agrees with
            the ORDER BY and no row is visited twice or skipped.

        Returns
        -------
        list[Any]
            List of Row objects with video_id, title, description, channel_id.
        """
        stmt: Select[tuple[Any, ...]] = select(
            VideoDB.video_id,
            VideoDB.title,
            VideoDB.description,
            VideoDB.channel_id,
        )

        if video_ids is not None:
            stmt = stmt.where(VideoDB.video_id.in_(video_ids))

        stmt = stmt.where(VideoDB.video_id > after_video_id)
        stmt = stmt.order_by(VideoDB.video_id.asc())
        stmt = stmt.limit(batch_size)

        result = await session.execute(stmt)
        return list(result.all())

    def _scan_metadata_batch(
        self,
        batch_rows: list[Any],
        compiled_patterns: list[tuple[_EntityPattern, re.Pattern[str]]],
        pattern_by_entity: dict[uuid.UUID, _EntityPattern],
        sources: list[str],
        dry_run: bool,
        write_scope: set[uuid.UUID] | None = None,
    ) -> tuple[list[EntityMentionCreate], list[dict[str, Any]]]:
        """Scan a batch of video rows against entity patterns for title/description.

        Parameters
        ----------
        batch_rows : list[Any]
            Video rows from ``_fetch_video_batch``.
        compiled_patterns : list[tuple[_EntityPattern, re.Pattern[str]]]
            Pre-compiled entity patterns.
        pattern_by_entity : dict[uuid.UUID, _EntityPattern]
            Lookup from entity_id to pattern (for exclusion patterns).
        sources : list[str]
            Which metadata fields to scan (``"title"``, ``"description"``).
        dry_run : bool
            Whether this is a dry-run.
        write_scope : set[uuid.UUID] | None
            NOTE 020 §2. When the caller widened ``compiled_patterns`` to
            shared-token neighbours so cross-entity longest-match-wins could
            arbitrate, this is the set of entity ids the scan actually WRITES
            for; neighbour matches are dropped after arbitration/exclusion.
            ``None`` (an unscoped scan) matches and writes every pattern.

        Returns
        -------
        tuple[list[EntityMentionCreate], list[dict[str, Any]]]
            (new_mentions, preview_data)
        """
        new_mentions: list[EntityMentionCreate] = []
        preview_data: list[dict[str, Any]] = []

        for row in batch_rows:
            if "title" in sources and row.title:
                title_mentions, title_previews = self._match_text_for_video(
                    video_id=row.video_id,
                    text=row.title,
                    mention_source=MentionSource.TITLE,
                    compiled_patterns=compiled_patterns,
                    pattern_by_entity=pattern_by_entity,
                    dry_run=dry_run,
                    write_scope=write_scope,
                )
                new_mentions.extend(title_mentions)
                preview_data.extend(title_previews)

            if "description" in sources and row.description:
                desc_mentions, desc_previews = self._match_text_for_video(
                    video_id=row.video_id,
                    text=row.description,
                    mention_source=MentionSource.DESCRIPTION,
                    compiled_patterns=compiled_patterns,
                    pattern_by_entity=pattern_by_entity,
                    dry_run=dry_run,
                    write_scope=write_scope,
                )
                new_mentions.extend(desc_mentions)
                preview_data.extend(desc_previews)

        return new_mentions, preview_data

    def _match_text_for_video(
        self,
        video_id: str,
        text: str,
        mention_source: MentionSource,
        compiled_patterns: list[tuple[_EntityPattern, re.Pattern[str]]],
        pattern_by_entity: dict[uuid.UUID, _EntityPattern],
        dry_run: bool,
        write_scope: set[uuid.UUID] | None = None,
    ) -> tuple[list[EntityMentionCreate], list[dict[str, Any]]]:
        """Match entity patterns against a text field for a single video.

        Applies longest-match-wins and exclusion pattern filtering, then
        creates mention rows.  For title mentions, only the first match
        per entity is kept (deduplication by entity_id).

        Parameters
        ----------
        video_id : str
            YouTube video ID.
        text : str
            The text to scan (title or description).
        mention_source : MentionSource
            Source type for the created mentions.
        compiled_patterns : list[tuple[_EntityPattern, re.Pattern[str]]]
            Pre-compiled entity patterns.
        pattern_by_entity : dict[uuid.UUID, _EntityPattern]
            Lookup from entity_id to pattern (for exclusion patterns).
        dry_run : bool
            Whether this is a dry-run.
        write_scope : set[uuid.UUID] | None
            NOTE 020 §2. When ``compiled_patterns`` was widened to shared-token
            neighbours purely so longest-match-wins could arbitrate, this is
            the set of entity ids the scan actually WRITES for. Neighbour
            matches are dropped AFTER arbitration/exclusion but BEFORE dedup,
            mention building, and the preview — so they neither reach a mention
            row nor consume a dry-run preview slot. ``None`` writes every match.

        Returns
        -------
        tuple[list[EntityMentionCreate], list[dict[str, Any]]]
            (new_mentions, preview_data)
        """
        mentions: list[EntityMentionCreate] = []
        previews: list[dict[str, Any]] = []

        # Step 1: Collect all matches.  Matching runs against the diacritic-
        # folded text and each folded match is mapped back to RAW offsets so the
        # stored mention_text keeps its accents and offsets point into ``text``.
        folded_text, offset_map = _fold_diacritics(text)
        raw_matches: list[tuple[uuid.UUID, int, int, str, _EntityPattern]] = []
        for pattern, py_regex in compiled_patterns:
            for match in py_regex.finditer(folded_text):
                f_start, f_end = match.start(), match.end()
                if f_end <= f_start:
                    continue
                raw_start = offset_map[f_start]
                raw_end = offset_map[f_end - 1] + 1
                raw_matches.append(
                    (
                        pattern.entity_id,
                        raw_start,
                        raw_end,
                        text[raw_start:raw_end],
                        pattern,
                    )
                )

        # Feature 111 US3 (FR-010): additively add disfluency-gap matches the
        # contiguous regex missed. Title/description carry no language, so only
        # the language-independent false-start / repeat tolerances apply here.
        raw_matches.extend(
            self._collect_gap_matches(
                folded_text,
                offset_map,
                text,
                [p for p, _ in compiled_patterns],
                None,
            )
        )

        if not raw_matches:
            return mentions, previews

        # Step 2: Longest-match-wins disambiguation
        # Create a minimal row-like object for logging
        _row = type("_Row", (), {"id": video_id})()
        surviving_matches, _ = self._apply_longest_match_wins(
            raw_matches, _row, dry_run
        )

        # Step 3: Exclusion pattern filtering
        final_matches, _ = self._apply_exclusion_patterns(
            surviving_matches, text, pattern_by_entity, _row, dry_run
        )

        # NOTE 020 §2: the MATCH set may include shared-token neighbours loaded
        # only so longest-match-wins could arbitrate against them. Their matches
        # survived arbitration above but are OUT of the write scope — drop them
        # here, before dedup/mention/preview build, so they never reach a row or
        # consume the dry-run preview cap. A neighbour that WON arbitration
        # simply produces no row for this (scoped) scan, the correct outcome.
        if write_scope is not None:
            final_matches = [m for m in final_matches if m[0] in write_scope]

        if not final_matches:
            return mentions, previews

        # Step 4: Deduplicate — for title, one mention per entity per video
        seen_entities: set[uuid.UUID] = set()
        for entity_id, m_start, m_end, matched_text, pat in final_matches:
            if mention_source == MentionSource.TITLE:
                if entity_id in seen_entities:
                    continue
                seen_entities.add(entity_id)

            # Context is the evidence a reviewer judges a match by, so every
            # source stores it — not only description. `text` is the raw
            # (unfolded) source and m_start/m_end are already mapped back to
            # raw offsets above, so the snippet reads as it was written.
            context = self._extract_context_snippet(text, m_start, m_end)

            fold_key = _fold_diacritics(matched_text)[0].casefold()
            mention = EntityMentionCreate(
                entity_id=entity_id,
                segment_id=None,
                video_id=video_id,
                language_code=None,
                mention_text=matched_text,
                detection_method=(
                    DetectionMethod.ASR_MATCH
                    if fold_key in pat.asr_folds
                    else DetectionMethod.RULE_MATCH
                ),
                confidence=1.0,
                match_start=m_start,
                match_end=m_end,
                mention_source=mention_source,
                mention_context=context,
                alias_id=pat.alias_id_by_fold.get(fold_key),
            )
            mentions.append(mention)

            if dry_run:
                preview_context = context or (text[:120] if len(text) > 120 else text)
                previews.append(
                    {
                        "video_id": video_id,
                        "segment_id": None,
                        "start_time": None,
                        "entity_name": pat.canonical_name,
                        "entity_type": pat.entity_type,
                        "matched_text": matched_text,
                        "match_start": m_start,
                        "match_end": m_end,
                        "context": preview_context,
                        "source": mention_source.value,
                    }
                )

        return mentions, previews

    @staticmethod
    def _extract_context_snippet(
        text: str, match_start: int, match_end: int, window: int = 75
    ) -> str:
        """Extract a context snippet around a match position.

        Returns approximately ``window`` characters before and after the
        match, with ellipsis (``...``) added if the snippet is truncated
        at either end.

        Parameters
        ----------
        text : str
            The full text containing the match.
        match_start : int
            Start position of the match.
        match_end : int
            End position of the match.
        window : int
            Number of characters of context before and after the match
            (default 75).

        Returns
        -------
        str
            The context snippet with optional leading/trailing ellipsis.
        """
        snippet_start = max(0, match_start - window)
        snippet_end = min(len(text), match_end + window)

        snippet = text[snippet_start:snippet_end]

        if snippet_start > 0:
            snippet = "..." + snippet
        if snippet_end < len(text):
            snippet = snippet + "..."

        return snippet

    async def _shared_token_neighbour_ids(
        self,
        session: AsyncSession,
        scope_patterns: list[_EntityPattern],
    ) -> set[uuid.UUID]:
        """Active entities sharing a whole name-token with the scoped entities.

        NOTE 020 §5. Entity patterns compile word-boundary-anchored on both ends
        (``re.compile(r"\\b(" + pattern + r")\\b")``), so the overlap region of
        any two matches is one or more WHOLE tokens; two entities can therefore
        produce overlapping matches **iff their names share at least one token**.
        That makes shared-token — not containment — the exact relation the scoped
        MATCH set must be widened by so cross-entity longest-match-wins can
        arbitrate (§2). Containment is a strict special case: a containment-only
        widening would structurally miss the partial-overlap class (two names
        sharing only a middle token, neither containing the other).

        Tokens are computed with the SAME fold the matcher uses
        (``_tokens(form)``) over each
        entity's canonical name and its non-``asr_error`` aliases. Returns the ids
        of active entities OUTSIDE the scope whose tokens intersect the scope's
        tokens; the scope entities themselves are excluded.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        scope_patterns : list[_EntityPattern]
            The patterns for the write-scoped entities.

        Returns
        -------
        set[uuid.UUID]
            Ids of shared-token neighbour entities (excluding the scope).
        """
        scope_ids = {p.entity_id for p in scope_patterns}

        scope_tokens: set[str] = set()
        for pattern in scope_patterns:
            for form in (pattern.canonical_name, *pattern.alias_names):
                scope_tokens.update(_tokens(form))
        if not scope_tokens:
            return set()

        # Load every active entity's canonical name, then its non-asr aliases —
        # the same two-query shape as _load_entity_patterns.
        entity_rows = (
            await session.execute(
                select(NamedEntityDB.id, NamedEntityDB.canonical_name).where(
                    NamedEntityDB.status == "active"
                )
            )
        ).all()
        forms_by_entity: dict[uuid.UUID, list[str]] = {}
        for entity_row in entity_rows:
            forms_by_entity.setdefault(entity_row.id, []).append(
                entity_row.canonical_name
            )

        active_ids = list(forms_by_entity.keys())
        if active_ids:
            alias_rows = (
                await session.execute(
                    select(EntityAliasDB.entity_id, EntityAliasDB.alias_name).where(
                        EntityAliasDB.entity_id.in_(active_ids),
                    )
                )
            ).all()
            for alias_row in alias_rows:
                forms_by_entity.setdefault(alias_row.entity_id, []).append(
                    alias_row.alias_name
                )

        neighbours: set[uuid.UUID] = set()
        for entity_id, forms in forms_by_entity.items():
            if entity_id in scope_ids:
                continue
            tokens: set[str] = set()
            for form in forms:
                tokens.update(_tokens(form))
            if tokens & scope_tokens:
                neighbours.add(entity_id)
        return neighbours

    async def _load_entity_patterns(
        self,
        session: AsyncSession,
        entity_type: str | None,
        new_entities_only: bool,
        entity_ids: list[uuid.UUID] | None = None,
    ) -> list[_EntityPattern]:
        """Load active entities and their aliases, build regex patterns.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        entity_type : str | None
            Optional entity type filter.
        new_entities_only : bool
            If True, only include entities with zero existing mentions.
        entity_ids : list[uuid.UUID] | None
            Optional list of specific entity IDs to restrict to.  Applied as
            an AND filter together with ``entity_type``.

        Returns
        -------
        list[_EntityPattern]
            List of entity pattern objects ready for matching.
        """
        # Determine which entity IDs to scan
        if new_entities_only:
            zero_mention_ids = await self._mention_repo.get_entities_with_zero_mentions(
                session, entity_type=entity_type
            )
            if not zero_mention_ids:
                return []
            entity_stmt = select(NamedEntityDB).where(
                NamedEntityDB.id.in_(zero_mention_ids)
            )
            if entity_ids is not None:
                entity_stmt = entity_stmt.where(NamedEntityDB.id.in_(entity_ids))
        else:
            entity_stmt = select(NamedEntityDB).where(NamedEntityDB.status == "active")
            if entity_type is not None:
                entity_stmt = entity_stmt.where(
                    NamedEntityDB.entity_type == entity_type
                )
            if entity_ids is not None:
                entity_stmt = entity_stmt.where(NamedEntityDB.id.in_(entity_ids))

        entity_result = await session.execute(entity_stmt)
        entities = list(entity_result.scalars().all())

        if not entities:
            return []

        # Load all aliases for these entities in a single query. ASR-error strings
        # are no longer in entity_aliases (Feature 110 relocated them to their own
        # store), so the name store holds only names and needs no per-reader filter.
        entity_id_list = [e.id for e in entities]
        alias_stmt = select(EntityAliasDB).where(
            EntityAliasDB.entity_id.in_(entity_id_list),
        )
        alias_result = await session.execute(alias_stmt)
        all_aliases = list(alias_result.scalars().all())

        # Load registered ASR-error forms for these entities (Feature 111 US1b).
        # Keyed by str to sidestep the uuid_utils/stdlib UUID equality boundary:
        # entity.id may be a uuid_utils value held in the identity map while the
        # query column round-trips as a stdlib UUID, and the two are unequal.
        asr_forms_by_entity = (
            await self._asr_error_repo.get_multiword_forms_by_entity_ids(
                session, entity_id_list
            )
        )
        asr_forms_by_str = {str(k): v for k, v in asr_forms_by_entity.items()}

        # Group aliases by entity_id, carrying each alias's id (#298 provenance)
        # and case-sensitivity.
        alias_map: dict[uuid.UUID, list[tuple[uuid.UUID, str, bool]]] = {}
        for alias in all_aliases:
            alias_map.setdefault(alias.entity_id, []).append(
                (alias.id, alias.alias_name, bool(alias.case_sensitive))
            )

        patterns: list[_EntityPattern] = []
        for entity in entities:
            names: list[str] = []
            # Names matched only at their exact casing (#177). The canonical
            # name is never here — it is not an alias and has no flag to set.
            case_sensitive_names: set[str] = set()

            # Add canonical name
            names.append(entity.canonical_name)

            # Add aliases (may include canonical name again, dedup below)
            entity_aliases = alias_map.get(entity.id, [])
            for _alias_id, alias_name, alias_cs in entity_aliases:
                if alias_name not in names:
                    names.append(alias_name)
                if alias_cs:
                    case_sensitive_names.add(alias_name)

            # Provenance map (#298): folded alias name -> id, unambiguous folds
            # only. Spans whose fold maps to >1 alias are indistinguishable to
            # the matcher, so they are omitted and record NULL.
            # casefold on top of the diacritic fold: detection is
            # case-insensitive (re.IGNORECASE), so attribution must be too, or a
            # lowercase transcript match of a capitalized alias would record no
            # link. (Two aliases differing only in case can't coexist —
            # alias_name_normalized is already lowercased — so this adds no new
            # collision.)
            fold_to_ids: dict[str, list[uuid.UUID]] = {}
            for a_id, a_name, _cs in entity_aliases:
                folded_name = _fold_diacritics(a_name)[0].casefold()
                if folded_name:
                    fold_to_ids.setdefault(folded_name, []).append(a_id)
            alias_id_by_fold = {
                f: ids[0] for f, ids in fold_to_ids.items() if len(ids) == 1
            }

            # Warn about short aliases
            for name in names:
                if len(name) < _MIN_ALIAS_LENGTH:
                    logger.warning(
                        "Entity %s (%s) has alias shorter than %d chars: '%s'",
                        entity.canonical_name,
                        entity.id,
                        _MIN_ALIAS_LENGTH,
                        name,
                    )

            # Registered ASR-error forms for this entity, filtered through the
            # admissibility gate (Feature 111 US1b). Single-word forms are already
            # excluded by the multiword SQL filter; the gate re-checks and also
            # drops one-char-token and all-common forms — defence in depth.
            admissible_asr_forms = [
                form
                for form in asr_forms_by_str.get(str(entity.id), [])
                if _asr_form_admissible(form)
            ]

            # Build the folded alias alternation + the _EntityPattern via the single
            # shared builder (module-level `_build_entity_pattern`), so DB loading and
            # candidate-discovery grounding construct the match pattern identically.
            patterns.append(
                _build_entity_pattern(
                    entity_id=entity.id,
                    canonical_name=entity.canonical_name,
                    entity_type=entity.entity_type,
                    names=names,
                    case_sensitive_names=case_sensitive_names,
                    exclusion_patterns=list(entity.exclusion_patterns or []),
                    alias_id_by_fold=alias_id_by_fold,
                    asr_forms=admissible_asr_forms,
                )
            )

        logger.info(
            "Loaded %d entity patterns (%d total aliases)",
            len(patterns),
            sum(len(p.alias_names) for p in patterns),
        )
        return patterns

    async def _fetch_segment_batch(
        self,
        session: AsyncSession,
        video_ids: list[str] | None,
        language_code: str | None,
        batch_size: int,
        after_id: int,
    ) -> list[Any]:
        """Fetch a batch of transcript segments with effective text.

        Paginates by primary key (``id > after_id``) rather than by ``OFFSET``.
        ``OFFSET n`` makes PostgreSQL walk and discard n rows to reach each
        window, so per-batch cost grows with depth and total scan cost grows
        with the *square* of the corpus.  Measured on a 1.9M-segment corpus,
        the same 500 rows took 11 ms at offset 0 and 531 ms at offset 1.8M.
        Seeking on the indexed key holds every batch at the offset-0 price.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        video_ids : list[str] | None
            Optional video ID filter.
        language_code : str | None
            Optional language filter.
        batch_size : int
            Maximum segments per batch.
        after_id : int
            Exclusive lower bound on segment id; pass 0 to start. Ids are a
            monotonic sequence, so ordering by id and seeking past the last id
            of the previous batch visits every row exactly once.

        Returns
        -------
        list[Any]
            List of Row objects with id, video_id, language_code, start_time,
            effective_text.
        """
        stmt: Select[tuple[Any, ...]] = select(
            TranscriptSegmentDB.id,
            TranscriptSegmentDB.video_id,
            TranscriptSegmentDB.language_code,
            TranscriptSegmentDB.start_time,
            literal_column(
                "CASE WHEN transcript_segments.has_correction "
                "THEN transcript_segments.corrected_text "
                "ELSE transcript_segments.text END"
            ).label("effective_text"),
        ).where(
            # Exclude segments with empty corrected text
            text(
                "NOT (transcript_segments.has_correction = TRUE "
                "AND (transcript_segments.corrected_text IS NULL "
                "OR transcript_segments.corrected_text = ''))"
            )
        )

        if video_ids is not None:
            stmt = stmt.where(TranscriptSegmentDB.video_id.in_(video_ids))
        if language_code is not None:
            stmt = stmt.where(TranscriptSegmentDB.language_code == language_code)

        stmt = stmt.where(TranscriptSegmentDB.id > after_id)
        stmt = stmt.order_by(TranscriptSegmentDB.id.asc())
        stmt = stmt.limit(batch_size)

        result = await session.execute(stmt)
        return list(result.all())

    async def _scan_batch(
        self,
        session: AsyncSession,
        batch_rows: list[Any],
        patterns: list[_EntityPattern],
        full_rescan: bool,
        dry_run: bool,
        limit: int | None,
        current_preview_count: int,
        write_scope: set[uuid.UUID] | None = None,
    ) -> tuple[list[EntityMentionCreate], int, list[dict[str, Any]], int, int]:
        """Scan a batch of segments against all entity patterns.

        For each segment, all entity patterns are matched via ``finditer()``
        to collect every occurrence.  Matches are then disambiguated with
        longest-match-wins and filtered through exclusion patterns before
        mention rows are created.

        Parameters
        ----------
        session : AsyncSession
            Database session.
        batch_rows : list[Any]
            Segment rows from ``_fetch_segment_batch``.
        patterns : list[_EntityPattern]
            Entity patterns to match against.
        full_rescan : bool
            Whether this is a full rescan (skip dedup check).
        dry_run : bool
            Whether this is a dry-run.
        limit : int | None
            Dry-run preview limit.
        current_preview_count : int
            Number of preview rows already collected.
        write_scope : set[uuid.UUID] | None
            NOTE 020 §2. When the caller widened ``patterns`` to shared-token
            neighbours so cross-entity longest-match-wins could arbitrate, this
            is the set of entity ids the scan actually WRITES for. Neighbour
            matches are dropped AFTER arbitration/exclusion but BEFORE dedup,
            counter accounting, and mention/preview building — so they never
            inflate ``*_skips``, trigger a dedup query, or consume the preview
            cap. ``None`` (an unscoped scan) matches and writes every pattern.

        Returns
        -------
        tuple[list[EntityMentionCreate], int, list[dict], int, int]
            (new_mentions, skipped_count, preview_data,
             longest_match_skips, exclusion_pattern_skips)
        """
        new_mentions: list[EntityMentionCreate] = []
        skipped = 0
        preview_data: list[dict[str, Any]] = []
        longest_match_skips = 0
        exclusion_pattern_skips = 0

        # Pre-compile all Python regexes
        compiled_patterns: list[tuple[_EntityPattern, re.Pattern[str]]] = []
        for pattern in patterns:
            try:
                py_regex = _compile_entity_regex(pattern)
                compiled_patterns.append((pattern, py_regex))
            except re.error:
                logger.warning(
                    "Failed to compile regex for entity %s (%s), skipping",
                    pattern.canonical_name,
                    pattern.entity_id,
                )

        # Build a lookup from entity_id to pattern (for exclusion patterns)
        pattern_by_entity: dict[uuid.UUID, _EntityPattern] = {
            p.entity_id: p for p in patterns
        }

        for row in batch_rows:
            effective_text = row.effective_text
            if not effective_text:
                continue

            # ----------------------------------------------------------
            # Step 1: Collect ALL (entity_id, start, end, text) via finditer.
            # Matching runs against the diacritic-folded text so accented
            # occurrences match accent-free aliases; each folded match is then
            # mapped back to RAW offsets so match_start/match_end/mention_text
            # reference the real (accented) segment text.
            # ----------------------------------------------------------
            folded_text, offset_map = _fold_diacritics(effective_text)
            raw_matches: list[tuple[uuid.UUID, int, int, str, _EntityPattern]] = []
            for pattern, py_regex in compiled_patterns:
                for match in py_regex.finditer(folded_text):
                    f_start, f_end = match.start(), match.end()
                    if f_end <= f_start:
                        continue
                    raw_start = offset_map[f_start]
                    raw_end = offset_map[f_end - 1] + 1
                    raw_matches.append(
                        (
                            pattern.entity_id,
                            raw_start,
                            raw_end,
                            effective_text[raw_start:raw_end],
                            pattern,
                        )
                    )

            # Feature 111 US3 (FR-010): additively add disfluency-gap matches the
            # contiguous regex missed, scoped to the same candidate patterns.
            raw_matches.extend(
                self._collect_gap_matches(
                    folded_text,
                    offset_map,
                    effective_text,
                    patterns,
                    row.language_code,
                )
            )

            if not raw_matches:
                continue

            # ----------------------------------------------------------
            # Step 2: Longest-match-wins disambiguation
            # ----------------------------------------------------------
            surviving_matches, lmw_skips = self._apply_longest_match_wins(
                raw_matches, row, dry_run
            )
            longest_match_skips += lmw_skips

            # ----------------------------------------------------------
            # Step 3: Exclusion pattern filtering
            # ----------------------------------------------------------
            final_matches, ep_skips = self._apply_exclusion_patterns(
                surviving_matches, effective_text, pattern_by_entity, row, dry_run
            )
            exclusion_pattern_skips += ep_skips

            # NOTE 020 §2: the MATCH set may include shared-token neighbours loaded
            # only so longest-match-wins could arbitrate against them. Their matches
            # survived arbitration above but are OUT of the write scope — drop them
            # here, before dedup/counters/previews, so they neither count as skips
            # nor consume the preview cap. A neighbour that WON arbitration simply
            # produces no row for this (scoped) scan, which is the correct outcome.
            if write_scope is not None:
                final_matches = [m for m in final_matches if m[0] in write_scope]

            if not final_matches:
                continue

            # ----------------------------------------------------------
            # Step 4: Incremental dedup check
            # ----------------------------------------------------------
            if not full_rescan:
                entity_ids_in_segment = list(
                    {entity_id for entity_id, _, _, _, _ in final_matches}
                )
                existing_stmt = select(
                    EntityMentionDB.segment_id,
                    EntityMentionDB.entity_id,
                ).where(
                    EntityMentionDB.segment_id == row.id,
                    EntityMentionDB.entity_id.in_(entity_ids_in_segment),
                )
                existing_result = await session.execute(existing_stmt)
                existing_pairs = {
                    (r.segment_id, r.entity_id) for r in existing_result.all()
                }
            else:
                existing_pairs = set()

            # ----------------------------------------------------------
            # Step 5: Create mentions from surviving matches
            # ----------------------------------------------------------
            for entity_id, m_start, m_end, matched_text, pat in final_matches:
                if (row.id, entity_id) in existing_pairs:
                    skipped += 1
                    continue

                fold_key = _fold_diacritics(matched_text)[0].casefold()
                mention = EntityMentionCreate(
                    entity_id=entity_id,
                    segment_id=row.id,
                    video_id=row.video_id,
                    language_code=row.language_code,
                    mention_text=matched_text,
                    detection_method=(
                        DetectionMethod.ASR_MATCH
                        if fold_key in pat.asr_folds
                        else DetectionMethod.RULE_MATCH
                    ),
                    confidence=1.0,
                    match_start=m_start,
                    match_end=m_end,
                    # A transcript mention is recoverable via segment_id, but
                    # only by joining and re-slicing by offset. Storing the
                    # snippet is what makes a match reviewable in place — and
                    # transcript is the largest source by a wide margin.
                    mention_context=self._extract_context_snippet(
                        effective_text, m_start, m_end
                    ),
                    alias_id=pat.alias_id_by_fold.get(fold_key),
                )
                new_mentions.append(mention)

                if dry_run:
                    if (
                        limit is None
                        or (current_preview_count + len(preview_data)) < limit
                    ):
                        context = (
                            effective_text[:120]
                            if len(effective_text) > 120
                            else effective_text
                        )
                        preview_data.append(
                            {
                                "video_id": row.video_id,
                                "segment_id": row.id,
                                "start_time": row.start_time,
                                "entity_name": pat.canonical_name,
                                "entity_type": pat.entity_type,
                                "matched_text": matched_text,
                                "match_start": m_start,
                                "match_end": m_end,
                                "context": context,
                            }
                        )

                logger.debug(
                    "Match: entity=%s, segment_id=%d, video_id=%s, "
                    "text='%s', pos=%d-%d",
                    pat.canonical_name,
                    row.id,
                    row.video_id,
                    matched_text,
                    m_start,
                    m_end,
                )

        return (
            new_mentions,
            skipped,
            preview_data,
            longest_match_skips,
            exclusion_pattern_skips,
        )

    # ------------------------------------------------------------------
    # Disambiguation & filtering helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _collect_gap_matches(
        folded_text: str,
        offset_map: list[int],
        raw_text: str,
        patterns: list[_EntityPattern],
        language: str | None,
    ) -> list[tuple[uuid.UUID, int, int, str, _EntityPattern]]:
        """Additively detect names interrupted by a bounded disfluency gap.

        Feature 111 US3 (FR-010). The ``\\b``-anchored entity regex matches only
        contiguous occurrences; this pass adds the spans it misses -- a name whose
        adjacent tokens are separated by a single interrupting token (a filler
        word, a false-start prefix of the following token, or a repeat of the
        preceding token), or by an enumerated multi-word filler phrase. It is
        purely additive: only matches that actually used a gap are emitted (see
        :func:`_find_gap_spans`), so a name that already matches contiguously is
        left entirely to the regex and this pass changes nothing for it.

        The scan runs over ``patterns`` ONLY -- the caller passes the segment's
        pre-filtered candidate set (the same scope the regex iterates), never the
        whole entity universe -- so the gap pass inherits the candidate pre-filter
        for free. The transcript is never modified: a gap span is sliced out of
        ``raw_text`` for its ``mention_text`` (so it reads as written, filler
        included), and no stored name/alias/ASR form ever gains the filler.

        Spans are found in fold space (token boundaries from :data:`_TOKEN_RE`
        over ``folded_text``) and mapped back to raw offsets via ``offset_map``,
        exactly as the regex match sites do, so the emitted ``(start, end)`` is a
        correct raw span covering the gap. Each tuple is shaped like a regex
        ``raw_matches`` entry so longest-match-wins arbitration dedupes and ranks
        it identically -- preferring the longer (gap-spanning or contiguous) match
        on overlap.

        Parameters
        ----------
        folded_text : str
            The diacritic-folded segment text (the matcher's working space).
        offset_map : list[int]
            Fold-position -> raw-index map from :func:`_fold_diacritics`.
        raw_text : str
            The original segment text, for slicing ``mention_text``.
        patterns : list[_EntityPattern]
            The segment's candidate entity patterns (already pre-filtered).
        language : str | None
            The segment's language code, selecting the filler set.

        Returns
        -------
        list[tuple[uuid.UUID, int, int, str, _EntityPattern]]
            Gap-match tuples ``(entity_id, raw_start, raw_end, matched_text,
            pattern)``, deduplicated by ``(entity_id, raw_start, raw_end)``.
        """
        filler_tokens = _filler_tokens_for_language(language)
        max_filler_len = max((len(t) for t in filler_tokens), default=1)

        # Tokenise the folded text once, keeping each token's fold-space span.
        seg_tokens: list[str] = []
        tok_spans: list[tuple[int, int]] = []
        for match in _TOKEN_RE.finditer(folded_text):
            seg_tokens.append(match.group(0).casefold())
            tok_spans.append((match.start(), match.end()))
        if not seg_tokens:
            return []

        results: list[tuple[uuid.UUID, int, int, str, _EntityPattern]] = []
        seen: set[tuple[uuid.UUID, int, int]] = set()
        for pattern in patterns:
            # ``gap_form_seqs`` is precomputed and cached per pattern (a pure
            # function of the entity's names/ASR folds) -- hoisted out of this
            # per-segment loop; see _EntityPattern.gap_form_seqs.
            for form_tokens in pattern.gap_form_seqs:
                for start_idx, end_idx in _find_gap_spans(
                    seg_tokens, form_tokens, filler_tokens, max_filler_len
                ):
                    f_start = tok_spans[start_idx][0]
                    f_end = tok_spans[end_idx][1]
                    raw_start = offset_map[f_start]
                    raw_end = offset_map[f_end - 1] + 1
                    key = (pattern.entity_id, raw_start, raw_end)
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append(
                        (
                            pattern.entity_id,
                            raw_start,
                            raw_end,
                            raw_text[raw_start:raw_end],
                            pattern,
                        )
                    )
        return results

    @staticmethod
    def _apply_longest_match_wins(
        raw_matches: list[tuple[uuid.UUID, int, int, str, _EntityPattern]],
        row: Any,
        dry_run: bool,
    ) -> tuple[list[tuple[uuid.UUID, int, int, str, _EntityPattern]], int]:
        """Disambiguate overlapping matches using longest-match-wins.

        Parameters
        ----------
        raw_matches : list[tuple]
            All ``(entity_id, start, end, text, pattern)`` tuples for one segment.
        row : Any
            The segment row (used for logging).
        dry_run : bool
            Whether this is a dry-run.

        Returns
        -------
        tuple[list[tuple], int]
            (surviving_matches, skip_count)
        """
        # Sort by length descending, then start ascending for stability
        sorted_matches = sorted(
            raw_matches,
            key=lambda m: (-(m[2] - m[1]), m[1]),
        )

        # Store claimed intervals as (start, end) tuples for O(k) overlap checks
        # where k = number of claimed intervals, avoiding O(n) set operations on
        # character positions.
        claimed_intervals: list[tuple[int, int]] = []
        surviving: list[tuple[uuid.UUID, int, int, str, _EntityPattern]] = []
        skip_count = 0

        for entity_id, m_start, m_end, matched_text, pattern in sorted_matches:
            # Check overlap against all claimed intervals
            overlaps = any(
                c_start < m_end and c_end > m_start
                for c_start, c_end in claimed_intervals
            )
            if overlaps:
                skip_count += 1
                if dry_run:
                    logger.info(
                        '[DRY RUN] Segment %d: "%s" → SKIPPED '
                        "(longest-match-wins: overlapping longer match preferred)",
                        row.id,
                        matched_text,
                    )
                else:
                    logger.debug(
                        'Segment %d: "%s" skipped (longest-match-wins)',
                        row.id,
                        matched_text,
                    )
                continue

            claimed_intervals.append((m_start, m_end))
            surviving.append((entity_id, m_start, m_end, matched_text, pattern))

        return surviving, skip_count

    @staticmethod
    def _apply_exclusion_patterns(
        matches: list[tuple[uuid.UUID, int, int, str, _EntityPattern]],
        segment_text: str,
        pattern_by_entity: dict[uuid.UUID, _EntityPattern],
        row: Any,
        dry_run: bool,
    ) -> tuple[list[tuple[uuid.UUID, int, int, str, _EntityPattern]], int]:
        """Filter matches against entity exclusion patterns.

        For each surviving match, check if any of the entity's exclusion
        patterns overlap the match position in the segment text.  Exclusion
        matching is folded the same way as entity matching (accents stripped,
        case-insensitive) and exclusion offsets are mapped back to the RAW
        segment text, so overlap is compared in a single, consistent RAW offset
        space against the (already RAW) match offsets.

        Parameters
        ----------
        matches : list[tuple]
            Surviving matches after longest-match-wins.
        segment_text : str
            The full effective text of the segment.
        pattern_by_entity : dict
            Lookup from entity_id to ``_EntityPattern``.
        row : Any
            The segment row (used for logging).
        dry_run : bool
            Whether this is a dry-run.

        Returns
        -------
        tuple[list[tuple], int]
            (final_matches, skip_count)
        """
        final: list[tuple[uuid.UUID, int, int, str, _EntityPattern]] = []
        skip_count = 0

        # Fold the segment text once; exclusion matches are found in folded
        # space and mapped back to RAW offsets to compare against RAW match
        # offsets.
        folded_text, offset_map = _fold_diacritics(segment_text)

        for entity_id, m_start, m_end, matched_text, pattern in matches:
            ep = pattern_by_entity.get(entity_id)
            exclusions = ep.exclusion_patterns if ep else []

            suppressed = False
            for excl_pattern_text in exclusions:
                # Find all accent- and case-insensitive occurrences of the
                # exclusion pattern in the folded segment text.
                folded_excl = _fold_diacritics(excl_pattern_text)[0]
                if not folded_excl:
                    continue
                try:
                    excl_regex = re.compile(re.escape(folded_excl), re.IGNORECASE)
                except re.error:
                    logger.warning(
                        "Invalid exclusion pattern '%s' for entity %s, skipping",
                        excl_pattern_text,
                        entity_id,
                    )
                    continue

                for excl_match in excl_regex.finditer(folded_text):
                    f_start, f_end = excl_match.start(), excl_match.end()
                    if f_end <= f_start:
                        continue
                    pattern_start = offset_map[f_start]
                    pattern_end = offset_map[f_end - 1] + 1
                    # Overlap check: pattern_start < match_end AND pattern_end > match_start
                    if pattern_start < m_end and pattern_end > m_start:
                        suppressed = True
                        skip_count += 1
                        if dry_run:
                            logger.info(
                                '[DRY RUN] Segment %d: "%s" at %d-%d → SKIPPED '
                                '(exclusion pattern: "%s")',
                                row.id,
                                matched_text,
                                m_start,
                                m_end,
                                excl_pattern_text,
                            )
                        else:
                            logger.debug(
                                'Segment %d: "%s" at %d-%d suppressed by '
                                'exclusion pattern "%s"',
                                row.id,
                                matched_text,
                                m_start,
                                m_end,
                                excl_pattern_text,
                            )
                        break  # One overlap is enough to suppress
                if suppressed:
                    break

            if not suppressed:
                final.append((entity_id, m_start, m_end, matched_text, pattern))

        return final, skip_count


__all__ = ["EntityMentionScanService", "ScanResult"]
