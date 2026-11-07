# Find novel relationships

The **novel-relationship candidate queue** surfaces pairs of entities that appear
together across your videos but have **no recorded Wikidata relationship** between
them — candidate relationships your knowledge graph does not yet know about. It is a
read-only measurement surface: a row proposes a *candidate*, nothing more.

## Generate the queue

Generation is an operator command (the only writer — the browser and API are
read-only):

```bash
# Preview: compute and report counts, write nothing
chronovista candidates relationships generate --dry-run

# Populate (or refresh) the queue
chronovista candidates relationships generate
```

Re-running is safe and idempotent: a still-qualifying pair is updated in place
(keeping its identity), new pairs are added, and pairs that no longer qualify are
removed. Only one generation runs at a time per channel.

## View the queue

- **Browser:** open the **Relationships** page (under the Entities group). Rows are
  ranked strongest-first; each links to both entities, with its evidence.
- **API:** `GET /api/v1/relationship-candidates` (lift-ranked, paginated). Query
  params: `limit`, `offset`, `eligible_only`, `min_support` (never below 5).

## Read a candidate

Each row shows:

- the **two entities** (each a link to its detail page);
- **shared videos** — how many of your videos mention both;
- **lift** — the size-normalised association strength the queue ranks by (strongest
  first); a high lift on a small shared count is the strongest signal, not an
  artifact;
- a **corroboration** indicator — how many captured properties the pair shares;
- a **measured-precision** badge when both entities have a typed profile (a trust
  signal, not a filter — all qualifying pairs are listed).

## What qualifies as a candidate

A pair qualifies when it co-occurs on the **title + description** channel with
**lift ≥ 5** and **at least 5 shared videos**, and has **no typed Wikidata tie** (no
direct edge, no shared membership, no shared country / place of birth / headquarters).
The ranking applies no further support floor by design.

## What it is for

The queue is a measurement instrument: look at the top of the ranked list and judge
whether these are real relationships worth capturing. The MVP asserts nothing and
writes no verdicts — it exists to inform whether a full confirm/reject workflow is
worth building.
