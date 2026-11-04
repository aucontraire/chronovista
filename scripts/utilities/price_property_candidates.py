"""Price each proposed WANTED-expansion property: how many candidates it would mint.

candidates(field) = distinct target QIDs of its PID across the archive that are NOT
already a library entity (matches GenerationSummary.candidates_discovered = "distinct
not-yet-library targets"). Also reports NET-NEW = minus QIDs already pending candidates.

Offline: reads the refreshed archive (local) + PROD (read-only) for the library/candidate QID sets.
"""

from __future__ import annotations
import glob, json, os, collections
import psycopg2  # type: ignore

ARCHIVE = os.path.expanduser("~/chronovista_wikidata_archive")
PG = dict(
    host="localhost",
    port=5435,
    user="chronovista",
    password="chronovista",
    dbname="chronovista",
)

# proposed edges: PID -> (label, field_name)
PROPOSED = {
    # person
    "P793": "significant_event",
    "P1038": "relative",
    "P3602": "candidacy_in_election",
    "P1411": "nominated_for",
    "P6872": "has_written_for",
    "P607": "participated_in_conflict",
    "P737": "influenced_by",
    "P135": "movement",
    "P937": "work_location",
    "P184": "doctoral_advisor",
    "P1066": "student_of",
    "P53": "family",
    "P1399": "convicted_of",
    "P945": "allegiance",
    # organization
    "P527": "has_part",
    "P138": "named_after",
    "P8324": "funder",
    "P740": "location_of_formation",
    "P1365": "replaces",
    "P155": "follows",
    "P1056": "product_or_material_produced",
    "P2652": "partnership_with",
    "P1037": "director_manager",
    "P3320": "board_member",
    "P3461": "designated_as_terrorist_by",
    "P137": "operator",
    "P98": "editor",
    "P5769": "editor_in_chief",
    "P131": "located_in_admin",
    # work
    "P1431": "executive_producer",
    "P344": "director_of_photography",
    "P1040": "film_editor",
    "P674": "characters",
    "P144": "based_on",
    "P840": "narrative_location",
    "P750": "distributed_by",
    "P921": "main_subject",
    # concept
    "P1269": "facet_of",
    "P3712": "has_goal",
    "P461": "opposite_of",
    "P3095": "practiced_by",
    "P5004": "in_opposition_to",
    "P1535": "used_by",
    "P3938": "named_by",
    "P61": "discoverer_or_inventor",
    "P828": "has_cause",
    "P1542": "has_effect",
    "P1537": "contributing_factor_of",
    # event
    "P710": "participant",
    "P276": "location",
    "P8031": "perpetrator",
    "P533": "target",
    "P1840": "investigated_by",
    "P156": "followed_by",
    # place optional political institutions
    "P6": "head_of_government",
    "P35": "head_of_state",
    "P194": "legislative_body",
    "P208": "executive_body",
    "P209": "highest_judicial_authority",
}


def qid_targets(claims: dict, pid: str) -> list[str]:
    out = []
    for st in claims.get(pid, []):
        if st.get("rank") == "deprecated":
            continue
        ms = st.get("mainsnak", {})
        if ms.get("snaktype") != "value":
            continue
        dv = ms.get("datavalue", {}).get("value", {})
        if isinstance(dv, dict) and dv.get("id"):
            out.append(dv["id"])
    return out


def main() -> None:
    conn = psycopg2.connect(**PG)
    cur = conn.cursor()
    cur.execute(
        """select external_ids->'wikidata'->>'id' from named_entities
                   where status='active' and merged_into_id is null
                     and external_ids->'wikidata'->>'id' is not null"""
    )
    library = {r[0] for r in cur.fetchall()}
    cur.execute(
        "select wikidata_qid from candidate_suggestions where review_status='pending'"
    )
    pending = {r[0] for r in cur.fetchall()}
    # qid -> entity_type (for source-type breakdown)
    cur.execute(
        """select external_ids->'wikidata'->>'id', entity_type from named_entities
                   where status='active' and merged_into_id is null
                     and external_ids->'wikidata'->>'id' is not null"""
    )
    qtype = {r[0]: r[1] for r in cur.fetchall()}
    conn.close()

    targets_by_pid: dict[str, set] = collections.defaultdict(set)
    srctype_by_pid: dict[str, collections.Counter] = collections.defaultdict(
        collections.Counter
    )
    for f in glob.glob(os.path.join(ARCHIVE, "Q*.json")):
        qid = os.path.basename(f)[:-5]
        src_t = qtype.get(qid, "?")
        with open(f) as fh:
            claims = json.load(fh)
        for pid in PROPOSED:
            tg = qid_targets(claims, pid)
            if tg:
                targets_by_pid[pid].update(tg)
                srctype_by_pid[pid][src_t] += 1

    rows = []
    for pid, label in PROPOSED.items():
        tgts = targets_by_pid.get(pid, set())
        new = tgts - library
        netnew = new - pending
        top_src = ", ".join(f"{t}:{c}" for t, c in srctype_by_pid[pid].most_common(3))
        rows.append((len(netnew), len(new), len(tgts), pid, label, top_src))
    rows.sort(reverse=True)
    print(
        f"library={len(library)}  pending_candidates={len(pending)}  archive_files={len(glob.glob(os.path.join(ARCHIVE,'Q*.json')))}"
    )
    print(
        f"{'NET-NEW':>7} {'NEW':>6} {'tot':>6}  {'PID':<7} {'field':<26} source-types(carrying)"
    )
    print("-" * 95)
    for netnew, new, tot, pid, label, top_src in rows:
        print(f"{netnew:>7} {new:>6} {tot:>6}  {pid:<7} {label:<26} {top_src}")
    print(
        "\nNET-NEW = new candidate ROWS added to the CURRENT pending queue (minus library, minus already-pending)."
    )
    print(
        "NEW = distinct not-yet-library targets (the formula for a fresh queue). tot = all distinct targets."
    )


if __name__ == "__main__":
    main()
