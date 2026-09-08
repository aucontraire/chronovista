# Resumable Entity-Mention Scan

The entity-mention scan walks every transcript segment (and, for the metadata
sources, every video title and description), matches each against the registered
entities and aliases, and writes the mentions it finds. Over a large library
this is long-running work. This note explains the transaction model that makes it
safe to interrupt and cheap to resume, and the guarantees that shaped it.

## The problem

The scan used to run as **one transaction that committed only at the very end**.
Two things followed from that:

- **Interrupting lost everything.** `Ctrl+C`, a dropped connection, or any
  mid-run error rolled back the whole run. Hours of detection work vanished and
  had to be redone from the start.
- **`--full` could shrink the library mid-run.** A full re-scan deleted *all* of
  a scope's existing mentions up front and only re-inserted them as it went. An
  interruption in that window left the affected entities with fewer mentions than
  they started with — a silent coverage loss until someone re-ran the scan.

A multi-hour open transaction is also a liability in its own right: it pins
database resources and blocks vacuum for the length of the run.

## The model: commit per batch, resume from a durable cursor

The scan processes segments (or videos) in keyset-ordered batches. Each batch is
a complete unit of work: detect, write, recompute the affected counters, and
**commit** — then move to the next batch. The longest-lived transaction is now
one batch, not the whole run.

After each commit, the scan reports the last committed position through a
checkpoint callback. The callback fires **after** the commit, never before, so
the persisted cursor can never point past durable data. That ordering is the
whole correctness argument for resume: a resume that starts from the saved cursor
can at worst repeat the one batch that was in flight when the process stopped, and
never skips a batch that was detected but not committed.

Resume state lives in a small **CLI-local JSON file**, not the database — resume
is an operator concern, and keeping it out of the schema means no migration and
no new table. The file is keyed by **scan scope** (a hash of the sources, entity
and type filters, video filter, language, and whether `--full` was set) and,
within a scope, by **source type** (`transcript` vs `metadata`). A `--resume`
only continues a run whose scope matches; change any scope input and it is a
different key, so a resume never applies a position from an unrelated run. A
completed source is recorded as such and skipped on resume rather than re-scanned.
A missing or corrupt file is treated as "no saved position" — the scan warns and
starts fresh rather than resuming from a bad cursor.

## Why `--full` is safe under interrupt

The upfront delete is gone. Under `--full`, each batch deletes the batch's own
`rule_match` / transcript-source mentions and re-inserts the freshly-detected
ones **in the same commit**. At every commit boundary a segment holds either its
pre-run mentions or its re-derived ones — never neither. The guarantee is
**atomicity per batch**, deliberately *not* a per-entity count floor: a
legitimate `--full` reduction (an alias was deleted, an exclusion added) *should*
lower a count, so a floor would be both wrong and unmeetable. What is guaranteed
is that no segment is ever observed mid-delete.

The delete is scoped by both segment/video id **and** source, so it only ever
touches machine-derived (`rule_match` / transcript / title / description)
mentions. **Manually added and correction-derived mentions are never deleted.**

## Counters stay consistent

Per-entity mention counts are recomputed from the mentions table for the entities
touched in each committed batch — including entities whose mentions were removed
by that batch's `--full` delete. Because the recompute reads the table rather than
adjusting a delta, it is idempotent and correct even if a batch is repeated on
resume. When a `--full` run completes, a final recompute runs across the whole
scope, so an entity that had stale counters but no rows in any scanned batch is
still reconciled.

## Failure isolation

A **detection-phase** failure on a single batch (a parsing error while matching)
is logged, counted, and skipped, and its cursor is advanced so a resume does not
re-hit the poison batch — one bad batch does not abort a multi-hour run. A
**write/commit-phase** failure aborts safely instead: the in-flight batch is
rolled back, every prior batch is already durable, and a resume re-does the
failed batch. The two phases are treated differently on purpose — a detection bug
should not cost the whole run, but a write that might be partial must not be
trusted.

## Scope and non-goals

- **No schema change, no migration, no new dependency.** Resume state is a
  CLI-local file.
- The metadata scan (`scan_metadata()`, title/description) has the **same**
  guarantees as the transcript scan, tracked as an independent source so a
  combined run resumes each source separately.
- The whitespace-normalization backfill
  ([Transcript whitespace normalization](transcript-whitespace-normalization.md))
  drives a per-video full re-scan; its mention outcome is unchanged — it now
  simply commits incrementally like every other scan.

## See also

- [Interrupt and resume a scan](../user-guide/scan-resume.md) — operator how-to.
- [CLI workflows](../user-guide/cli-overview.md) — the `entities scan` flags.
