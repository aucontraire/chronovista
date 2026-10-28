# How seed-and-grow discovery works

The seed-and-grow candidate queue grows the entity knowledge graph *outward from
entities that already exist*. This page explains the model and the decisions behind
it; for the commands, see [Grow your entity graph](../user-guide/candidate-queue.md).

## The problem it solves

Grounded entities carry relationships to other things — a person's employer, a
work's creator, an organisation's parent. Most of those related things are **not**
entities in your library yet; the relationship points at an external Wikidata item
and dangles there. The graph stays sparse not because the edges are unknown but
because the nodes on the far end were never created.

Seed-and-grow turns those dangling targets into reviewable candidates.

## Two channels, one queue

There are two complementary ways to discover candidates, and the store is designed
to host both:

- **Relation channel (implemented).** Follow a grounded entity's stored
  relationships to their targets. Requires existing grounded "seed" entities, so it
  is a *growth* activity — it presupposes you have already climbed the first rung.
- **Tag-seed channel (future, cold-start).** Classify normalised tags as likely
  people/places/organisations and offer them as the *first* seeds, for a brand-new
  library that has no entities yet. Its input (normalised tags) is something every
  imported library has on day one, which is why it — not this feature — is the part
  that genuinely belongs in onboarding.

Every candidate carries a *source channel* and channel-specific provenance, and all
channels share the same store, scoring, review, and approval machinery. This feature
implements the relation channel; the tag-seed and shared-category channels are
future producers that write into the same queue rather than parallel systems.

## The pipeline

1. **Emit (offline).** Read each grounded, active entity's already-stored
   relationship data and keep the targets that are not already library entities.
   This reads stored data only — no network call — so generation is fast,
   deterministic, and unaffected by knowledge-base outages. A target's coarse type
   is inferred from the relationship that produced it (a spouse relationship implies
   a person; a headquarters relationship implies a place); when relationships
   disagree the type falls back to a catch-all.
2. **Ground.** Measure how often each candidate's name appears in the local corpus
   of video **titles and descriptions**, using the *same* detection rule the scanner
   applies to registered entities — the shared pattern builder, not a re-implemented
   matcher. Reusing one rule means a name "found" during discovery is a mention the
   real scanner would reproduce. Transcripts are excluded (their ASR noise would
   inflate presence).
3. **Score.** Rank by a specificity-weighted presence: raw presence divided by the
   name's commonness, with a mild boost for corroboration (how many of your entities
   point at the target). A common single word that appears everywhere scores *low*,
   not high; a specific, present, well-corroborated name scores high. The score only
   ranks — it never rejects.
4. **Triage.** Each candidate gets an advisory bucket — *grounds-nowhere* (absent
   from the corpus), *likely-eliminable* (the common/ambiguous profile), or
   *worth-review* — so the reviewable set stays tractable. The buckets sort the
   queue; they never decide it.

## Why nothing is created automatically

A measured review of real candidates showed that single-word names are a
high-variance mix of genuine one-word entities and ordinary vocabulary that only a
human can separate — the auto-flag that looked eliminable was kept by the reviewer
most of the time. So the system **never** auto-creates: every entity results from an
explicit human approval, and single-token names always require review. Approval
reuses the normal entity-creation and enrichment path, so an approved candidate is
indistinguishable from a hand-created grounded entity (its discovery provenance lives
in the candidate record).

## Durability and reconciliation

The queue is durable and resumable. Re-running generation refreshes the signals on
still-pending candidates but never touches a candidate you have already approved or
rejected, and a rejected candidate is never offered again. If a candidate's identity
becomes a library entity by other means between runs, it is retired as *superseded*
rather than left pending or duplicated. Approval is idempotent against duplicates:
an identity already grounded, or a name-and-type that already exists, supersedes the
candidate instead of creating a second entity.

## Relationship to onboarding

This feature is the growth half of the system, not an onboarding step: it needs
seeds, and a day-one library has none. The onboarding pipeline is a set of steps
whose status is derived from live database counts; a future tag-seed step would slot
in there, keyed off a count the queue already exposes. The read-only summary
endpoint is shaped so such a step could read a single number — which is why the
queue is designed to be *onboarding-ready* without adding an onboarding step here.

## Browser review (Feature 097)

The whole loop — generate, triage, approve/reject — is available in the browser, so
no step requires the command line.

- **Generation runs as a background job with a persisted run record.** Triggering a
  run returns immediately and launches a detached task; the run's status and a
  determinate completion percentage live in `candidate_generation_runs`, not in
  process memory, so the live percentage is readable whichever worker answers a
  status poll, a crashed run is detectable (a stale `updated_at` heartbeat reads as
  failed), and a partial unique index on the running row enforces one run at a time.
- **Approval detaches enrichment.** The approve endpoint reuses the review service
  but schedules the on-approval property fetch as a detached task *after* the entity
  and verdict commit, so the request is never held across enrichment's network
  calls.
- **The tag footprint claims unclaimed tags only.** Approving an entity surfaces how
  many additional videos linking a name-matching canonical tag would associate — the
  tag's videos minus those already associated with the entity, so the count never
  double-counts. Linking reuses the existing classify operation. Moving a tag that is
  already linked to another entity is deliberately *not* supported here: the only
  re-classify primitive deletes the prior owner when forced, so safe re-assignment is
  left to its own future operation.
