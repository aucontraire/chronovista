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

There are two ways to ask the question, and they read **different graphs**:

- **The `chronovista graph connect` CLI** reads a **dev-scoped** Neo4j you stand up yourself (the
  steps below). It is not part of the production stack.
- **The web Connection Explorer** (at `/connections`, documented under
  [In the web UI](#in-the-web-ui)) is served by the production app against the **production** Neo4j
  that now ships in the main Docker stack. You do not stand that one up by hand — it comes up with
  the rest of the stack.

Both are read-only, and both answer the same question with the same honest states; they differ
only in which graph they read and how you reach them.

!!! warning "The CLI path is dev-scoped"
    The `chronovista graph connect` command reads a local Neo4j graph you stand up yourself (the
    [prerequisite](#prerequisite-stand-up-the-dev-graph) below), built from a read-only snapshot of
    your data. The web explorer is the production-served path and needs no manual graph — see
    [In the web UI](#in-the-web-ui).

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

## In the web UI

The web Connection Explorer answers the same question in the browser, with an interactive graph and
an equivalent table. It lives at **`/connections`** and is served by the production app against the
production Neo4j in the Docker stack.

The graph is built from your database on demand. Build it once — and re-run whenever you want to
refresh it from newer data:

```bash
make graph-reload
```

The loader runs **inside the app container** (production Neo4j publishes no host ports), reads your
database read-only, and rebuilds all four layers. Until it has been built, the page honestly reports
*"not available yet"* and names this step — never a false *"no connection."*

### Open it and pick two entities

1. Go to **`/connections`** (for example `http://localhost:8765/connections`).
2. In **Entity A**, type at least two characters and pick an entity. The picker lists
   **graph-present entities first**; an entity that is in your library but *not in the current
   graph* is shown but **disabled** with a "not in current graph" note, so you are never led into a
   guaranteed dead end.
3. Pick **Entity B** the same way. The result loads as soon as both are chosen (and they differ).

!!! tip "Jump straight from an entity's 'Appears with' panel"
    Every row of the **Appears with** panel on an entity detail page has a **"How do these
    connect?"** action. It opens `/connections` with *both* endpoints already filled in — the page
    carries them in the address as `?a=<id>&b=<id>`, so the link is shareable and reproduces the
    same query.

### Read the graph

- The graph is an **interactive node-link view**: the two entities are the endpoints, with the
  connecting neighbourhood between them. Pan and zoom to explore; a legend explains the encoding.
- **Nothing depends on colour alone.** Connection kind is shown by **line style** — a solid line is
  a knowledge-base relationship, a dotted line is a shared category, and a dashed curve is the
  **co-occurrence overlay**. Node **role** is shown by shape, and a **category bridge node is sized
  by its specificity** (a narrow, meaningful category is drawn larger than a broad one).
- **Co-occurrence is a separate overlay**, drawn as a distinct dashed curve between the endpoints —
  never folded into the knowledge-base path, and shown even when a knowledge-base path also exists.
- Below the graph is an **equivalent table** (source, relationship, target, kind) built from the
  same data as the graph, so the two can never disagree. The table is the **keyboard and
  screen-reader path**: a "Skip to table" link jumps to it, and it conveys every node and edge the
  graph shows. A very large result hides the graph (to stay readable) and shows the table alone —
  tighten the controls if that happens.

### Tune the search

Two controls bound the result:

| Control | Effect |
|---|---|
| **Reach (hops)** | How far the knowledge-base search looks between the two entities. Minimum **3** (a lower reach reliably returns nothing, so it is not offered); default **3**. |
| **Largest category size** | The specificity floor — shared categories broader than this are ignored. Default **500**. |

### The five honest states

The web explorer never conflates these outcomes — each reads as itself:

1. **Connected** — the graph and table render the connection. A **human-reviewed *relationship***
   verdict reads as **connected** even when no chain was inferred (a confirmed tie the knowledge
   base may not state yet), shown as a "Reviewed: confirmed relationship" note plus a direct edge.
2. **No knowledge-base connection** — a "no path" result that still shows **each endpoint's
   knowledge-base coverage** (its count of KB facts) and a **link to each endpoint's external
   record**, so you can act on the gap. An endpoint that is not yet enriched gets a **"Look up on
   Wikidata"** fallback link rather than a dead end.
3. **Graph unavailable** — the graph is **rebuilding** ("try again in a few minutes") or has
   **never been loaded / can't be reached** (names the next action). This is never shown as "no
   connection" or as an error.
4. **Not in the current graph** — a chosen entity is valid in your library but absent from the
   current graph (the graph may be **older than your library**). This is distinct from "no
   connection": pick a different entity, or rebuild the graph.
5. **Error** — a generic request failure with a Retry button.

A **"Graph as of &lt;date&gt;"** line shows when the served graph was last built, so you can judge
how current it is.

## See also

- [How the connection explorer answers honestly](../architecture/connection-explorer.md) — the
  design: the tiers, the shape-split, log-specificity, the serving-state honesty contract, and why
  order is by kind.
- [Your first connection query](../getting-started/first-connection.md) — a guided walkthrough.
- [Find what entities have in common](entity-intersection.md) — the **Appears with** panel the
  web explorer deep-links from.
