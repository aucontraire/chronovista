"""Guard: the import constraints that keep a source abstraction introducible.

Feature 065 deliberately deferred the general recovery-source abstraction and
replaced "keep it straightforward to introduce later" — which cannot be shown
true or false — with two conditions that can (FR-030, FR-031).

They are enforced here rather than by inspection. An inspection is a promise
someone made once; a refactor two months from now does not consult it. The same
week this was written, a documentation page in this repository was found to have
drifted for three releases under a header asserting it could not drift, and the
fix was a test.

Imports are read with ``ast`` rather than by importing the modules: importing
`services.recovery` executes its package ``__init__``, which is itself how the
first version of this feature discovered a circular import.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
RECOVERY = REPO_ROOT / "src" / "chronovista" / "services" / "recovery"
SRC = REPO_ROOT / "src" / "chronovista"

# Repositories that already imported a service before this guard existed.
#
# Found by this test on 2026-08-12, and left alone: fixing it belongs to
# whoever owns that code, not to a recovery feature. It is recorded rather than
# excluded by narrowing the rule, so the violation stays visible and no *new*
# one can be added quietly.
_KNOWN_INVERSIONS = {"entity_mention_repository.py"}

MERGE_POLICY = RECOVERY / "merge_policy.py"
FILMOT_RECOVERY = RECOVERY / "filmot_recovery.py"


def _imported_modules(path: Path) -> set[str]:
    """Every module named by an import in *path*, dotted and absolute."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def _modules_importing(target: str) -> set[Path]:
    """Every file under ``src/`` that imports *target*."""
    importers: set[Path] = set()
    for path in SRC.rglob("*.py"):
        if target in _imported_modules(path) or any(
            m.startswith(f"{target}.") for m in _imported_modules(path)
        ):
            importers.add(path)
    return importers


class TestMergePolicyIsALeaf:
    """FR-031: dependencies point towards the policy, never away from it."""

    def test_it_imports_neither_recovery_path(self) -> None:
        imports = _imported_modules(MERGE_POLICY)

        assert "chronovista.services.recovery.filmot_recovery" not in imports
        assert "chronovista.services.recovery.orchestrator" not in imports

    def test_it_imports_nothing_from_this_project_at_all(self) -> None:
        """Stronger than FR-031 requires, and deliberately so.

        The policy is pure rules over values. The moment it needs a repository,
        a model or a client, it has stopped being the thing both paths can
        safely share — and that erosion is gradual, so the guard is absolute.
        """
        project_imports = {
            m for m in _imported_modules(MERGE_POLICY) if m.startswith("chronovista")
        }

        assert (
            project_imports == set()
        ), f"merge_policy gained project imports: {sorted(project_imports)}"


class TestFilmotRecoveryIsNotAPublicDependency:
    """FR-030: only the operator surface and tests may import the path."""

    def test_only_the_cli_imports_it(self) -> None:
        importers = _modules_importing("chronovista.services.recovery.filmot_recovery")
        relative = sorted(p.relative_to(REPO_ROOT).as_posix() for p in importers)

        assert relative == ["src/chronovista/cli/commands/recover.py"], (
            "only the command exposing this source to operators may import it; "
            f"found: {relative}"
        )

    def test_no_repository_imports_a_recovery_service(self) -> None:
        """The direction that was wrong once already.

        An early draft had `video_repository` import the merge policy, which
        was not merely backwards but an actual import cycle
        (repository -> services.recovery -> orchestrator -> repository). The
        fix was to pass the placeholder patterns in. This asserts the direction
        stays fixed.
        """
        offenders = []
        for path in (SRC / "repositories").rglob("*.py"):
            services = {
                m
                for m in _imported_modules(path)
                if m.startswith("chronovista.services")
            }
            if services and path.name not in _KNOWN_INVERSIONS:
                offenders.append((path.name, sorted(services)))

        assert offenders == [], f"repositories importing services: {offenders}"

    def test_the_known_inversion_has_not_spread(self) -> None:
        """The allowlist must stay exactly as long as it was found.

        An allowlist that grows is how a rule dies quietly. This asserts the
        pre-existing entry still exists (so the guard is not silently passing
        because someone fixed it and forgot to remove the exemption) and that
        nothing joined it.
        """
        still_inverted = {
            path.name
            for path in (SRC / "repositories").rglob("*.py")
            if any(
                m.startswith("chronovista.services") for m in _imported_modules(path)
            )
        }

        assert still_inverted == _KNOWN_INVERSIONS, (
            "the set of repositories importing services changed. If one was "
            "fixed, remove it from _KNOWN_INVERSIONS. If one was added, do not."
        )
