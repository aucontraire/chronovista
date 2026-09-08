"""Persisted resume state for the entity-mention scan CLI (#291).

The scan service is stateless: it accepts a start cursor (`resume_from` /
`resume_from_video_id`) and reports the committed cursor per batch via a
checkpoint callback. This module is the CLI-side durable store that turns those
into `--resume`: a small JSON file under ``settings.data_dir`` mapping a
**scan scope** (the parameters that define a run) to a **per-source** keyset
position. It is written per committed batch, so the saved cursor is never ahead
of durable data, and it is cleared when a scope completes.

No database, no migration — resume is a CLI concern (FR-004/FR-013/FR-014).
A missing/unreadable/corrupt file is treated as "no saved position": the scan
starts fresh with a warning, never crashing and never resuming from a bad
position (spec Edge Cases).
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from pydantic import BaseModel, ValidationError

from chronovista.config.settings import settings

logger = logging.getLogger(__name__)

_STATE_FILENAME = "scan_resume_state.json"


class SourcePosition(BaseModel):
    """Resume position for one source type within a scope."""

    cursor: str  # transcript: last committed segment id (as str); metadata: video id
    completed: bool = False


class ScopeState(BaseModel):
    """Per-source resume positions for one scan scope."""

    sources: dict[str, SourcePosition] = {}


class ResumeStateFile(BaseModel):
    """The whole on-disk document: scope-key -> ScopeState."""

    scopes: dict[str, ScopeState] = {}


def compute_scope_key(
    *,
    sources: list[str],
    entity_type: str | None,
    entity_ids: list[str] | None,
    video_ids: list[str] | None,
    language: str | None,
    full: bool,
) -> str:
    """Return a stable key identifying a scan scope (FR-013).

    A re-run resumes only when its scope matches; a different scope gets a
    different key and so never resumes from an unrelated position.
    """
    payload = {
        "sources": sorted(sources),
        "entity_type": entity_type,
        "entity_ids": sorted(entity_ids) if entity_ids else None,
        "video_ids": sorted(video_ids) if video_ids else None,
        "language": language,
        "full": bool(full),
    }
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _state_path() -> Path:
    return Path(settings.data_dir) / _STATE_FILENAME


def _read_file() -> ResumeStateFile:
    """Load the state file; a missing/corrupt file yields an empty document."""
    path = _state_path()
    try:
        if not path.exists():
            return ResumeStateFile()
        return ResumeStateFile.model_validate_json(path.read_text())
    except (OSError, ValidationError, ValueError) as exc:
        logger.warning(
            "Scan resume-state file unreadable/corrupt (%s); treating as no saved "
            "position and starting fresh.",
            exc,
        )
        return ResumeStateFile()


def _write_file(doc: ResumeStateFile) -> None:
    path = _state_path()
    try:
        Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
        path.write_text(doc.model_dump_json())
    except OSError as exc:  # pragma: no cover - disk failure
        logger.warning("Could not write scan resume state (%s).", exc)


def read_position(scope_key: str, source: str) -> SourcePosition | None:
    """Return the saved position for ``source`` in ``scope_key`` (or None).

    A position marked ``completed`` returns None — there is nothing to resume.
    """
    scope = _read_file().scopes.get(scope_key)
    if scope is None:
        return None
    pos = scope.sources.get(source)
    if pos is None or pos.completed:
        return None
    return pos


def is_source_completed(scope_key: str, source: str) -> bool:
    """Return True if ``source`` in ``scope_key`` was recorded as completed.

    Lets a ``--resume`` skip a phase that already finished (e.g. transcript
    finished, metadata interrupted) instead of re-scanning it from scratch.
    """
    scope = _read_file().scopes.get(scope_key)
    if scope is None:
        return False
    pos = scope.sources.get(source)
    return pos is not None and pos.completed


def record_cursor(
    scope_key: str, source: str, cursor: str, *, completed: bool = False
) -> None:
    """Persist ``source``'s cursor for ``scope_key`` (called per committed batch).

    Written only after the batch's commit, so the saved position is never ahead
    of durable data (SEAM-1).
    """
    doc = _read_file()
    scope = doc.scopes.setdefault(scope_key, ScopeState())
    scope.sources[source] = SourcePosition(cursor=cursor, completed=completed)
    _write_file(doc)


def clear_scope_if_all_complete(scope_key: str, expected_sources: list[str]) -> None:
    """Remove the scope entry once every expected source is completed."""
    doc = _read_file()
    scope = doc.scopes.get(scope_key)
    if scope is None:
        return
    if all(
        scope.sources.get(s) is not None and scope.sources[s].completed
        for s in expected_sources
    ):
        doc.scopes.pop(scope_key, None)
        _write_file(doc)
