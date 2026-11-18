# Your first connection query

This short walkthrough takes you from nothing to your first answer to "how are these two
entities connected?" — and shows you how to read it. It assumes you've already installed
chronovista and populated some data; if not, start with
[Installation](installation.md) and [Quick Start](quickstart.md).

By the end you'll have stood up the graph, run a query that finds a connection, and run one
that honestly finds none.

## 1. Start the graph

The connection explorer reads a local Neo4j graph, separate from your main database. Start it:

```bash
docker compose -f docker-compose.dev.yml --profile graph up -d neo4j-dev
```

Give it a few seconds, then load it from your data (read-only — this only writes to the graph):

```bash
./scripts/graph/reload_all.sh
```

You'll see it load entities, the knowledge-base layer, categories, and reviewed verdicts.

## 2. Run a query

Pick two entities you'd expect to be connected — each can be an exact name or an entity id:

```bash
chronovista graph connect "Entity A" "Entity B"
```

You'll get one line per kind of connection that exists. For a well-connected pair (names are
placeholders):

```
Entity A  ↔  Entity B
  asserted: Entity A —[FOUNDER]→ «Org X» ←[BOARD_MEMBER]— Entity B  (score 4.8)
  shared affiliation: both → «Award Y»  (AWARD_RECEIVED, score 13.9)
  listed by connection kind; a score ranks within its kind, not across
  discussed alongside (transcript): Entity A —[CO_OCCURS_TRANSCRIPT]→ Entity B
```

## 3. Read it

Three things to notice — they're what make the answer trustworthy:

- **`asserted`** is a *composed fact*: Entity A founded Org X, and Entity B is on its board. The
  arrows show the real direction.
- **`shared affiliation`** is `both → «Award Y»` — they *both* received the award. It's a
  co-membership, not a chain, so it's never written to imply one received it *from* the other.
- The note **"a score ranks within its kind, not across"** is a real caveat: the `4.8` and the
  `13.9` are on different scales. Don't read the top line as "the strongest" — read it as "the
  composed-fact kind".

## 4. Now find an honest "no"

Try two entities you wouldn't expect to be connected in the knowledge base:

```bash
chronovista graph connect "Entity A" "Unrelated Entity"
```

```
Entity A  ↔  Unrelated Entity
  no meaningful connection (searched within 4 hops) — KB coverage: «Entity A» 12, «Unrelated Entity» 0 edges
  ↳ «Unrelated Entity» is barely in the knowledge base — likely an enrichment gap, not a stated non-relationship
```

The tool doesn't just say "nothing". It tells you it *searched* (within 4 hops), and it tells you
*why* there's nothing: one entity has no knowledge-base edges yet, so this is an enrichment gap,
not a proven non-relationship. That distinction is the whole point.

## 5. Stop the graph (optional)

When you're done:

```bash
docker compose -f docker-compose.dev.yml --profile graph down
```

Run the same query with the graph stopped and you'll get a clean "Graph unavailable" message
with how to restart it — never a crash.

## Where to go next

- [See how two entities connect](../user-guide/connection-explorer.md) — all the options and
  output details.
- [How the connection explorer answers honestly](../architecture/connection-explorer.md) — why
  it's built this way.
