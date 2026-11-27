"""Contract guard between the invariant register and the audit's checks (FR-015, FR-016).

``docs/architecture/invariants.md`` names each audit check on its entry's Check line;
``invariant_audit_service.REGISTRY`` says which entry each check verifies. The two
must agree, or the register claims a check that does not exist, or a check verifies
an entry nobody can read. Entries without a data check are allowed: process and
code-structure rules name their test instead.

Mutation-verified (2026-11-27): renaming a registered check, deleting an entry's
heading, or removing a check ID from its Check line each turns a test here red.
"""

from __future__ import annotations

import re
from pathlib import Path

from chronovista.services.invariant_audit_service import REGISTRY

_REGISTER = (
    Path(__file__).resolve().parents[3] / "docs" / "architecture" / "invariants.md"
)
_HEADING = re.compile(r"^### ([A-Z][0-9]+): ", re.MULTILINE)
_CHECK_ID = re.compile(r"`([A-Z][0-9]+-[a-z0-9-]+)`")


def _entries() -> dict[str, str]:
    """Each entry's ID and its section text, up to the next heading."""
    text = _REGISTER.read_text(encoding="utf-8")
    starts = list(_HEADING.finditer(text))
    sections: dict[str, str] = {}
    for i, match in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else len(text)
        sections[match.group(1)] = text[match.start() : end]
    return sections


def _check_lines(section: str) -> str:
    return "\n".join(
        line
        for line in section.splitlines()
        if line.lstrip("- ").startswith("**Check:**")
    )


def test_every_registered_check_verifies_an_entry_that_exists() -> None:
    entries = _entries()
    missing = {
        c.check_id: c.register_entry
        for c in REGISTRY
        if c.register_entry not in entries
    }
    assert missing == {}


def test_every_check_the_register_names_exists() -> None:
    registered = {c.check_id for c in REGISTRY}
    named = {
        check_id
        for section in _entries().values()
        for check_id in _CHECK_ID.findall(_check_lines(section))
    }
    assert named - registered == set()


def test_every_check_is_named_on_its_own_entrys_check_line() -> None:
    entries = _entries()
    unnamed = [
        c.check_id
        for c in REGISTRY
        if c.register_entry in entries
        and c.check_id not in _CHECK_ID.findall(_check_lines(entries[c.register_entry]))
    ]
    assert unnamed == []
