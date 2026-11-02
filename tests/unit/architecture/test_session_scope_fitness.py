"""Architecture fitness guards — ``db_manager.session()`` is the one session idiom (issue #233).

Issue #233: ``chronovista enrich run`` printed a spurious ``GeneratorExit`` traceback after an
otherwise-successful run. The cause was the generator form ``async for s in
db_manager.get_session(...): ... return/break``: leaving the loop early throws ``GeneratorExit`` at
the suspended ``yield``, and the generator's cleanup (``commit``/``close``) is deferred to garbage
collection or interpreter shutdown, where the stray traceback surfaces.

The fix converged every call site onto the async context manager ``db_manager.session(...)``, whose
early exit (``return``/``break``/exception) is ordinary control flow with a deterministic
commit/rollback, and removed the ``get_session`` generator method entirely. These guards, run as
ordinary unit tests on every push, keep that single idiom enforced (the v1.3.0 "Single-Source
Operations and Fitness Guards" rule):

- **G1 (load-bearing, exact-count 0)**: no ``async for ... in ... get_session(...)`` loop exists
  anywhere under ``src/chronovista/``. This is the footgun the fix removed; any reintroduction is
  the exact shape that re-earns #233 and lands here as a reviewable RED.
- **G2 (exact-count 0)**: the ``get_session(`` session-generator accessor does not appear under
  ``src/chronovista/`` at all — the method is gone, so ``db_manager.session()`` is the only way to
  open a session. (``get_session_factory(`` is a different, legitimate method and is not matched:
  the pattern requires ``get_session`` immediately followed by ``(``.)

CAVEAT (stated honestly): these are text-based guards over source. They catch **honest
reintroduction** — someone writing the old ``async for ... get_session`` idiom again, or re-adding
the generator method — **not deliberate evasion** (aliasing the accessor, building the loop from
fragments). The goal is a reviewable diff that reads "this brings back the GeneratorExit footgun",
not a security boundary.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SRC_DIR = _REPO_ROOT / "src" / "chronovista"

# G1: an ``async for`` whose iterable is a ``get_session(...)`` call — the #233 footgun.
_ASYNC_FOR_GET_SESSION = re.compile(r"async\s+for\s+\w+\s+in\s+[\w.]*get_session\s*\(")

# G2: the session-generator accessor ``get_session(``. ``get_session_factory(`` is NOT matched,
# because the char after ``get_session`` there is ``_``, not ``(``.
_GET_SESSION_CALL = re.compile(r"\bget_session\s*\(")


def _src_files() -> Iterator[Path]:
    for path in _SRC_DIR.rglob("*.py"):
        if "__pycache__" not in path.parts:
            yield path


def _rel(path: Path) -> str:
    return path.relative_to(_REPO_ROOT).as_posix()


def test_g1_no_async_for_over_get_session() -> None:
    """G1 (load-bearing): the ``async for ... get_session(...)`` footgun exists nowhere in src.

    This is the exact idiom issue #233 reports: exiting such a loop early throws ``GeneratorExit``
    at the suspended yield and defers cleanup to shutdown. Converging onto ``async with
    db_manager.session(...)`` made the mistake unrepresentable; any reintroduction trips here.
    """
    offenders = sorted(
        _rel(path)
        for path in _src_files()
        if _ASYNC_FOR_GET_SESSION.search(path.read_text(encoding="utf-8"))
    )
    assert offenders == [], (
        "The `async for ... in db_manager.get_session(...)` idiom re-earns issue #233 "
        "(spurious GeneratorExit on early exit). Use `async with db_manager.session(...) as "
        f"session:` instead. Offending files: {offenders}"
    )


def test_g2_get_session_accessor_is_gone() -> None:
    """G2 (exact-count 0): the ``get_session(`` generator accessor appears nowhere in src.

    The generator method was removed in favour of the ``session()`` context manager, so the only
    way to open a session is ``db_manager.session()``. Re-adding the accessor (method or call)
    brings back the deferred-cleanup footgun and trips this. ``get_session_factory(`` is a distinct,
    legitimate method and is intentionally not matched.
    """
    offenders = sorted(
        _rel(path)
        for path in _src_files()
        if _GET_SESSION_CALL.search(path.read_text(encoding="utf-8"))
    )
    assert offenders == [], (
        "`get_session(` must not appear under src/chronovista/ — `db_manager.session()` is the "
        f"single supported session idiom (issue #233). Offending files: {offenders}"
    )
