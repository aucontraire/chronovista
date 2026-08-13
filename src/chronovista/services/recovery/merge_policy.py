"""
Shared merge policy for recovery sources.

This module is the single home for the rules deciding whether a *recovered*
value may be written over what is stored. It belongs to no recovery path: it
imports none of them, and nothing it depends on can import it back (FR-031).
Dependencies point towards the policy, never away from it — which is what keeps
the deferred source abstraction introducible.

Only the Filmot path imports it today. The archived-page path predates it and
has not been migrated; saying "both import it" would describe an intention
rather than the tree, and an intention is not enforceable by a test.

**Fill-only, for third-party archives.** A third-party index is weaker evidence
than what the platform itself or the user's own export said, so it may fill a
gap and may never contest a value. Every rule below therefore gates on the
*stored* value, not on what the archive offers.

That gating is also why no precedence rule between sources exists or is needed:
a field another source has filled is unreachable, so two sources can never
contest one. The invariant has a single failing condition — *this source wrote
a field that already held a real value* — and it is enforced by test rather
than described (FR-015).

One caveat the policy alone cannot satisfy: these functions decide against a
value read at some earlier moment. The caller MUST re-assert each gate as part
of the write itself (FR-011b), or a concurrent writer could fill the field in
between and this source would overwrite it.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import ColumnElement, func, or_
from sqlalchemy.orm import InstrumentedAttribute

# Measured against production 2026-08-12: of 1,312 placeholder titles among
# unavailable videos, 1,226 carry the URL form and 86 the bracketed form —
# together exactly the independently-counted total. No `http://` form exists,
# so no scheme-insensitive matching is specified: it would serve zero rows.
_PLACEHOLDER_URL_PREFIX = "https://www.youtube.com/watch"

# Machine-generated, hence matched case-sensitively.
_PLACEHOLDER_BRACKET_PREFIX = "[Placeholder] Video "

# The same two prefixes as SQL LIKE patterns, for the candidate query.
#
# Derived from the constants above rather than written out again: FR-004c
# requires the query and the policy to share one definition, not two that agree
# today. A new placeholder form is then a one-line change here, and it is
# impossible to update the predicate without updating the matcher.
#
# `_` and `%` are LIKE wildcards; neither prefix contains one, so no escaping
# is needed. A future prefix containing either would.
PLACEHOLDER_TITLE_SQL_PATTERNS: tuple[str, ...] = (
    f"{_PLACEHOLDER_URL_PREFIX}%",
    f"{_PLACEHOLDER_BRACKET_PREFIX}%",
)

# The whitespace both halves of the definition trim, spelled out rather than
# left to the defaults — which disagree. Python's `str.strip()` removes every
# Unicode space, including U+00A0; PostgreSQL's `btrim(col)` removes ASCII
# space alone. Naming one set makes the Python matcher and the SQL predicate
# provably equivalent instead of approximately so, and a test asserts they
# agree input by input.
_TRIMMED_WHITESPACE = " \t\n\r\x0b\x0c"

# Above this, a unit error at the source is likelier than a real runtime. The
# library already holds 18 videos longer than a day, the largest at roughly 902
# days, which is evidence that implausible durations do reach databases. The
# accepted cost is that a genuine multi-day recording would be refused, and
# refusals are reported rather than silent so the cost stays visible (FR-022c).
MAX_PLAUSIBLE_DURATION_SECONDS = 86_400

# Reasons a value was refused. Reported, never silently dropped.
REFUSED_STORED_VALUE_IS_REAL = "stored_value_is_real"
REFUSED_INCOMING_IS_PLACEHOLDER = "incoming_is_placeholder"
REFUSED_INCOMING_IMPLAUSIBLE = "incoming_implausible"
REFUSED_CHANNEL_UNKNOWN = "channel_unknown"


def is_placeholder_title(title: str | None) -> bool:
    """
    Whether a stored title is a placeholder rather than a real value (FR-004a).

    A placeholder is NULL, empty, whitespace-only, a string beginning with the
    YouTube watch URL, or one beginning with the generated ``[Placeholder]
    Video `` prefix. Anything else is a **real value** and is beyond a
    fill-only source's reach.

    The first two forms do not currently occur among unavailable videos. They
    are handled defensively rather than speculatively: they cost one comparison
    and would otherwise be discovered as a bug.

    Parameters
    ----------
    title : str | None
        The stored title.

    Returns
    -------
    bool
        True when the title may be overwritten by a fill-only source.
    """
    if title is None or not title.strip(_TRIMMED_WHITESPACE):
        return True
    return title.startswith(_PLACEHOLDER_URL_PREFIX) or title.startswith(
        _PLACEHOLDER_BRACKET_PREFIX
    )


def placeholder_title_condition(
    title_col: InstrumentedAttribute[str],
) -> ColumnElement[bool]:
    """
    ``is_placeholder_title`` as a SQL predicate over *title_col* (FR-004c).

    Two consumers need this rule in SQL rather than in Python: the query that
    selects candidates, and the conditional UPDATE that re-asserts the gate at
    write time (FR-011b). They MUST be the same expression, and this function
    is how they are.

    When they were merely *similar*, the selection trimmed whitespace and the
    write gate compared against the empty string. A whitespace-only title was
    therefore selected, approved by the policy, and refused by the gate —
    leaving the row an untouched candidate for the next run, and the one after
    that, while the log blamed a concurrent writer that did not exist. The
    patterns were also indexed positionally at the gate, so a third placeholder
    form would have been selected and then silently never written.

    Takes the column rather than importing the model, which is what lets a
    repository be handed the finished condition without any repository ever
    importing a service (FR-030, FR-031).

    Parameters
    ----------
    title_col : InstrumentedAttribute[str]
        The mapped title column to test, e.g. ``Video.title``.

    Returns
    -------
    ColumnElement[bool]
        True for rows a fill-only source may write to.
    """
    return or_(
        title_col.is_(None),
        func.btrim(title_col, _TRIMMED_WHITESPACE) == "",
        *[title_col.like(pattern) for pattern in PLACEHOLDER_TITLE_SQL_PATTERNS],
    )


class FilmotMergeOutcome(BaseModel):
    """
    What the fill-only policy permits for one video.

    Pure data: the policy computes it, and the caller applies it. Keeping the
    decision separate from the write is what allows the same rules to be
    unit-tested exhaustively and re-asserted at write time.

    Attributes
    ----------
    updates : dict[str, Any]
        Column name to new value. Empty when nothing may be written.
    fields_written : list[str]
        The columns in ``updates``, for the provenance record.
    refused : list[str]
        ``"field:reason"`` for each value the archive offered and the policy
        declined, so the cost of the rules stays visible.
    unknown_channel_id : str | None
        A channel the archive named that the library does not know. Reported
        rather than created (FR-006).
    """

    model_config = ConfigDict(frozen=True)

    updates: dict[str, Any] = Field(default_factory=dict)
    fields_written: list[str] = Field(default_factory=list)
    refused: list[str] = Field(default_factory=list)
    unknown_channel_id: str | None = None

    @property
    def writes_anything(self) -> bool:
        """Whether applying this outcome would change the row.

        ``updates`` empty means no write **and** no provenance record — a
        source that contributed nothing must not claim a contribution
        (FR-013).
        """
        return bool(self.updates)


def build_filmot_update(
    stored_title: str | None,
    stored_channel_id: str | None,
    stored_duration: int | None,
    incoming_title: str | None,
    incoming_channel_id: str | None,
    incoming_duration: int | None,
    channel_known: bool,
) -> FilmotMergeOutcome:
    """
    Apply the fill-only policy for one video.

    Takes stored and incoming values rather than ORM objects so the rules can
    be exercised without a database and cannot accidentally read anything else
    about the row.

    Parameters
    ----------
    stored_title, stored_channel_id, stored_duration
        The values currently held by the library.
    incoming_title, incoming_channel_id, incoming_duration
        The values the archive supplied. Any may be absent.
    channel_known : bool
        Whether ``incoming_channel_id`` already has a record. The caller
        resolves this; the policy does not query.

    Returns
    -------
    FilmotMergeOutcome
        Permitted writes, refusals with reasons, and any unknown channel.

    Notes
    -----
    ``upload_date`` is absent from the signature deliberately. It is not
    "never written by rule" — it is not passed in at all, so no future edit to
    this function can begin writing it by accident (FR-008).
    """
    updates: dict[str, Any] = {}
    refused: list[str] = []
    unknown_channel: str | None = None

    # Title: fill a placeholder, never contest a real value, and never write a
    # value that is itself placeholder-shaped (FR-004, FR-004b).
    if incoming_title:
        if not is_placeholder_title(stored_title):
            refused.append(f"title:{REFUSED_STORED_VALUE_IS_REAL}")
        elif is_placeholder_title(incoming_title):
            refused.append(f"title:{REFUSED_INCOMING_IS_PLACEHOLDER}")
        else:
            updates["title"] = incoming_title

    # Channel: fill only when absent AND the channel is already known. A
    # missing channel is reported, never invented — creating a row to satisfy
    # a foreign key is how placeholder data gets laundered into looking real
    # (FR-005, FR-006).
    if incoming_channel_id:
        if stored_channel_id is not None:
            refused.append(f"channel_id:{REFUSED_STORED_VALUE_IS_REAL}")
        elif not channel_known:
            unknown_channel = incoming_channel_id
            refused.append(f"channel_id:{REFUSED_CHANNEL_UNKNOWN}")
        else:
            updates["channel_id"] = incoming_channel_id

    # Duration: fill only zero/absent, and only with a plausible value. Zero
    # from the archive means "unknown" at the source, so it never arrives here
    # as a candidate write (FR-007, FR-007a).
    if incoming_duration is not None and incoming_duration > 0:
        if stored_duration:
            refused.append(f"duration:{REFUSED_STORED_VALUE_IS_REAL}")
        elif incoming_duration > MAX_PLAUSIBLE_DURATION_SECONDS:
            refused.append(f"duration:{REFUSED_INCOMING_IMPLAUSIBLE}")
        else:
            updates["duration"] = incoming_duration

    return FilmotMergeOutcome(
        updates=updates,
        fields_written=sorted(updates),
        refused=refused,
        unknown_channel_id=unknown_channel,
    )
