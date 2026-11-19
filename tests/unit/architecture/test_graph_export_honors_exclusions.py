"""Fitness guard: the co-occurrence export subtracts Feature-091 manual exclusions on the mention
channels — and deliberately does NOT subtract them on the tag-arm nodeset seed.

THE BUG THIS GUARDS (gap-detection follow-up to Feature 113). ``scripts/graph/export_graph.sh``
builds the typed ``CO_OCCURS_{TRANSCRIPT,TITLEDESC,MANUAL}`` edges straight from ``entity_mentions``.
Before this guard it did so with NO anti-join against ``entity_video_exclusions``, so a false
mention the user excluded in the app never left the graph: the co-occurrence edge counted that
video forever, and the gap-mining rankings (which read co-occurrence strength) could never improve
from QC. The three MENTION channels MUST subtract the exclusion.

THE INVARIANT THAT MUST NOT BREAK WHILE FIXING IT. The SQL tag arm (``LINKS[3]``:
``canonical_tags`` → ``tag_aliases`` → ``video_tags``) feeds ONLY the nodeset spine — the per-channel
edge loop ``continue``s on ``tags``, and the real tag EDGES come from ``export_tag_edges.py``, which
already subtracts exclusions. The nodeset is a deliberate SUPERSET (co-occurrence spine ∪ every
grounded entity) whose job is to guarantee every edge has a node. Anti-joining ``LINKS[3]`` could
only SHRINK it — risking a dropped non-grounded tag-edge endpoint (a dangling edge) for ZERO benefit
(an isolated excluded-tag node is harmless; the tag edge already excludes). So ``LINKS[3]`` is kept
un-subtracted, and this guard pins that asymmetry so a future "wrap all four for uniformity" edit
goes red and must re-justify itself.

Sibling of ``test_graph_loader_target_guard.py`` / ``test_graph_serving_state_bracket.py`` (same
script tree). Constitution: the anti-join is defined ONCE (``EXCL_ANTIJOIN``) and used by three
channels — one home, three call sites — so it carries a same-PR, mutation-verified fitness test.

Mutation-verify (do before merge):
  - delete ``${EXCL_ANTIJOIN}`` from any one mention channel
      → test_mention_channels_subtract_exclusions goes red.
  - add ``${EXCL_ANTIJOIN}`` (or ``entity_video_exclusions``) to the tag arm
      → test_tag_seed_is_not_subtracted goes red (and the mention test too — count becomes 4).
"""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
_EXPORT = _REPO / "scripts" / "graph" / "export_graph.sh"


def _links_block() -> str:
    """The ``LINKS=( ... )`` array literal, where the channel link-sets are defined.

    Sliced from ``LINKS=(`` to the array's closing paren — which is the first ``)`` that starts a
    line (``\\n)``). The ``IN ('title','description')`` and ``EXCL_ANTIJOIN`` parens are mid-line, so
    they are not mistaken for the close.
    """
    src = _EXPORT.read_text()
    start = src.index("LINKS=(")
    end = src.index("\n)", start)
    return src[start:end]


def test_mention_channels_subtract_exclusions() -> None:
    src = _EXPORT.read_text()
    assert "entity_video_exclusions" in src, (
        "export_graph.sh must anti-join the mention channels against entity_video_exclusions "
        "(Feature-091). Without it an excluded false mention keeps producing a co-occurrence edge "
        "and QC never reaches the graph."
    )
    # The shared anti-join must be defined against the OUTER mention row (em.*), not the exclusion
    # row — a correlation bug (x.entity_id = x.entity_id) would silently subtract nothing.
    assert "x.entity_id = em.entity_id" in src and "x.video_id = em.video_id" in src, (
        "the exclusion anti-join must correlate on the outer entity_mentions row (em.*); otherwise "
        "it matches the exclusion table against itself and removes nothing."
    )
    block = _links_block()
    n_mention = block.count("FROM entity_mentions em")
    n_antijoin = block.count("${EXCL_ANTIJOIN}")
    assert n_mention == 3, f"expected exactly 3 mention channels, found {n_mention}"
    assert n_antijoin == 3, (
        f"expected the ${{EXCL_ANTIJOIN}} anti-join on exactly the 3 mention channels, found "
        f"{n_antijoin}. If this is 4, the tag arm was wrapped too — see test_tag_seed_is_not_subtracted."
    )


def test_tag_seed_is_not_subtracted() -> None:
    block = _links_block()
    tag_arm = block[block.index("FROM canonical_tags") :]
    assert (
        "${EXCL_ANTIJOIN}" not in tag_arm and "entity_video_exclusions" not in tag_arm
    ), (
        "the SQL tag arm (LINKS[3]) must NOT subtract exclusions — it feeds ONLY the nodeset spine "
        "and must stay a superset covering every tag-edge endpoint. Subtracting it risks dropping a "
        "non-grounded endpoint (a dangling edge) for zero benefit; the tag EDGES honor exclusions "
        "separately in export_tag_edges.py."
    )
