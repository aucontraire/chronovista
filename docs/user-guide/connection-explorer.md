# See how two entities connect

Ask how any two entities in your library are connected and get an **honest** answer — every
kind of link that exists between them, labelled for what it is, and a plain "no meaningful
connection" when there isn't one.

## Overview

`chronovista graph connect <a> <b>` answers one question: *how are these two entities
connected?* It searches a dev-scoped graph built from your library and the knowledge base, and
returns, strongest kind first:

- a **reviewed verdict**, if a human has judged the pair;
- an **asserted** chain — a composed path of stated knowledge-base facts (`A → … → B`);
- a **shared affiliation** — both relate to one knowledge-base node (`both → «X»`);
- a **shared category** — both sit under one Wikipedia category;
- **co-occurrence** — they appear together in your transcripts, titles/descriptions, or tags.

Everything is read-only. The command never changes a mention, an entity, or the graph.

!!! warning "This is a dev-scoped tool"
    The connection explorer reads a local Neo4j graph you stand up yourself (below). It is not
    part of the production stack, and it is built from a read-only snapshot of your data.

## Prerequisite: stand up the dev graph

The explorer reads a Neo4j container, not your Postgres database. Start it and load it once:

```bash
# start the dev Neo4j (a profile on the dev compose stack)
docker compose -f docker-compose.dev.yml --profile graph up -d neo4j-dev

# load entities, the knowledge-base layer, categories, and reviewed verdicts
./scripts/graph/reload_all.sh
```

`reload_all.sh` reads your data read-only and writes only to the local graph. If the graph
isn't running when you query, the command tells you so and exits cleanly — it never hangs or
prints a stack trace.

## Run a query

Pass two entities, each an **exact name or an entity id**:

```bash
chronovista graph connect "Entity A" "Entity B"
```

A pair with a real knowledge-base tie reads like this (names are placeholders):

```
Entity A  ↔  Entity B
  asserted: Entity A —[FOUNDER]→ «Org X» ←[BOARD_MEMBER]— Entity B  (score 4.8)
  shared affiliation: both → «Award Y»  (AWARD_RECEIVED, score 13.9)
  shared category: via «A narrow shared category»  (score 47.8)
  listed by connection kind; a score ranks within its kind, not across
  co-occurrence (distinct channels, listed by type — not ranked):
  discussed alongside (transcript): Entity A —[CO_OCCURS_TRANSCRIPT]→ Entity B
```

## Read the result honestly

A few deliberate choices make the output trustworthy rather than impressive:

- **Order is by kind, not strength.** A composed `asserted` chain is listed before a shared
  category, but the per-line **scores are within-kind only** — a chain's `score 4.8` and a
  category's `score 47.8` are on different scales and must not be compared. The explorer says
  so on its own line.
- **"Both → «X»" is not a chain.** When A and B both point at the same node, that's a *shared
  affiliation* (co-membership), rendered with "both → «X»" — never dressed up as a directed
  chain that would imply one is a member of the other.
- **A catch-all grouping is dropped, not shown.** If the only thing two entities share is a
  near-universal category ("both are living people"), it contributes nothing and is **not
  emitted** — you'll see a genuine weaker connection instead, or an honest none.
- **Absence is qualified.** When there's no knowledge-base path, the result says whether that
  looks like an *enrichment gap* (one endpoint has barely any KB edges) or a genuine
  non-relationship, and notes the hop bound it searched within:

```
Entity A  ↔  Entity B
  discussed alongside (transcript): Entity A —[CO_OCCURS_TRANSCRIPT]→ Entity B
  no asserted KB path within 4 hops — KB coverage: «Entity A» 1, «Entity B» 40 edges
  ↳ «Entity A» is barely in the knowledge base — likely an enrichment gap, not a stated non-relationship
```

!!! note "Reviewed as coincidental"
    If a human reviewed the pair's co-occurrence as *coincidental*, those co-occurrence lines
    are suppressed and replaced by a "reviewed as coincidental" note — the human judgment wins
    over the raw signal, but never suppresses an asserted or category tie.

## Options

| Option | Effect |
|---|---|
| `--max-hops N` | Hop budget for the asserted chain search (default 4, minimum 1). |
| `--max-category-size N` | A tractability bound: ignore shared categories larger than `N` (default: no cut — broad categories already self-suppress). |
| `--json` | Emit the full result as JSON — a stable, self-describing shape (kinds, scores, `kb_degree`, `any_truncated`, `reviewed_verdict`) for scripting. |

!!! tip "Scripting"
    The `--json` output always carries the per-endpoint `kb_degree` and the `any_truncated`
    flag even when the human output summarises them, so a script can distinguish "searched and
    found nothing within the bound" from "one endpoint is under-enriched".

## When the graph is down

Every failure is a clean, non-zero exit with a clear message — never a traceback:

- graph not running / unreachable / timeout / auth → "Graph unavailable" + how to start it;
- a name that matches several entities → the candidate ids, so you can re-run by id;
- a well-formed id that isn't loaded → "not in the loaded graph" (it may be stale);
- a name that matches nothing → "no entity named …".

## See also

- [How the connection explorer answers honestly](../architecture/connection-explorer.md) — the
  design: the tiers, the shape-split, log-specificity, and why order is by kind.
- [Your first connection query](../getting-started/first-connection.md) — a guided walkthrough.
