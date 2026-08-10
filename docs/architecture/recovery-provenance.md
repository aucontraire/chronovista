# Where recovered metadata came from

When a video is deleted or made private, YouTube stops answering questions about
it. Its title, channel and description can still be reconstructed from archives —
but once they are, the row looks exactly like any other row. Nothing in it says
*this came from an archive*, or *which one*, or *when*.

This page explains how that attribution is recorded, and why it is stored
additively rather than as a single value.

---

## Recovery has more than one source

Three routes can contribute metadata for an unavailable video, and none of them
is sufficient alone:

| field | Takeout export | Web archive | Third-party index |
|---|---|---|---|
| title | yes | yes | yes |
| channel | yes | yes | yes |
| description | no | **only source** | no |
| duration | no | no | **only source** |

A single row can therefore hold a title from one source, a description from a
second and a duration from a third. That is the normal case, not an edge case.

## Why a single column could not hold it

The original design stored provenance in one `varchar` per row — the model you
would choose when there is exactly one source, which is what existed at the time.
Two things follow from it, and both caused real damage.

**Whichever pass ran last claimed the whole row.** A bulk import in August 2026
wrote the column unconditionally on every row it touched. 92 rows that had been
recovered from a web archive months earlier were relabelled as coming from the
importer. No video data was lost — the titles and descriptions written by the
earlier pass were still there — but the record of where they came from was gone.

**Two facts were packed into one string.** The convention was
`source:snapshot_timestamp`, so the archive's capture timestamp lived *inside*
the source value. Overwriting the source destroyed the timestamp with it. Worse,
the loss was not detectable from the data afterwards: the obvious heuristic —
"the importer never writes descriptions, so an importer-sourced row that has one
must have come from somewhere else" — is wrong, because most such descriptions
came from the original sync.

## The model

Provenance lives in an append-only join table, one row per (target, source):

```
video_recovery_sources
  video_id       -> videos.video_id, ON DELETE CASCADE
  source          'takeout' | 'wayback' | 'filmot' | 'sync'
  source_detail   nullable; e.g. an archive snapshot timestamp
  recovered_at    when this source contributed
  fields_written  nullable; what this pass actually wrote
  PRIMARY KEY (video_id, source)
```

`channel_recovery_sources` has the same shape, keyed on `channel_id`.

Three properties matter:

**`source` and `source_detail` are separate columns.** Packing them into one
string is what destroyed the snapshot timestamps. Structured data has no
equivalent failure mode.

**The primary key is (target, source), not a surrogate.** A source that runs
twice — a retry, or a second pass filling a gap it could not fill before —
refreshes its own row and leaves every other source's row untouched. That is the
whole invariant, expressed as a constraint rather than as a rule each caller has
to remember.

**`fields_written` is a hint, not a guarantee.** It gives a cheap approximation
of per-field provenance without rewriting every adapter. A pass that does not
populate it degrades to "this source touched this row" — still more than the
previous model could say. Consumers must never treat it as complete.

## The denormalised column is derived

`videos.recovery_source` and `videos.recovered_at` still exist, and the API still
exposes them unchanged. They now hold a projection of the join table — the most
recent contributor — so the video detail endpoint does not need a join per row to
render a banner.

This is deliberately a second copy of a fact, which is the pattern that caused
the original problem. The mitigation is that **exactly one code path writes
them**, and it recomputes from the join table rather than trusting whatever the
caller passed. That path is `RecoveryProvenanceRepository`; no recovery adapter
writes the column directly.

For backward compatibility that projection still rebuilds the packed
`source:detail` form, because existing readers consume that shape. New readers
should use the join table. The column can be dropped once none do.

## What this does not record

**Failed attempts.** This table records what *succeeded*. "We tried the archive
for this video and it had no capture" is a different question — a property of the
process rather than of the data — and it has its own unresolved design questions
around retention and expiry. The two share a principle (append, never overwrite)
and are deliberately not sharing a table until those are answered.

**Transcript sources.** `video_transcripts.source` looks like the same problem
and is not. A transcript row has exactly one source by nature — one fetch
produced one transcript — and it never accumulates contributions. It stays
single-valued.

**Per-field provenance.** Which source wrote *this particular column* is
answerable only approximately, via `fields_written`. A table keyed on
(target, field, source) would answer it exactly, at the cost of every write path
recording per field. No consumer needs that today.

## Consequences worth knowing

Recovery is now **auditable per source** — "show me everything one pass wrote" is
a query, which makes a bulk import reviewable and reversible.

Attribution is **restorable**. The 92 rows above were repaired by adding the
archive rows *alongside* the importer's, so both facts are true at once. Under
the previous model that restore was not possible to do correctly: writing the old
value back would have erased the fact that the importer had also contributed,
replacing one inaccuracy with another.

Availability semantics are **unchanged**. Recovery does not modify
`availability_status`; a recovered video is still an unavailable video whose
metadata happens to be known.
