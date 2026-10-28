# Grow your entity graph

Once you have a handful of **grounded** named entities (entities linked to a
Wikidata item), chronovista can suggest *more* entities to add — by following the
relationships your existing entities already carry and checking which of those
related things actually appear in your own videos. You review the suggestions and
approve the ones worth keeping; each approval becomes a real, grounded entity.

This is the **seed-and-grow candidate queue**. It never creates entities on its
own — every entity comes from an explicit approval.

## Before you start

You need some **grounded, active** entities to grow from. If you have none yet,
generation produces an empty queue and tells you so — ground a few entities first
(see [Ground entities in a knowledge base](entity-enrichment.md)).

## 1. Generate candidates

```bash
chronovista candidates generate
```

This reads your grounded entities' stored relationships (offline — no network
call), keeps the targets that are not already in your library, measures how often
each one's name appears in your video titles and descriptions, scores and triages
them, and saves them to the queue. Re-running is safe: it refreshes still-pending
candidates and never disturbs ones you have already approved or rejected.

Preview without writing anything:

```bash
chronovista candidates generate --dry-run
```

## 2. Review the queue

```bash
chronovista candidates list
```

Candidates are ranked best-first by a plausibility score that favours specific,
corpus-present, well-corroborated names and pushes common or ambiguous single-word
names to the bottom. Narrow the list while you work:

```bash
chronovista candidates list --triage worth_review   # the bucket worth your time
chronovista candidates list --min-tokens 2          # hide single-word names
chronovista candidates list --type person --sort corroboration
chronovista candidates list --possible-duplicate    # only name-collision flags
```

Each row shows the score, corpus presence (`sal`), how many of your entities point
at it (`corrob`), its triage bucket, and a `⚠` when its name collides with an
existing ungrounded entity. Inspect one in full:

```bash
chronovista candidates show <candidate-id>
```

!!! note "Triage is advisory"
    The `likely_eliminable` bucket is a *ranking* hint, not a verdict — plenty of
    good candidates land there. Single-word names are always left for you to judge
    and are never created automatically.

## 3. Approve or reject

```bash
chronovista candidates approve <candidate-id>
chronovista candidates reject  <candidate-id>
```

Approving creates a grounded entity through the normal entity-creation path and
enriches it in the background. If the target already exists in your library (or was
added since you generated), approval recognises that and does not create a
duplicate. Rejected candidates are never suggested again.

## 4. Check progress

```bash
chronovista candidates summary
```

Shows counts by review status and the pending triage breakdown.

## Read the queue from the API

The queue is also exposed read-only, for a dashboard or script:

- `GET /api/v1/candidates` — the ranked pending queue (same filters as the CLI)
- `GET /api/v1/candidates/{id}` — one candidate with its provenance
- `GET /api/v1/candidates/summary` — the counts

Approving and rejecting are command-line only; the API never mutates the queue.

## See also

- [Ground entities in a knowledge base](entity-enrichment.md)
- [How seed-and-grow discovery works](../architecture/seed-and-grow.md)
