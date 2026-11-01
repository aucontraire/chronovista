"""Architecture fitness guards — the Wikimedia fetch layer has one home (Feature 102, FR-010).

Promotes the single-entry-point invariant from the Constitution's Judgment tier to the Automated
tier (the v1.3.0 "Single-Source Operations and Fitness Guards" rule): five async knowledge-source
services — the Wikidata client, the DBpedia resolver, the entity-category fetch, the category-size
fetch, and the page-image fallback — now compose one shared ``WikimediaTransport`` instead of each
re-rolling the outbound-HTTP scaffolding that had drifted into two silent-wrong-result bugs. Three
guards, run as ordinary unit tests on every push, keep that single entry point enforced:

- **G1 (identity — LOAD-BEARING, exact-count)**: the outbound User-Agent is assembled in EXACTLY
  ONE site — ``wikimedia_user_agent`` in ``wikimedia_transport.py``. This is the guarantee: every
  outbound request must carry the single-sourced, contact-bearing UA (Wikimedia throttles a
  contactless UA ~20x), so any request hand-rolled outside the transport must assemble its own UA
  → the assembler set grows → RED → a reviewable diff. G2/G3 are supporting.
- **G2 (pagination — exact-count)**: the MediaWiki continuation token ``clcontinue`` appears in
  EXACTLY ONE site — the shared ``paginate_mediawiki`` helper (which defaults the token so no thin
  client re-names it). ``clcontinue`` correctness — the ``normalized``/``redirects`` hop-remap that
  is the v0.104.1 false-zero fix — exists in exactly one place; a future listing fetch written
  without the helper re-earns that bug and trips this.
- **G3 (endpoint locality — supporting heuristic, NOT exact-count)**: host/endpoint literals
  (``wikidata.org`` / ``dbpedia.org`` / ``api.php`` / ``/sparql`` / ``wbgetentities``) appear only
  within the transport, the five thin clients, and a bounded, documented set of non-fetch holders.
  This is explicitly a SECONDARY heuristic, NOT the guarantee (G1 is): the allowlist is bounded
  today but would grow with a new service, so it is not relied on as the exact-count guard and it
  carries the honest-duplication-not-evasion caveat below. It is intentionally NOT a count of
  ``httpx.AsyncClient(`` — client construction is legitimate in several places.

CAVEAT (stated honestly, per the amendment): these are name/literal-based guards over source text.
They catch **honest duplication** — a new request hand-assembling a UA the ordinary way, a
re-rolled continuation loop, a raw endpoint literal in a fresh module — **not deliberate evasion**
(aliasing the UA template, building the header dict under a differently-named key, or composing a
host from fragments). The goal is a reviewable diff that reads "this adds a second place that talks
to a Wikimedia endpoint," not a security boundary.

The deleted-video **recovery** clients (``recovery/``) and the **image-caching/serving** subsystem
(``image_cache.py``) are out of scope (spec Non-Goals): they are not Wikimedia-knowledge-source
fetchers and own their own mature rate-limit/UA handling, which this feature mirrors but does not
absorb. They are therefore excluded from G1 and allowlisted in G3 — a bounded carve-out, widened
only by a reviewable edit to this file.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_SERVICES_DIR = _REPO_ROOT / "src" / "chronovista" / "services"

_TRANSPORT = "src/chronovista/services/wikimedia_transport.py"


def _services_files() -> Iterator[Path]:
    for path in _SERVICES_DIR.rglob("*.py"):
        if "__pycache__" not in path.parts:
            yield path


def _rel(path: Path) -> str:
    return path.relative_to(_REPO_ROOT).as_posix()


# --- G1: the User-Agent is assembled in exactly one site (load-bearing) ---------------------------

# A UA-assembly marker: either the ``"User-Agent"`` header-dict key, or the product-token assembly
# ``chronovista/<version>`` (f-string ``chronovista/{`` or a literal ``chronovista/1.0``). It
# deliberately does NOT match a path like ``~/.chronovista/enrichment.lock`` (``chronovista/e``).
_UA_ASSEMBLY = re.compile(r'"User-Agent"|chronovista/(?:\{|\d)')

# The two out-of-scope subsystems that own their own UA (spec Non-Goals): the image
# caching/serving endpoint and the deleted-video recovery clients. Excluded, not allowlisted,
# because G1 is the load-bearing guarantee and must not silently grow an allowlist.
_UA_EXCLUDED_FILES = frozenset({"src/chronovista/services/image_cache.py"})
_UA_EXCLUDED_DIRS = ("src/chronovista/services/recovery/",)


def _ua_excluded(rel: str) -> bool:
    return rel in _UA_EXCLUDED_FILES or any(
        rel.startswith(prefix) for prefix in _UA_EXCLUDED_DIRS
    )


def test_g1_user_agent_assembled_in_exactly_one_site() -> None:
    """G1 (load-bearing): the single UA producer is ``wikimedia_user_agent`` in the transport.

    Among the in-scope fetch-layer services (the out-of-scope recovery/image subsystems carved
    out), the ONLY file that assembles a User-Agent is the transport. A thin client that hand-rolls
    a request must assemble its own UA and lands here as a second assembler — RED.
    """
    assemblers = sorted(
        _rel(path)
        for path in _services_files()
        if not _ua_excluded(_rel(path))
        and _UA_ASSEMBLY.search(path.read_text(encoding="utf-8"))
    )
    assert assemblers == [_TRANSPORT], (
        "The outbound User-Agent must be assembled in exactly one site "
        "(wikimedia_user_agent in the transport); a hand-rolled request elsewhere assembles its "
        f"own UA and trips this. Assembler files found: {assemblers}"
    )


# --- G2: clcontinue continuation handling lives in exactly one site -------------------------------

_CLCONTINUE = re.compile(r"clcontinue")


def test_g2_clcontinue_in_exactly_one_site() -> None:
    """G2: MediaWiki ``clcontinue`` continuation handling appears only in ``paginate_mediawiki``.

    The transport defaults the continuation token, so a thin client delegates (passing nothing)
    rather than naming it; the literal lives in exactly one services file. A hand-rolled
    continuation loop anywhere else re-earns the normalized/redirect false-zero bug and trips this.
    """
    homes = sorted(
        _rel(path)
        for path in _services_files()
        if _CLCONTINUE.search(path.read_text(encoding="utf-8"))
    )
    assert homes == [_TRANSPORT], (
        "MediaWiki clcontinue continuation handling must appear in exactly one site "
        f"(paginate_mediawiki in the transport); found in: {homes}"
    )


# --- G3: endpoint literals are local to the fetch layer (supporting heuristic) --------------------

_ENDPOINT_LITERALS = re.compile(
    r"wikidata\.org|dbpedia\.org|api\.php|/sparql|wbgetentities"
)

# The bounded-today allowlist (honest-duplication-not-evasion caveat in the module docstring): the
# transport + the five thin clients, plus three documented non-fetch holders —
# ``category_coverage.py`` (a DBpedia-IRI-parsing docstring example), ``wikidata_properties.py`` (a
# ``wbgetentities`` claims-shape docstring), and ``image_cache.py`` (the out-of-scope Commons image
# endpoint). NOT the exact-count guarantee — G1 is; this check grows with a reviewable edit here.
_ENDPOINT_ALLOWLIST = frozenset(
    {
        _TRANSPORT,
        "src/chronovista/services/wikidata_client.py",
        "src/chronovista/services/dbpedia_resolver.py",
        "src/chronovista/services/entity_category_fetch.py",
        "src/chronovista/services/category_size.py",
        "src/chronovista/services/wikipedia_image_fallback.py",
        "src/chronovista/services/category_coverage.py",
        "src/chronovista/services/wikidata_properties.py",
        "src/chronovista/services/image_cache.py",
    }
)


def test_g3_endpoint_literals_local_to_fetch_layer() -> None:
    """G3 (supporting heuristic): no Wikimedia host/endpoint literal outside the allowlisted set.

    A secondary, acknowledged-bounded check (G1 is the guarantee). A raw endpoint literal in a
    module outside the fetch layer is the smell of a new hand-rolled Wikimedia call — RED until it
    either goes through the transport or is deliberately allowlisted here.
    """
    offenders = sorted(
        _rel(path)
        for path in _services_files()
        if _ENDPOINT_LITERALS.search(path.read_text(encoding="utf-8"))
        and _rel(path) not in _ENDPOINT_ALLOWLIST
    )
    assert offenders == [], (
        "A Wikimedia host/endpoint literal appears outside the fetch-layer allowlist — route it "
        "through WikimediaTransport or add it to the documented allowlist in this guard. "
        f"Offenders: {offenders}"
    )
