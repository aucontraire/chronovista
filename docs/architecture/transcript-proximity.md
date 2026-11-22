# Transcript proximity co-occurrence

A first-class, language-scoped record of how **close in time** two entities are discussed within a
transcript. It is the substrate for a forthcoming transcript-based relationship-candidate channel
and for semantic relation-extraction work; on its own it changes no user-facing surface.

## Why proximity, not plain co-occurrence

The novel-relationship candidate queue ([Novel-relationship discovery](relationship-discovery.md)) is
built from entities paired in video **titles and descriptions**. The obvious extension — pairs that
co-occur in *transcripts* — is degenerate at the video level: almost any two entities appear together
in *some* transcript, so the signal barely discriminates and a naive channel floods with incidental
co-presence ("a publication covers a person").

What discriminates is **intimacy, not breadth**: two entities mentioned *in the same breath* are far
more likely to be related than two mentioned twenty minutes apart. Proximity measures that — the
count of mention pairs within a short time window, and the single closest moment — so it up-weights
genuine co-discussion and down-weights broad co-presence.

## What it stores

Three tables (see the [schema reference](../reference/schema.md), group *Transcript Proximity*):

- **`entity_pair_proximity`** — one row per close co-mention *instance*: the entity pair, the
  `(video_id, language_code)`, the two transcript segments, and their `gap_seconds`. Instances are
  kept out to a generous 120-second outer window, so narrower windows (15/30/60s) are read-time
  filters rather than a baked-in constant, and the segment ids let a consumer render the actual
  passage.
- **`entity_pair_proximity_rollup`** — the per-pair aggregate consumers usually read: close-co-mention
  counts within 15/30/60s, the minimum gap, and shared-video breadth.
- **`proximity_dirty_scopes`** / **`proximity_generation_runs`** — the freshness queue and run log
  (below).

## The language-scoping invariant

One video can carry several transcripts — one per language — and they transcribe the **same audio**,
so their timestamps are aligned. An unscoped mention-pair self-join would therefore pair an entity in
the English transcript with another in the Spanish transcript at a near-identical timestamp,
**fabricating the strongest possible proximity signal (a gap of zero) out of nothing**.

The computor therefore joins only mentions in the **same transcript language**
(`a.language_code = b.language_code`). This is a non-negotiable correctness invariant, held by a
**mutation-verified guard**: removing the clause makes a multilingual fixture produce cross-language
instances, and the guard test fails. A pair-keyed table has nowhere to store "language", so the
guarantee lives in the computor itself.

## Keeping it fresh — the invalidation contract

Proximity is a derived aggregate, so every operation that changes the underlying entity mentions can
stale it. Freshness is kept by a **dirty-scope queue at the `(video, language)` grain**: each writer
of `entity_mentions` enqueues the scope it touched, and a drain recomputes those scopes.

| Trigger | Why |
|---|---|
| Entity scan (full / per-entity / per-video) | adds and removes mentions |
| Batch / find-replace correction | creates `user_correction` mentions (additive — corrections never move timestamps) |
| Alias delete / undo, whitespace re-scan, transcript download | change which mentions exist |
| "Not about this?" exclusion (F091) | marks **every** language of the video — exclusions have no language grain |

Entity deletion needs no hook (the foreign keys cascade). A drain lists dirty scopes, deduplicates by
video, runs **one** batched recompute, then deletes only the scopes that have not been re-marked
since — so an invalidation landing mid-drain is not lost.

## Operating it

```
chronovista proximity rebuild            # full build
chronovista proximity rebuild --video-id <id>   # scoped
chronovista proximity drain              # process the dirty-scope queue
```

A pair qualifies for computation by its **global** transcript shared-video count (support), never by
lift — so even a hub-anchored pair that a lift gate would bury is measured, which is exactly where
proximity earns its value.
