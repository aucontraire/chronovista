#!/usr/bin/env bash
# Export the chronovista entity co-occurrence graph from Postgres for Neo4j loading.
# Produces (next to this script):
#   entities.jsonl        - one RAW JSON object per node (psql -tA, no COPY escaping)
#   cooccurs.csv          - e1,e2,reltype,n  (typed CO_OCCURS_* edges per channel, shared-video count), header
#   wikidata_stubs.jsonl  - (:WikidataItem) stub nodes for relation targets (v2 semantic layer)
#   semantic_edges.csv    - src,reltype,targetqid,targetIsEntity (typed entity relations, v2)
#   category_edges.jsonl  - {entityId,categoryName,globalSize} JSON lines (v3 category layer)
#
# Re-sync as the local DB grows:  ./export_graph.sh && python load_neo4j.py
#
# Config via env (defaults = prod container per CLAUDE.md):
#   CHRONO_PGHOST(5435) CHRONO_PGPORT CHRONO_PGUSER CHRONO_PGDB CHRONO_PGPASSWORD
# Co-occurrence threshold (shared videos) as $1, default 2.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PGHOST="${CHRONO_PGHOST:-localhost}"
PGPORT="${CHRONO_PGPORT:-5435}"
PGUSER="${CHRONO_PGUSER:-chronovista}"
PGDATABASE="${CHRONO_PGDB:-chronovista}"
export PGPASSWORD="${CHRONO_PGPASSWORD:-chronovista}"
THRESHOLD="${1:-2}"
# Co-occurrence is SPLIT into one edge TYPE per presence channel (Option 1, 2026-10-26), so a
# co-tagged pair is distinguishable from a discussed-together pair. Each channel is a
# (entity_id, video_id) link-set; the edges file carries a reltype column and the loader MERGEs
# one typed edge per channel -- a pair in N channels gets N parallel edges, each with its own
# sharedVideos count. The combined/weighted view is a QUERY over CO_OCCURS_* (weighting is
# query-time policy, not stored). CHRONO_CHANNEL is retired -- every channel is always emitted.
#   CO_OCCURS_TRANSCRIPT  mention_source='transcript'               spoken substance
#   CO_OCCURS_TITLEDESC   mention_source in (title,description)      billing/framing
#   CO_OCCURS_MANUAL      mention_source='manual'                    human/visual ground truth
#   CO_OCCURS_TAGS        FULL tag association via the repo -- canonical ∪ alias arms, Feature-091
#                         exclusions honored (export_tag_edges.py, Option B). boilerplate-prone.
# TAGS EDGES now come from export_tag_edges.py (repo's association_triples, source=='tag'), NOT the
# SQL arm -- it adds the alias-tag arm (Python normaliser, #207) the pure-SQL export can't do. The
# SQL canonical-tag entry below is kept ONLY to seed the NODESET spine (verified: it already covers
# every Option-B tag endpoint, so no edge is dropped for a missing node).
# Per-channel threshold overrides: THRESHOLD_TRANSCRIPT/_TITLEDESC/_MANUAL/_TAGS (default = $1, 2).
CHANNELS=(transcript titledesc manual tags)
RELTYPES=(CO_OCCURS_TRANSCRIPT CO_OCCURS_TITLEDESC CO_OCCURS_MANUAL CO_OCCURS_TAGS)
LINKS=(
  "SELECT DISTINCT entity_id, video_id FROM entity_mentions WHERE mention_source='transcript'"
  "SELECT DISTINCT entity_id, video_id FROM entity_mentions WHERE mention_source IN ('title','description')"
  "SELECT DISTINCT entity_id, video_id FROM entity_mentions WHERE mention_source='manual'"
  "SELECT DISTINCT ct.entity_id AS entity_id, vt.video_id AS video_id
     FROM canonical_tags ct
     JOIN tag_aliases ta ON ta.canonical_tag_id = ct.id
     JOIN video_tags  vt ON vt.tag = ta.raw_form
    WHERE ct.entity_id IS NOT NULL"
)
THRESHOLDS=(
  "${THRESHOLD_TRANSCRIPT:-$THRESHOLD}"
  "${THRESHOLD_TITLEDESC:-$THRESHOLD}"
  "${THRESHOLD_MANUAL:-$THRESHOLD}"
  "${THRESHOLD_TAGS:-$THRESHOLD}"
)

PSQL=(psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -v ON_ERROR_STOP=1)

# NODESET spine CTE: node membership is channel-AGNOSTIC -- an entity is a node if it co-occurs
# in ANY channel (combined union of all link-sets, base threshold) or is grounded (NODESET_CTE).
# The typed per-channel EDGES are emitted separately below; assoc_links/pairs here feed ONLY the
# nodeset, stub, and semantic queries (which key off e1/e2 membership), never the edge file.
ALL_LINKS="${LINKS[0]}
UNION
${LINKS[1]}
UNION
${LINKS[2]}
UNION
${LINKS[3]}"
PAIRS_CTE="WITH assoc_links AS (
  ${ALL_LINKS}
),
pairs AS (
  SELECT a1.entity_id e1, a2.entity_id e2, count(DISTINCT a1.video_id) n
  FROM assoc_links a1
  JOIN assoc_links a2 ON a1.video_id = a2.video_id AND a1.entity_id < a2.entity_id
  GROUP BY a1.entity_id, a2.entity_id
  HAVING count(DISTINCT a1.video_id) >= ${THRESHOLD}
)"

# Graph nodeset: ALL grounded active entities (not just the co-occurring ones). This makes grounded
# entities that are relationship endpoints — a show with a cast, an employer org — into real nodes /
# hubs instead of vanishing or collapsing into bare Wikidata stubs. The co-occurrence `pairs` CTE
# still drives the CO_OCCURS_* edges; widening the nodeset only changes which entities are nodes
# (and promotes grounded relation targets from stubs to real :Entity nodes). Defined once, used by
# the entities / stubs / semantic queries so they can't drift.
NODESET_CTE="nodeset AS (
  -- The co-occurrence spine: every entity in a co-occurring pair (grounded OR not).
  SELECT e1 AS id FROM pairs UNION SELECT e2 FROM pairs
  UNION
  -- Plus every grounded entity, so relationship endpoints (a show with a cast, an employer org)
  -- become real nodes/hubs even when they never co-occur. UNION dedupes the overlap.
  SELECT id FROM named_entities
  WHERE status='active' AND merged_into_id IS NULL AND external_ids ? 'wikidata'
)"

# v2: traversable Wikidata relation (property key -> Neo4j rel type), DERIVED from the single source
# of truth — src/chronovista/services/wikidata_properties.py:RELATIONS — so it can never drift from
# WANTED again (the old hand-copied list had fallen 9 relations behind: founder, the credit family,
# significant_person, unmarried_partner, field_of_work). reltype = field name upper-cased, which
# reproduces the historical mapping exactly. Override the repo location with CHRONO_REPO.
REPO="${CHRONO_REPO:-$(cd "$HERE/../.." && pwd)}"
REL_VALUES=$(cd "$REPO" && poetry run python -c "
from chronovista.services.wikidata_properties import RELATIONS
print(','.join(f\"('{f}','{f.upper()}')\" for f in dict.fromkeys(RELATIONS.values())))
")
if [ -z "$REL_VALUES" ]; then
  echo "Failed to derive RELATIONS from $REPO (set CHRONO_REPO to the repo path)" >&2
  exit 1
fi
RELS="rels(prop, reltype) AS (VALUES ${REL_VALUES})"

# T030 guard (Feature 105): relations/attributes are derived from the CAPTURE set
# (wikidata_properties.py:RELATIONS / ATTRIBUTES_*), NEVER the seed allowlist — so a
# captured-but-not-seeded edge still reaches the graph. Fail loudly if that ever leaks in.
# The forbidden token is assembled from fragments so this guard never matches its own source.
_FORBIDDEN_IMPORT='SEED''_''ALLOWLIST'
if grep -q "$_FORBIDDEN_IMPORT" "${BASH_SOURCE[0]}"; then
  echo "export_graph.sh must not reference the seed allowlist; relations come from RELATIONS" >&2
  exit 1
fi

# v2 (Feature 105): node ATTRIBUTE projection pairs, DERIVED from the attribute kind groups
# (ATTRIBUTES_ITEM / ATTRIBUTES_LITERAL / IDENTIFIERS) the same way REL_VALUES is derived from
# RELATIONS — so a newly-captured attribute reaches the graph automatically (or must be named in
# OPT_OUT). The scalar/array shape IS the kind group: literals + identifiers are scalar (->>0),
# items are arrays (->'values'), minus a documented SINGLE_VALUED set. Presentation-only exceptions
# (opt-outs, the one key override, single-valued items, the relation-as-attribute extra) live here,
# not in the registry, which stays display-agnostic. A coverage FAIL exits non-zero → empty capture
# → the check below aborts the export.
ATTR_PAIRS=$(cd "$REPO" && poetry run python - <<'PY'
import sys
from chronovista.services.wikidata_properties import (
    ATTRIBUTES_ITEM,
    ATTRIBUTES_LITERAL,
    IDENTIFIERS,
)

# Captured but deliberately NOT a graph node attribute (each with its reason).
OPT_OUT = {
    "instance_of",        # P31 — entity-type cross-check, not a display fact
    "image",              # rendered as the transformed imageUrl, not a raw filename
    "youtube_channel_id",  # social/external IDs we do not surface on graph nodes
    "facebook_id",
    "tiktok_username",
    "mastodon_address",
}
# Items whose first value is the datum — kept scalar to preserve node shape.
SINGLE_VALUED = {"country", "sex_or_gender", "headquarters"}
# Hand-chosen shorter graph keys (else the key is mechanical camelCase of the field).
KEY_OVERRIDES = {"native_language_name": "nativeName"}
# A RELATION also surfaced as a node-attribute array (historical dual projection).
EXTRA_ARRAY = ("field_of_work",)


def camel(field: str) -> str:
    if field in KEY_OVERRIDES:
        return KEY_OVERRIDES[field]
    head, *rest = field.split("_")
    return head + "".join(w.title() for w in rest)


def pair(field: str, *, array: bool) -> str:
    expr = f"ne.properties->'{field}'->'values'" + ("" if array else "->>0")
    return f"  '{camel(field)}', {expr}"


seen: set[str] = set()
lines: list[str] = []
# literals + identifiers -> scalar
for field in list(ATTRIBUTES_LITERAL.values()) + list(IDENTIFIERS.values()):
    if field in OPT_OUT or field in seen:
        continue
    seen.add(field)
    lines.append(pair(field, array=False))
# items -> array (except the single-valued ones)
for field in ATTRIBUTES_ITEM.values():
    if field in OPT_OUT or field in seen:
        continue
    seen.add(field)
    lines.append(pair(field, array=field not in SINGLE_VALUED))
# explicit relation-as-attribute extras
for field in EXTRA_ARRAY:
    if field in seen:
        continue
    seen.add(field)
    lines.append(pair(field, array=True))

# Consistency check (FR-017). Because membership is DERIVED, a newly-captured attribute always
# auto-projects — "silent miss" is structurally impossible, so the original coverage check
# ("projected or opted out") is a tautology. What CAN drift, and what this guards instead:
#   1. a stale OPT_OUT — a field opted out that is no longer captured (dead config, or a typo that
#      would silently drop a real attribute once the real field name appeared), and
#   2. an EXTRA_ARRAY collision — a relation-as-attribute that has since become a real attribute,
#      which would then project twice.
# Either fails the export loudly rather than shipping a wrong graph.
all_attrs = (
    set(ATTRIBUTES_ITEM.values())
    | set(ATTRIBUTES_LITERAL.values())
    | set(IDENTIFIERS.values())
)
problems = []
stale = OPT_OUT - all_attrs
if stale:
    problems.append(f"OPT_OUT names fields no longer captured: {sorted(stale)}")
collide = set(EXTRA_ARRAY) & all_attrs
if collide:
    problems.append(f"EXTRA_ARRAY fields are now real attributes (double-projected): {sorted(collide)}")
if problems:
    sys.stderr.write("ATTRIBUTE PROJECTION FAIL:\n  " + "\n  ".join(problems) + "\n")
    sys.exit(1)

sys.stdout.write(",\n".join(lines))
PY
)
if [ -z "$ATTR_PAIRS" ]; then
  echo "Failed to derive node attributes from $REPO (coverage check failed, see above)" >&2
  exit 1
fi

echo "Exporting (threshold = ${THRESHOLD})  <-  ${PGUSER}@${PGHOST}:${PGPORT}/${PGDATABASE}"

# --- NODES: raw JSON lines via -tA (no COPY escaping) ---
"${PSQL[@]}" -tA > "$HERE/entities.jsonl" <<SQL
${PAIRS_CTE},
${NODESET_CTE}
SELECT jsonb_strip_nulls(jsonb_build_object(
  'entityId', ne.id::text,
  'qid', ne.external_ids->'wikidata'->>'id',
  'name', ne.canonical_name,
  'entityType', ne.entity_type,
  'subtype', ne.entity_subtype,
  'description', COALESCE(ne.description, ne.properties->'wikidata_description'->'values'->>0),
  'mentionCount', ne.mention_count,
  'videoCount', ne.video_count,
  'confidence', ne.confidence,
  'wikidataUrl', CASE WHEN ne.external_ids->'wikidata'->>'id' IS NOT NULL
    THEN 'https://www.wikidata.org/wiki/'||(ne.external_ids->'wikidata'->>'id') END,
  'dbpediaUrl', ne.external_ids->'dbpedia'->>'id',
  'imageUrl', CASE WHEN ne.properties->'image'->'values'->>0 IS NOT NULL
    THEN 'https://commons.wikimedia.org/wiki/Special:FilePath/'||replace(ne.properties->'image'->'values'->>0,' ','_') END,
${ATTR_PAIRS}
))::text
FROM named_entities ne
JOIN nodeset n ON n.id = ne.id;
SQL

# --- EDGES: one TYPED edge per channel. File = e1,e2,reltype,n (one row per pair per channel);
#     the loader MERGEs (a)-[:<reltype> {sharedVideos}]->(b). Per-channel self-join + threshold. ---
{
  echo "e1,e2,reltype,n"
  # SQL mention channels. TAGS is skipped here and produced by export_tag_edges.py below (the
  # repo-backed full tag association: canonical ∪ alias arms + Feature-091 exclusions).
  for i in "${!CHANNELS[@]}"; do
    [ "${CHANNELS[$i]}" = "tags" ] && continue
    "${PSQL[@]}" -tA -F',' <<SQL
WITH links AS (
  ${LINKS[$i]}
)
SELECT a1.entity_id::text, a2.entity_id::text, '${RELTYPES[$i]}', count(DISTINCT a1.video_id)
FROM links a1
JOIN links a2 ON a1.video_id = a2.video_id AND a1.entity_id < a2.entity_id
GROUP BY a1.entity_id, a2.entity_id
HAVING count(DISTINCT a1.video_id) >= ${THRESHOLDS[$i]};
SQL
  done
  # CO_OCCURS_TAGS from the repo's association layer (Option B). Same PROD DB as the psql queries
  # (db_target DEFAULT_URL = :5435). Emits e1,e2,CO_OCCURS_TAGS,n rows.
  ( cd "$REPO" && CHRONO_REPO="$REPO" poetry run python "$HERE/export_tag_edges.py" \
      --threshold "${THRESHOLD_TAGS:-$THRESHOLD}" )
} > "$HERE/cooccurs.csv"

NODES=$(wc -l < "$HERE/entities.jsonl" | tr -d ' ')
EDGES=$(( $(wc -l < "$HERE/cooccurs.csv" | tr -d ' ') - 1 ))
echo "Wrote entities.jsonl ($NODES nodes) and cooccurs.csv ($EDGES edges)."

# Fail loud if the tag/creator channel produced ZERO edges. export_tag_edges.py exits non-zero on
# error (and set -e above aborts us), but a silent zero-row result — e.g. an empty association set —
# would otherwise yield a graph that looks complete while missing CO_OCCURS_TAGS, the people-to-
# people channel the connection explorer exists to explain. Catch it BEFORE any load.
if ! grep -q ',CO_OCCURS_TAGS,' "$HERE/cooccurs.csv"; then
  echo "export_graph.sh: cooccurs.csv has ZERO CO_OCCURS_TAGS rows — the tag/creator channel is missing. Aborting before any load." >&2
  exit 1
fi

# Validate every JSON line parses (catches any escaping/encoding surprise early).
python3 -c "import json,sys; [json.loads(l) for l in open('$HERE/entities.jsonl') if l.strip()]; print('entities.jsonl: all lines valid JSON')"

# =========================== v2: semantic layer ============================
# A target is linked to an EXISTING graph node when its qid is one of the loaded
# entities (nodeset); otherwise it becomes a WikidataItem stub.

# --- STUB NODES: distinct relation targets NOT already in the graph ---
"${PSQL[@]}" -tA > "$HERE/wikidata_stubs.jsonl" <<SQL
${PAIRS_CTE},
${NODESET_CTE},
nodeset_qids AS (
  SELECT ne.external_ids->'wikidata'->>'id' qid FROM named_entities ne
  JOIN nodeset n ON n.id=ne.id WHERE ne.external_ids ? 'wikidata'),
${RELS},
exploded AS (
  SELECT q.qid, v.val FROM named_entities ne JOIN nodeset n ON n.id=ne.id
  JOIN rels r ON ne.properties ? r.prop
  CROSS JOIN LATERAL jsonb_array_elements_text(ne.properties->r.prop->'qids') WITH ORDINALITY q(qid, ord)
  LEFT JOIN LATERAL jsonb_array_elements_text(ne.properties->r.prop->'values') WITH ORDINALITY v(val, ord2)
    ON v.ord2 = q.ord
  WHERE COALESCE(q.qid,'') <> '')
SELECT jsonb_build_object('qid', e.qid, 'name', COALESCE(max(e.val), e.qid))::text
FROM exploded e
WHERE NOT EXISTS (SELECT 1 FROM nodeset_qids nq WHERE nq.qid = e.qid)
GROUP BY e.qid;
SQL

# --- SEMANTIC EDGES: src entityId, rel type, target qid, is-it-already-a-node ---
{
  echo "src,reltype,targetqid,targetIsEntity"
  "${PSQL[@]}" -tA -F',' <<SQL
${PAIRS_CTE},
${NODESET_CTE},
nodeset_qids AS (
  SELECT ne.external_ids->'wikidata'->>'id' qid FROM named_entities ne
  JOIN nodeset n ON n.id=ne.id WHERE ne.external_ids ? 'wikidata'),
${RELS},
exploded AS (
  SELECT ne.id::text AS src, r.reltype, q.qid FROM named_entities ne JOIN nodeset n ON n.id=ne.id
  JOIN rels r ON ne.properties ? r.prop
  CROSS JOIN LATERAL jsonb_array_elements_text(ne.properties->r.prop->'qids') q(qid)
  WHERE COALESCE(q.qid,'') <> '')
SELECT e.src, e.reltype, e.qid,
  CASE WHEN EXISTS (SELECT 1 FROM nodeset_qids nq WHERE nq.qid = e.qid) THEN 1 ELSE 0 END
FROM exploded e;
SQL
} > "$HERE/semantic_edges.csv"

STUBS=$(wc -l < "$HERE/wikidata_stubs.jsonl" | tr -d ' ')
SEMEDGES=$(( $(wc -l < "$HERE/semantic_edges.csv" | tr -d ' ') - 1 ))
echo "Wrote wikidata_stubs.jsonl ($STUBS stubs) and semantic_edges.csv ($SEMEDGES edges)."
python3 -c "import json; [json.loads(l) for l in open('$HERE/wikidata_stubs.jsonl') if l.strip()]; print('wikidata_stubs.jsonl: all lines valid JSON')"

# =========================== v3: category layer ============================
# Entity -> Wikipedia category edges (LIVE tables entity_categories JOIN wikipedia_categories,
# Features 083/084 — fetched from the MediaWiki API, NOT the DBpedia snapshot), scoped to the nodeset so
# there are no orphan category endpoints. Emitted as JSONL (not CSV) because category names are free
# text with commas/quotes/parens that would break an unquoted psql -F',' split. categoryName is the
# shared-node key; globalSize (the category's global Wikipedia member count, nullable) rides along
# for specificity ranking.
"${PSQL[@]}" -tA > "$HERE/category_edges.jsonl" <<SQL
${PAIRS_CTE},
${NODESET_CTE}
SELECT jsonb_build_object(
  'entityId', ne.id::text,
  'categoryName', wc.name,
  'globalSize', wc.global_size
)::text
FROM entity_categories ec
JOIN named_entities ne ON ne.id = ec.entity_id
JOIN nodeset n ON n.id = ne.id
JOIN wikipedia_categories wc ON wc.id = ec.category_id;
SQL

CATEDGES=$(wc -l < "$HERE/category_edges.jsonl" | tr -d ' ')
echo "Wrote category_edges.jsonl ($CATEDGES entity->category edges)."
python3 -c "import json; [json.loads(l) for l in open('$HERE/category_edges.jsonl') if l.strip()]; print('category_edges.jsonl: all lines valid JSON')"
