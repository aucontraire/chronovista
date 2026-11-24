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
  connecting neighbourhood between them. Pan and zoom to explore; a **colour key** explains the
  encoding (and is also shown in full-screen).
- **Nodes are colour-coded by entity type** — person, organization, place, work, event, and so on —
  with the key naming every type currently on screen. Two structural node kinds read as muted
  neutrals, kept visually distinct from the typed colours: a **shared-category** node (a sand
  diamond, **sized by its specificity** — a narrow, meaningful category is drawn larger than a broad
  one) and a **reference value that is not an entity in your library** (a muted sage node with a
  dashed outline — the target of a fact such as *educated at* or *position held*). Entities whose
  type is uncategorised fall back to a neutral grey.
- **Nothing depends on colour alone.** Connection kind is shown by **line style** — a solid line is
  a knowledge-base relationship, a dotted line is a shared category, and a dashed curve is the
  **co-occurrence overlay**. Node **role** is shown by **shape**, every node carries a **text
  label**, and the equivalent table below conveys everything the graph does — so the colour coding
  is an extra channel for reading the graph, never the only one.
- When both entities are chosen, each gets a small card with a link to its **external record** (or a
  **"Look up on Wikidata"** fallback when it isn't enriched yet) and its internal **Entity page** —
  available while you explore, not only on a "no connection" result.
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

### The evidence panel

Below the graph and table, the panel shows **where the two entities are discussed together** in your
transcripts: the stretches of speech where both come up within a few seconds of each other. A count
("they share N videos") can't be checked by eye; a passage can. This is where you read what was said,
and where you catch a false match (a name collision, or a common word that is also an entity name).
The panel shows co-mention, never a relationship: you decide what a passage means.

**Choose how close is "close".** The **Mentioned within** selector offers 15, 30, 60 and 120
seconds (30 by default), measured between the starts of the two mentions. Everything follows it: which
videos are listed, how passages are merged, and every count. The choice is saved in the page address,
so a refresh or a shared link reopens the panel with the same window.

**Read the summary first.** For example: *"7 discussion passages across 4 videos, 3 channels; closest
mentions 6 s apart."* A **discussion passage** is a stretch of one video where the two keep being
mentioned within the window of each other. Two discussions ten minutes apart are two passages; rapid
back-and-forth is one. A long, sustained conversation can be a single long passage: that is how the
rule works, not a judgement that it was one topic. A video with transcripts in several languages counts
**once**, and so does each discussion: translations never inflate a count.

**Then read the passages.** Videos come closest-first. Under each video:

- Each passage shows its time range, how many co-mentions it holds, its own closest gap ("closest 9s
  apart"), and the text around its **closest** co-mention, with both names highlighted. The video's
  header line gives the closest gap over all its passages, which is how videos are ordered.
- The segment after each mention is shown dimmed, so a name split across two transcript lines reads
  whole, and it is highlighted on both lines. A "…" marks transcript text left out between the shown
  lines.
- **Open at m:ss** opens the video with the player at that moment and the transcript scrolled there.
- **Other moments in this passage** lists the passage's other co-mentions with both mentions' times,
  for example "0:12 → 0:25 · 13s apart". The link jumps to the earlier one. Several rows can share a
  start time when one mention pairs with several later ones; the second time tells them apart.
- **Also in N other transcripts** shows the same discussion in the video's other languages. The
  language shown first is your preferred one (set under Settings → Languages: fluent first, then
  learning); without a preference, it is the language with the closest co-mention.
- **Several names in one segment** marks a line that just lists names, such as credits or a panel
  introduction. It still counts; the marker helps you skim past it.
- A video with many passages shows the first three; **Show N more passages** reveals the rest in place.

**Videos where both are spoken farther apart.** When both entities are spoken in a video but never
within the window, that video is not a passage. The summary adds *"Plus N videos where both are spoken
farther apart"*; open it to list them nearest-first with the closest moment. This is the place to
audit a mention that sits far from the other entity. Widening the window moves the nearer ones into the
passages.

**When the numbers are not final.** Corrections, scans and new transcripts are measured in the
background, usually within seconds:

- **"Updating: N transcripts are being recomputed"**: the counts are shown but may change, and the
  panel refreshes itself until the work is done.
- **"N transcripts could not be computed; counts may be incomplete"**: open it to see which videos and
  languages. See [Troubleshooting](../troubleshooting.md#the-evidence-panel-says-could-not-be-computed).

**When there is no passage**, the panel says which case it is: *not computed yet* (it updates itself),
*not spoken together in any transcript* (naming the tag, title or description link when there is one),
or *no passage within* the chosen window (with the farther-apart videos, if any).

The panel reflects your **live** library, while the graph edges are a periodic snapshot. Just after
you exclude a false mention, the panel drops it before the edges do, until the next graph rebuild.

To act on a false match you spot here, exclude it with the existing entity–video exclusion tooling;
the next graph rebuild then drops it from the edges too.

### Explore mode: the whole neighborhood

Connect answers "how are these two related?" with the single cleanest path. **Explore** answers a
different question — "what's *around* these entities?" — by drawing a bounded **neighborhood
subgraph**: the entities, their neighbors, and the edges among them, the way a Neo4j/AuraDB query
result looks, rather than one pruned thread.

- Switch with the **Connect / Explore** toggle. Your selected entities carry over, and the mode is
  in the URL (`?mode=explore`), so an Explore view is linkable.
- Explore seeds from the entities you've chosen (one or both) and shows the **union** of their
  neighborhoods. It loads up to 60 nodes at first — a legible starting view, not the whole graph.
- **Trust layers.** Every edge is labeled by how far it can be trusted, and each layer toggles on
  its own:
    - **Verified** — a knowledge-base fact (or a human-reviewed relationship). Solid, prominent.
    - **Category** — a shared Wikipedia category. Dashed, de-emphasized.
    - **Co-occurrence** — the two were merely *discussed together*; **not** a stated relationship.
      Faint, dotted, a distinct colour — and **off by default**. Turn it on deliberately.
  The styling never relies on colour alone, so a co-occurrence hint can't be mistaken for a fact.
- **Grow outward.** Double-click a node — or use the **Expand** control in the table row (the
  keyboard path) — to add that entity's neighbors *in place*, without disturbing the layout you've
  arranged. The graph accumulates up to a ceiling (250 nodes); past that it tells you it's full and
  stops, rather than dropping what you're looking at.
- **Focus the view.** Busy neighborhoods pare down without losing your place: the colour **key
  doubles as a filter** — untick an entity type to hide its nodes (the two endpoints always stay) —
  and a **relationship-type list beside the table** (with **Show all / Hide all**) hides whole kinds
  of edge, such as every "in category" link at once. Both work in the maximized view too, and every
  filter applies to the graph and the equivalent table together, so the two never disagree.
- **Hover a node** to read its full name when the on-canvas label is truncated (the table always
  carries the full names for assistive tech).
- **"Showing N of M nodes"** tells you how much of the available neighborhood is on screen.
- **Maximize** gives a dense neighborhood room: the graph fills the window (Esc exits), with a
  pared-down toolbar; the node cap still applies, so it's more space, not an uncapped hairball.
- **Your arrangement is remembered.** Move nodes or change the zoom, navigate away, and come back:
  the graph returns exactly as you left it — positions and zoom — instead of reshuffling into a fresh
  layout. (A full page reload still re-lays out, and nodes you expanded aren't restored across
  navigation yet.)

Explore is strictly read-only: it draws only relationships already in the graph and never infers a
new one — that is a separate, deliberately-not-built capability.

## See also

- [How the connection explorer answers honestly](../architecture/connection-explorer.md) — the
  design: the tiers, the shape-split, log-specificity, the serving-state honesty contract, and why
  order is by kind.
- [Your first connection query](../getting-started/first-connection.md) — a guided walkthrough.
- [Find what entities have in common](entity-intersection.md) — the **Appears with** panel the
  web explorer deep-links from.
