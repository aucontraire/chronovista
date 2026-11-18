#!/usr/bin/env bash
# Full graph reload — ALL FOUR layers in one command, in the correct order.
# Targets the LOCAL --profile graph container by default; pass --allow-remote to target a remote
# instance (e.g. Aura) on purpose — the loaders refuse a remote write otherwise.
#
# Why this exists: `load_neo4j.py --wipe` clears the entire DB, and `export_graph.sh` does NOT
# produce the reviewed layer — so the reviewed edges only survive a full rebuild if someone
# remembers to re-run `load_reviewed.py` last. "Remember the second loader" is exactly the
# operational step that erodes over months, so the full-reload path calls it here.
#
# Layers loaded:
#   1. observed          (load_neo4j.py --wipe)  : :Entity nodes + CO_OCCURS_* (typed per channel)
#   2. Wikidata semantic (load_semantic.py)      : :WikidataItem stubs + typed relations
#   3. reviewed          (load_reviewed.py)       : :ASSOCIATED_WITH / :COVERS / :CO_CAST (from verdicts.jsonl)
#   4. categories        (load_categories.py)     : :Category nodes + :IN_CATEGORY (DBpedia, Features 083-086)
#
# Env (required by the loaders): NEO4J_URI, NEO4J_USER(/NAME), NEO4J_PWD(/PASSWORD), DB_NAME optional.
# Optional: CHRONO_CHANNEL (transcript|titledesc, default transcript), and $1 = co-occurrence threshold.
#
# Usage:
#   ./reload_all.sh            # full clean rebuild of all three layers
#   ./reload_all.sh 3          # same, co-occurrence threshold 3
#
# For a VERDICT-ONLY change (a re-sort / new review marks, no prod change) you do NOT need this —
# just: python load_reviewed.py --wipe-reviewed
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE"

# Optional --allow-remote (accepted in ANY position): without it, the loaders refuse a non-local
# Neo4j target (they issue DETACH DELETE). Default target is the local --profile graph container;
# your lab .env may point NEO4J_URI at a remote instance, which this guard then refuses by default.
# The one other positional arg is the co-occurrence threshold (default 2).
ALLOW_REMOTE_FLAG=""
ALLOW_REMOTE_PY="False"
THRESHOLD_ARG=""
for arg in "$@"; do
  case "$arg" in
    --allow-remote) ALLOW_REMOTE_FLAG="--allow-remote"; ALLOW_REMOTE_PY="True" ;;
    *) THRESHOLD_ARG="$arg" ;;
  esac
done

# Pre-flight the Neo4j target through the shared guard (neo4j_target.resolve) so a misconfigured or
# accidentally-remote target fails NOW, before the long read-only export — not at step [2/5]. $HERE
# goes via the environment (not interpolated into the -c literal) so a path with a quote can't break
# the Python string.
CHRONO_HERE="$HERE" python -c "import os, sys; sys.path.insert(0, os.environ['CHRONO_HERE']); import neo4j_target; neo4j_target.resolve(allow_remote=$ALLOW_REMOTE_PY)" || exit 1

# Fail fast if the active Python lacks the neo4j driver. The load steps ([2]-[5]) use bare `python`,
# so a wrong-env terminal (e.g. PyCharm re-activated a different interpreter) would otherwise burn
# the whole read-only export first and only die at [2/5]. Mirrors the NEO4J_* env check above.
if ! python -c "import neo4j" >/dev/null 2>&1; then
  echo "The active Python has no 'neo4j' module — the load steps would fail." >&2
  echo "Fix: activate the env that has it  ->  pyenv activate chronovista-env" >&2
  echo "     or install it here            ->  python -m pip install neo4j" >&2
  exit 1
fi

echo "===> [1/5] export_graph.sh (read-only from prod)";  ./export_graph.sh "${THRESHOLD_ARG:-2}"
echo "===> [2/5] load_neo4j.py --wipe (observed layer)";  python load_neo4j.py --wipe $ALLOW_REMOTE_FLAG
echo "===> [3/5] load_semantic.py (Wikidata semantic layer)"; python load_semantic.py $ALLOW_REMOTE_FLAG
echo "===> [4/5] load_reviewed.py (reviewed layer — the step that gets forgotten)"; python load_reviewed.py $ALLOW_REMOTE_FLAG
echo "===> [5/5] load_categories.py (category layer — loaded last so a semantic wipe can't clobber it)"; python load_categories.py $ALLOW_REMOTE_FLAG
echo "===> Done. All four layers reloaded and in sync with prod + verdicts.jsonl."
