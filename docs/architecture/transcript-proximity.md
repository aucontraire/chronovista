# Transcript proximity

A record of **where two entities are discussed close together** in a transcript: the video, the
transcript language, the two passages, and how many seconds apart they are. It exists so a person
reviewing the knowledge graph can find, and then open, the moments where two entities come up together,
especially associations that the imported Wikidata/DBpedia relationships don't have.

Proximity **surfaces evidence; it does not infer relationships.** It never decides that two entities are
related, and it never writes to the relationship-candidate queue. A human reads the passages and gives
them meaning. The evidence panel reads it (since Feature 118: see
[Discussion passages](#discussion-passages-what-the-evidence-panel-shows) below), the graph view is the
next consumer, and the candidate queue reads it through its own threshold (see the end of this page).

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

## Discussion passages: what the evidence panel shows

The connection explorer's evidence panel turns a pair's records into **discussion passages** a person can
read (`GET /api/v1/graph/connect/passages`, Feature 118). It is built from the records themselves, so
the videos it lists are, by construction, exactly the videos proximity reports for that pair and
window. Agreement is a property of the design, not a hope two implementations share. A production
sample of 55 pairs (the densest, single-video pairs, multi-language pairs and random pairs) at all four
windows agreed in every case.

### From records to passages

The reviewer picks a **window**: 15, 30, 60 or 120 seconds, default 30. Every record within it is a
co-mention, and each co-mention gets a time **interval**: from the earlier of the two mentions' starts
to the later of their ends. A name split across a segment boundary ends in its end segment. Only
mentions that pass the shared rule give an end. The same entity can carry a rejected mention in the
same segment, and that must never stretch a passage.

The **passage rule** (version `118.0`) then works in two steps:

1. **Chaining, within one video and language.** Co-mentions are taken in time order. A co-mention joins
   the current passage when its start is at most one window after the latest end of the passage so far;
   otherwise it starts a new passage. So dense back-and-forth within a stretch is **one** passage, and two
   discussions ten minutes apart are **two**. Chaining has a documented consequence: a sustained
   conversation whose co-mentions keep arriving within the window becomes one long passage. That is
   intended. A passage is a stretch of nearby co-mentions, **not** a topic boundary: the rule says
   nothing about what was said.
2. **Grouping across languages, within one video.** A video with transcripts in several languages has
   the same discussion once per language. Passages of different languages whose time ranges overlap
   (one starts before the other ends) form one **grouped discussion passage**, transitively. When one
   language splits a discussion where another does not, all three passages still land in one group.
   Ranges that merely touch do not group.

The grouped discussion passage is the unit the panel counts. A translation never adds to a count, and
no count depends on which page is open, which language leads, or the order the two entities are given in.

### What a passage shows

- Its time range and how many co-mentions it holds.
- The **closest** co-mention's segments, with both names highlighted, and the segment after each mention
  dimmed as reading context. At most six segments, however long the passage.
- A link that opens the video with the player at that moment.
- The passage's other co-mentions as timestamps only.
- A **"Several names in one segment"** marker when the closest co-mention sits in one segment naming
  three or more library entities (a credits line or a panel introduction). Proximity knows this already:
  every pair of qualifying entities in one segment has a zero-gap record there. The marker never removes
  or discounts a passage.

Which language variant shows first follows the reviewer's language preferences (fluent, then learning,
then priority; `es-MX` matches `es`), and falls back to the closest co-mention. Without an established
identity the panel still works, closest first.

### Videos spoken farther apart

A video where both entities are spoken (qualifying mentions in the **same** transcript language) but
never within the window is not a passage video. It is reported as a separate count ("plus 9 videos where
both are spoken farther apart"), and can be listed nearest-first with the closest moment, so a false match
far from the other entity can still be audited (`/graph/connect/passages/farther`).

### Honest state

The panel reports the freshness of every transcript a pair's evidence depends on (the same set
`complete` is judged by, above):

- **Updating**: some transcripts are pending (stale, never computed, or retrying with fewer than three
  failures). The counts are shown but may change, and the panel refreshes itself until none is pending.
- **Could not be computed**: some transcripts are **failing** exactly as `proximity status` reports them
  (failed three or more times under the current rule). They are listed by video and language, never
  described as updating; `chronovista proximity retry-failed` retries them.

When there is no passage at all, the panel says which of these it is, in this order: still computing;
not spoken together in any transcript (naming a tag, title or description basis when there is one); or
no passage within the chosen window.

### How it reads, and why that way

Each request reads in one read-only snapshot (`REPEATABLE READ`), because the worker replaces scopes
while the panel reads and a count must come from the same moment as its rows. The co-mentions come from
two set-based statements: the records in the window, then the qualifying mention ends for just the
segments those records reference. Chaining and grouping then run in Python
(`proximity_service.chain_passages` and `group_across_languages`, where the rule is documented).

A single statement joining the records to the qualifying mentions was tried first and measured on
production. Postgres estimates the visible-name match (`lower(unaccent(text)) = name`) at one row, plans
nested loops on that estimate, and re-evaluates the whole mention set per record: up to 39 seconds for a
dense pair. The two-statement read takes about one second for the densest pair in the library.

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
