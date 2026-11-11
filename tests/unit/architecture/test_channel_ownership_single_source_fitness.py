"""Architecture fitness test — the imported channel-ownership property has one read home.

Feature 109 adds a user-asserted ownership store (``channel_ownership_assertions``) whose
rows MUST be UNIONed with the imported Wikidata ``youtube_channel_id`` (P2397) values on
every ownership read (spec FR-009). The failure this guards against: a future consumer reads
the raw ``youtube_channel_id`` property directly — a new graph exporter, the productionised
cast detector, a service-layer query — and silently sees only the imported subset, dropping
every user-added link. That is the ``entity_mentions``/tag-evidence hazard one layer up.

The guard keys on the **quoted key literal** ``"youtube_channel_id"`` (either quote style),
NOT on a single accessor pattern — so a reader spelled differently (``properties.get(...)``,
a raw ``text()`` SQL string, a service query) is still caught as long as it names the key.
This is deliberate: an exact-count guard matching only the JSONB-path accessor would pass
VACUOUSLY against another spelling — the v0.117.0 head-scoping lesson, where a structural
guard went green after the query stopped using the constant it counted.

The one read home is ``repositories/named_entity_repository.py`` (the
``_OWNERSHIP_PROPERTY_KEY`` constant + the two private imported-primitives it feeds). The
only other legitimate mention is the WRITE side — the ``P2397 -> youtube_channel_id`` mapping
in ``services/wikidata_properties.py`` (enrichment stores under this key). Any OTHER file
naming the key is a new reader bypassing the union.

CAVEAT (honest): a literal-based guard catches **honest duplication, not deliberate evasion**
— a key built dynamically (``"youtube_" + "channel_id"``) or spelled only in untokenised SQL
would slip past. The goal is a reviewable diff that reads "this adds a second place that
touches the raw ownership property", not a security boundary.

MUTATION-VERIFIED (Constitution §Single-Source Operations): add a differently-spelled reader
in a third file — e.g. ``_x = properties.get("youtube_channel_id")`` — and
``test_imported_ownership_property_has_one_read_home`` goes RED naming that file; remove it,
green. A same-spelling copy of the JSONB path would be caught for the same reason (both name
the quoted key). Confirmed on 2026-11-10.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC = _REPO_ROOT / "src" / "chronovista"

# Exact set, NOT a growable allowlist: adding a file here is itself a reviewable diff.
_ALLOWED = {
    "repositories/named_entity_repository.py",  # the one read home (constant + primitives)
    "services/wikidata_properties.py",  # the write side (P2397 -> key mapping)
}

_KEY = re.compile(r"""["']youtube_channel_id["']""")


def _py_files() -> Iterator[Path]:
    # Migrations are frozen historical snapshots that legitimately carry the key literal in
    # the create_table call; they are out of scope for a guard about live read structure.
    for path in _SRC.rglob("*.py"):
        if "migrations" in path.parts or "__pycache__" in path.parts:
            continue
        yield path


def _files_naming_the_key() -> set[str]:
    out: set[str] = set()
    for path in _py_files():
        if _KEY.search(path.read_text(encoding="utf-8")):
            out.add(str(path.relative_to(_SRC)))
    return out


def test_imported_ownership_property_has_one_read_home() -> None:
    offenders = _files_naming_the_key() - _ALLOWED
    assert not offenders, (
        "the imported `youtube_channel_id` property is named outside its one read home "
        f"(the union helper) and the write mapping: {sorted(offenders)}. Every ownership "
        "read MUST go through NamedEntityRepository's union (spec FR-009); a consumer that "
        "reads the raw property sees only the imported subset and silently drops user-added "
        "links. Route it through the union helper, or — if this is a genuine new home — add "
        "it to _ALLOWED here (a reviewable diff)."
    )


def test_allowed_homes_actually_name_the_key() -> None:
    """The guard is meaningful only if the allowlisted homes really contain the key — else a
    rename leaves the guard green while the home moved. This is the other mutation direction.
    """
    missing = _ALLOWED - _files_naming_the_key()
    assert not missing, (
        f"allowlisted ownership homes no longer name the key: {sorted(missing)}. The read "
        "home or the write mapping moved; update _ALLOWED to the new location."
    )
