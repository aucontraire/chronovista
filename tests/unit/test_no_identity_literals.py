"""Structural anti-mint guard (Feature 060, T026a / FR-012a).

Enforces the identity invariant as a *test*, not a maintained list: no identity
literal may appear as a default value or inline argument anywhere in
``src/chronovista/`` outside the resolver module, the identity model (where the
constants are defined), and repair/migration code. Any new minting path fails
this the moment it is added — the same discipline as the US3 guard.

Rationale: three review rounds each found *more* literal sites; enumeration was
not converging (see spec FR-012a).
"""

from __future__ import annotations

import pathlib

FORBIDDEN_LITERALS = (
    '"takeout_user"',
    "'takeout_user'",
    '"local_user"',
    "'local_user'",
    '"default_user"',
    "'default_user'",
)

# Files allowed to reference the literals: the resolver, the identity model
# (constant + recognized-placeholder set), and repair/migration code.
_ALLOWED = {
    "services/identity_service.py",
    "models/app_identity.py",
}
_ALLOWED_DIR_PARTS = ("db/migrations/",)

_SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "chronovista"


def _is_allowed(rel: str) -> bool:
    return rel in _ALLOWED or any(part in rel for part in _ALLOWED_DIR_PARTS)


def test_no_identity_literals_outside_resolver() -> None:
    offenders: list[str] = []
    for path in _SRC.rglob("*.py"):
        rel = path.relative_to(_SRC).as_posix()
        if _is_allowed(rel):
            continue
        text = path.read_text(encoding="utf-8")
        for lit in FORBIDDEN_LITERALS:
            if lit in text:
                offenders.append(f"{rel}: contains {lit}")
    assert not offenders, (
        "Identity literals must be resolved via IdentityService, not hardcoded. "
        "Offending sites:\n" + "\n".join(offenders)
    )
