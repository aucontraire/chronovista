"""Fitness guard: every per-source salience column is refreshable (ADR 015 D1).

Candidate regeneration writes only ``_REFRESHABLE_FIELDS`` on still-pending rows. A salience
column added to the model but omitted from that hand-maintained tuple is silently never
populated on existing pending rows — in step 3 that would read as "transcripts found nothing,"
the absence-of-evidence trap again.

This asserts the **exact set** of salience columns, not mere membership: a membership check
(`"salience_transcript" in _REFRESHABLE_FIELDS`) passes while a *fourth* source added later goes
unrefreshed (the presence-vs-value gap, ADR 016 Mode 1a/1b). The expected set is derived from the
model, so it tracks the schema without a hand-maintained duplicate. Mutation-verify by removing
one salience column from ``_REFRESHABLE_FIELDS`` and confirming this reddens.
"""

from __future__ import annotations

from chronovista.db.models import CandidateSuggestion
from chronovista.repositories.candidate_suggestion_repository import _REFRESHABLE_FIELDS


def test_all_salience_columns_are_refreshable() -> None:
    salience_cols = {
        c.name
        for c in CandidateSuggestion.__table__.columns
        if c.name.startswith("salience")
    }
    refreshable_salience = {f for f in _REFRESHABLE_FIELDS if f.startswith("salience")}
    assert salience_cols == refreshable_salience, (
        f"every salience column must be refreshable. model has {sorted(salience_cols)}; "
        f"_REFRESHABLE_FIELDS has {sorted(refreshable_salience)}; "
        f"unrefreshed: {sorted(salience_cols - refreshable_salience)}"
    )
