# Transcript Whitespace Normalization

Caption text is matched literally in two places — batch-correction find/replace
and the entity-mention scan. When a caption puts an invisible or non-standard
whitespace character where a normal space belongs, a literal match silently
fails: a phrase or a multi-word name split across a line break is never found.
This note explains how segment text is normalized to close that gap, and the
consequences that shaped the design.

## The problem

The dominant case is a **line break inside a cue**: a caption wraps one cue
across two display lines, so `"Foo Bar"` is stored as `"Foo\nBar"`. Other cases
are **non-breaking spaces** (U+00A0), other Unicode spaces, **zero-width**
characters (U+200B/U+200C/U+200D/U+FEFF), and the **soft hyphen** (U+00AD).
Across the corpus these affect tens of thousands of segments — rare as a
fraction, but they saturate the tracks they appear on.

Because a literal scan cannot report what it *fails* to match, the missed
mentions and corrections are invisible: the only way to know they were lost is
to normalize and look again.

## Why normalize the *derived* text (and why that is lossless)

A segment's `text` is a **derived projection** of the caption file, whose
untouched original is retained in `video_transcripts.raw_transcript_data`.
Normalizing the derived `text` therefore loses nothing — the original is always
recoverable. This is what makes it safe to rewrite stored segment text rather
than only folding at match time.

Fixing the correction path in particular *requires* normalizing the stored text,
not just folding the search at match time: the correction replace rewrites the
stored string, so even if a folded search located a phrase split by a line
break, the replace would run against the raw text and change nothing. Clean
stored text is the only way both the find and the replace agree.

## Two folds, for two different jobs

There are deliberately **two** normalizations, because they serve opposite ends:

- **The stored-text normalizer** (`normalize_segment_text`, in `utils/text.py`) is
  **content-preserving**. It collapses whitespace runs to a single space, strips
  the invisibles, applies Unicode **NFC**, and trims — but keeps accents, case,
  emoji, currency, and non-Latin scripts. It is what ingest and the backfill
  write.
- **The match fold** (`_fold_diacritics`, in the scan) is **content-*reducing***:
  on top of the same whitespace/invisible handling it also strips diacritics and
  matching ignores case, so an accent-free, normal-spaced alias matches an
  accented, oddly-spaced occurrence. It is applied only for comparison; the
  stored text and the recorded mention text are never diacritic-folded.

### Why NFC is applied last

The normalizer strips invisibles *before* composing (NFC). A zero-width
character sitting between a base letter and its combining mark would otherwise
block composition; stripping it first, then composing, yields the precomposed
form. Applying NFC first would leave a decomposed pair that a second pass would
compose — breaking idempotency (and re-writing rows on every backfill run).

## The consequence that drives the backfill: mention offsets

Entity mentions store **character offsets** (`match_start`/`match_end`) into the
segment text, and a copy of the matched text. Two facts interact:

- A single-character substitution (line break → space, nbsp → space) **preserves
  length**, so offsets stay valid — but the stored `mention_text` still holds the
  old character until the mention is regenerated.
- Stripping an invisible or collapsing a run **shortens** the text, so every
  offset after that point **shifts**.

So re-deriving a segment's text necessarily invalidates its mentions' stored
positions. That is why the backfill does not merely rewrite text: after
normalizing a video's segments it **re-scans** that video, deleting and
regenerating its auto-detected (`rule_match`) mentions so their offsets and text
match the normalized segments. Hand-made and correction-derived mentions are
never auto-detected, so they are preserved untouched.

## What the backfill deliberately does *not* touch

- **Corrections.** A correction links to its segment by a stable id, not by text,
  so normalization never orphans one. Each correction also froze a snapshot of
  the pre-edit text; those historical snapshots are left as-is (an audit field),
  and the backfill never writes the corrections table.
- **The raw caption data**, which stays the lossless original.
- **The display-only full-transcript projection** (`video_transcripts.transcript_text`).
  It is built from a separate path and used only for the frontend full-text view,
  not for matching — and its inter-cue newlines are meaningful structure, so
  collapsing them would harm display rather than help. The matching paths this
  feature fixes read segment effective text, which *is* normalized.

## Delivery and safety

Ingest normalizes new segment text going forward. Existing transcripts are
cleaned by a one-time, operator-run CLI backfill (`transcript
normalize-whitespace`), never an Alembic migration — production applies
migrations automatically on container start, and a heavy ~80k-row rewrite plus
re-scan must stay under the operator's control (dry-run first, then `--apply`).

The backfill commits **per video**, so it is resumable, and it is **idempotent**:
a segment already normalized is a no-op, and re-scanning clean text reproduces
the same mentions. It re-detects a video whose segment text still carries an
artifact *or* whose mentions still do, so a run interrupted between normalizing
and re-scanning is picked up again — with one narrow exception it logs a warning
for: a length-shifting normalization followed by a hard process kill before the
re-scan leaves clean text and possibly clean mentions that resume cannot detect,
so the operator re-runs those named videos explicitly.

### Two accepted transient windows

Both are inherent to shipping the code before running the backfill, both
self-heal once the backfill runs, and neither loses data:

1. **Corrections** over still-dirty stored rows won't find a split phrase until
   the backfill normalizes them (the search pattern is normalized, but the stored
   text isn't yet).
2. A mention the scan **recovers** over still-dirty text carries the raw
   whitespace in `mention_text`; the SQL name-fold used by counters and
   alias-linking does not collapse whitespace, so that one mention is transiently
   under-counted / unlinked until the re-scan produces a clean `mention_text`.

The mitigation for both is simply to run the backfill promptly after deploying.

## See also

- [Work with transcripts](../user-guide/transcripts.md) — how to run the backfill.
- [Correct transcripts](../user-guide/corrections.md) — the correction workflow.
