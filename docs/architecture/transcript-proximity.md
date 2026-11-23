# Transcript proximity

A record of **where two entities are discussed close together** in a transcript: the video, the
transcript language, the two passages, and how many seconds apart they are. It exists so a person
reviewing the knowledge graph can find, and then open, the moments where two entities come up together,
especially associations that the imported Wikidata/DBpedia relationships don't have.

Proximity **surfaces evidence; it does not infer relationships.** It never decides that two entities are
related, and it never writes to the relationship-candidate queue. A human reads the passages and gives
them meaning. The graph view and the evidence panel are the intended consumers (later slices). Today
only the candidate queue reads it, through its own threshold (see the end of this page).

## Why proximity, not plain co-occurrence

Two entities appearing somewhere in the same transcript says little: in a long conversation almost
everything co-occurs with everything. What carries information is **closeness in time**. Two entities
mentioned within a few seconds of each other are being discussed together; two mentioned twenty minutes
apart are probably not. Proximity therefore records each close co-mention with its gap, so a consumer
can ask "within 15 seconds?" as easily as "within two minutes?".

## What a record is

One row of `entity_pair_proximity` (see the [schema reference](../reference/schema.md), group
*Transcript Proximity*) is one **close co-mention**:

- the entity pair, stored in canonical order (`entity_a_id < entity_b_id`);
- the `video_id` and `language_code`;
- the two transcript segments (`segment_a_id`, `segment_b_id`), so the passages can be shown; and
- `gap_seconds`, the distance between the two segments' **start** times.

Records are kept for every co-mention up to **120 seconds** apart. Narrower windows are filters at read
time: a co-mention is *within* a window `w` when the two mentions are in the same video and the same
transcript language and `gap_seconds ≤ w` (inclusive). A mention that spans two segments is positioned
by the segment where it starts.

**There is no eligibility threshold.** A pair close together in a single video is measured. (An earlier
design measured only pairs sharing at least five videos, which left most rarely discussed entities with
no proximity at all, and those are often the associations worth finding.)

## Which mentions count: one rule, shared with the evidence panel

Proximity and the evidence panel must count **the same mentions**, or a reviewer would open passages
the numbers never counted, or count passages they can't open. Both use one rule,
`positioned_transcript_mention_qualifies`. A mention counts when it:

- comes from a transcript and is anchored to a segment (a manual video-level tag has no position);
- is not a `manual` assertion;
- is *real*: its text matches one of the entity's **visible names** (its canonical name or an alias),
  or it was recovered from a known speech-recognition error (`asr_match`); and
- is not excluded: a manual "not about this" exclusion of the entity for that video removes it.

Each end of a pair is checked separately. A single-source guard (a test in
`tests/unit/architecture/`) fails if either surface stops using the shared rule.

## The language-scoping invariant

One video can carry several transcripts, one per language, and they transcribe the **same audio**,
so their timestamps are aligned. Pairing a mention in one language with a mention in another would
therefore **fabricate the strongest possible signal (a gap near zero) out of nothing**.

So the two mentions of a record must be in the **same transcript language**. This is a non-negotiable
correctness invariant held by a **mutation-verified guard**: removing the clause makes a multilingual
fixture produce cross-language records, and the guard test fails.

## Scopes and freshness

Proximity is computed per **scope**: one `(video, language)` transcript. The scope is the unit of work.
It is recomputed as a whole, and its records and its state change together in one transaction, so a
reader never sees a half-updated scope.

Each scope has a state in `proximity_scope_states`:

| State | Meaning |
|---|---|
| **not computed** | never computed yet |
| **current** | computed from the scope's latest transcript and mentions under the current rules (possibly with **zero** records, which is a real answer, not a missing one) |
| **stale** | the transcript, its mentions, or an entity's names changed since it was computed |

A scope is current when its `computed_revision` equals its `revision` and it was computed under the
current rules version. **"Not computed" and "zero records" are different answers**, and consumers can
tell them apart.

### What makes a scope stale

Every change that could alter which mentions count, or where they are, marks the affected scopes
stale **in the same transaction as the change** (so a change that fails to commit marks nothing):

| Change | Scopes marked |
|---|---|
| Entity scan writes or removes transcript mentions | the scanned `(video, language)` |
| Batch correction that tags an entity; reverting one | the corrected `(video, language)` |
| Transcript download or re-download | the downloaded `(video, language)` |
| Whitespace normalization of a transcript | every language of the video |
| "Not about this?" exclusion, restore, or undoing either | every language of the video (exclusions have no language) |
| Alias added, renamed, or removed; canonical name changed; undoing a rename or alias removal; a tag linked to an existing entity | every scope the entity appears in |

A name or alias change matters even when no mention row changes. Removing an alias leaves its mentions
in place, but their text is no longer a visible name, so they stop counting. Deleting an entity, video,
or segment needs no hook: the database cascades remove the records with them.

The set of call sites is pinned by a guard test, so adding or removing an invalidation call fails the
build and forces a review. (A guard can only count calls that exist: a new code path that changes
mentions and forgets to call it is caught by review and by the per-producer behavioral tests, not by
the count.)

### The recompute worker

The API process runs a **background worker** that recomputes stale scopes automatically: typically
within seconds of a change when nothing else is pending. Stale scopes are processed oldest first, so a
large backlog (a first deploy's full build, or an entity rename touching thousands of scopes) delays
newer changes until it clears, and nothing is recomputed while the API is stopped. On a first deploy
the worker creates a state row for every transcript and builds them all, without pausing between
batches (measured at production scale: about six minutes). Its state is reported by `/health`
(`proximity_worker`: `running`, `stopped`, `crashed`, or `disabled`, plus `last_cycle_at`).

If a scope fails to compute, the failure is recorded and retried later, waiting 30 s, then 60 s, then
120 s, and so on, up to an hour. After three attempts it is reported as **failing**, but it keeps being
retried. One failing scope never holds up the others. Brief database contention (a lock or deadlock)
is retried immediately and is not counted as a failure.

## Reading it

The repository offers three reads for consumers (internal methods; the evidence panel and graph slices
will expose them):

- **Scope states**: the state of each transcript scope of some videos.
- **Pair summaries**: for each pair, in one consistent read:
    - `videos_within_15/30/60/120`: how many **distinct videos** have a co-mention within each window;
    - `segment_pairs_within_15/30/60/120`: how many **segment pairs** do. This is mention density, not
      the number of separate discussions; a second transcript language of the same video adds to it,
      but not to the video count;
    - `min_gap_seconds`: the closest the two ever come; and
    - `complete`: `true` only if every scope that could contribute to the pair is current. Otherwise
      the numbers may still change.
- **Records for a pair**: each close co-mention within a window, closest first, with the video,
  language, and both segments, so the passages can be opened.

## Operating it

The worker keeps proximity current on its own. These commands are for a bulk build, for catching up when
the API is not running, and for inspection:

```
chronovista proximity status           # counts by state, failing scopes, oldest stale scope
chronovista proximity rebuild          # bring every scope current; resumable
chronovista proximity rebuild --force  # recompute everything, e.g. after the rules change
chronovista proximity rebuild --dry-run --video-id <id>   # preview counts; writes nothing
chronovista proximity drain            # what the worker does, without the API running
chronovista proximity retry-failed     # retry failing scopes now
```

`rebuild` works in small batches and publishes each scope as it goes, so interrupting it loses at most
the scope in progress. Running it again resumes: current scopes are skipped. Only one rebuild runs at a
time. Exit codes are `0` when everything requested is current, `1` on an error or when another rebuild
is running, and `75` when work remains (not `2`, which is the command-line usage-error code). See [the CLI overview](../user-guide/cli-overview.md#transcript-proximity).

## Relationship to the candidate queue

The novel-relationship candidate queue ([Novel-relationship discovery](relationship-discovery.md))
reads proximity's per-pair video counts for its transcript channel, and applies **its own** threshold
(at least five shared videos). Measuring everything does not flood the queue: the threshold belongs
to the consumer, not to the measurement.
