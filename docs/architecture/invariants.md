# System invariants

*Created 2026-11-25 · Last updated 2026-11-27*

This page lists what must stay true in chronovista, whatever a feature changes. Each entry says what the rule is, why
we know it matters, what enforces it, and how to check it on the data.

The register exists because, in a codebase this size, these rules were spread across tests, docstrings, local specs and
people's memory. Nobody could see them all at once. A feature could break one that an earlier feature relied on, and
every review checked only the rules its author thought of. A rule written only as prose is a reminder, and reminders
have already failed here. So every entry names its enforcement, or says plainly that it has none yet. Those entries are
the to-do list.

## How to use it

- **Specs and plans** name the invariants the feature touches, by ID, and say how the work will show each one still
  holds.
- **Pull requests** list the invariants they touch, add or change. A new rule and its guard land in the same PR.
- **Reviewers**, human or agent, get the entries for the area under review in their brief. Attack those entries, not
  only the ones the author chose.
- **Changes to production data** (repairs, backfills, rescans) are bracketed by the audit. Before:
  `chronovista audit-invariants --save backups/<name>.json`. After: `chronovista audit-invariants --compare
  backups/<name>.json`. The comparison fails on any violation that is new, even when a total fell. Saved runs hold
  library identifiers, so keep them in `backups/`.

**Adding an entry** needs a receipt: an incident, a measurement or a defect that shows the rule matters. A rule nobody
has broken and nobody depends on does not belong here yet. **Retire** an entry by marking it *Retired*, with the date
and reason; don't delete it.

### Statuses

- **Enforced:** a test fails if the rule is broken.
- **Partly enforced:** some paths are guarded and others are not; the entry says which.
- **Not yet enforced:** convention only.
- **Violated (measured <date>: <counts>):** broken on the data, and not yet fixed. It needs a fix and a guard.
- **Observation:** a measured fact with no receipt and no enforcement, kept so it is not rediscovered. It is not a rule
  and has no check.
- **Retired (<date>, <reason>):** no longer applies.

### Checks

An entry's **Check** line names its audit check, by ID, where one exists. `chronovista audit-invariants --list` shows
them all, and `--check <ID>` runs one; an entry ID (such as `T1`) runs every check for that entry. Entries about process
or code structure have no data check, and their Check line names their test or procedure instead.

## Transcript mentions

### M1: A stored mention reads as its text

Every positioned transcript mention reads as its `mention_text` at its offsets. Offsets index the segment's effective
text, which is the correction when the segment is corrected. A name split across segments is read across those segments
joined by one space.

- **Home:** `TranscriptTextIndex.mention_reads`. Nothing else compares a stored slice to `mention_text`.
- **Status:** Enforced in code: `tests/unit/architecture/test_mention_single_source_fitness.py` and
  `tests/integration/services/test_mention_correction_integrity.py`.
- **Check:** `M1-mention-reads`. It covers the mention repair's candidate transcripts only: segments with a correction,
  overlapping mentions of one entity, and corrected middles of names split across segments.
- **Receipt:** #426. On 2026-11-24, 428 production mentions were off their words, because corrections never moved
  existing offsets.

### M2: One row per occurrence

No two transcript mentions of one entity overlap in the transcript's assembled text.

- **Status:** Partly enforced.
  - The write paths (the correction writer, `scan --full` and the cross-segment pass) and the repair are tested in
    `tests/integration/services/test_mention_repair.py` and `test_mention_correction_integrity.py`.
  - The schema does not enforce it: `uq_entity_mentions_transcript` covers only an identical start, which is how the
    duplicates got in.
- **Check:** `M2-one-row-per-occurrence`, over the same candidate scope as M1.
- **Receipt:** #426. There were 324 surplus rows on 2026-11-24, most of them an alias recorded again inside a name split
  across two segments.

### M3: One answer to "where is this entity's name in this text"

Corrections, the repair and the scan all find names with one rule: diacritic folding, case-sensitive aliases, registered
ASR forms and longest-match-wins arbitration.

- **Home:** `EntityMentionScanService.detect_in_text`. Arbitration has its own single ranker.
- **Status:** Enforced: `test_mention_single_source_fitness.py` and `tests/unit/architecture/test_shadowing_invariant.py`.
- **Check:** none on data; the guards above.
- **Receipt:** #426. Corrections used a plain case-insensitive search that disagreed with the scan, so a corrected name
  and a rescan produced different rows.

### M4: One definition of a segment's effective text

A segment reads as its correction when it is corrected, and as its original text otherwise, by one definition.

- **Status:** Not yet enforced. There are several copies, and they differ for a corrected segment whose correction is
  missing or empty:
  - `effective_text` (in `services/transcript_text_index.py`) treats an empty correction as a correction;
  - the SQL twin in the evidence passages falls back to the original text;
  - the full-text rebuild reads a missing correction as empty;
  - about 15 inline copies repeat the rule.

  They agree on today's data: no corrected segment has a missing or empty correction (measured 2026-11-27).
- **Check:** none yet. Single-homing the rule, with a guard on access to the correction column, is planned.
- **Receipt:** the 2026-11-26 invariant sweep.

### M9: A mention's row shape matches its method and its segments

- A manual mention has no segment, position or end segment.
- An alias link appears only on a rule-matched mention.
- A mention's video and language are those of its start and end segments.

The rules come from the mention model's validator, which runs only when a mention is created through it. Raw updates
and bulk inserts bypass it, and the database has no matching constraints.

- **Status:** Partly enforced. The validator covers the create path; the audit covers the data.
- **Check:** `M9-mention-shape`.
- **Observation:** 1,172 historical manual mentions carry a confidence value, which the model now forbids (measured
  2026-11-27). Nothing reads it, so it is not checked.
- **Receipt:** the 2026-11-26 invariant sweep.

## Transcripts and corrections

### T1: A transcript's correction metadata agrees with its segments

- A transcript's "has corrections" flag is true exactly when one of its segments is corrected.
- Its correction count is the number of segments currently corrected ("active corrections", Feature 033 FR-014a).
  Correcting an already corrected segment adds a version, not a count.

- **Status:** Violated (measured 2026-11-27: 80 flags, 346 counts).
  - Every flag mismatch is a transcript whose language code has a region (for example `es-MX`). The correction service
    looks the transcript up by the lowercased code, misses it, and skips the update.
  - The count increments on every correction, but decrements only on a revert to the original.
- **Check:** `T1-correction-flag` and `T1-correction-count`.
- **Receipt:** the 2026-11-26 invariant sweep.

### T3: Re-downloading a transcript keeps its corrections and its counts

- **Status:** Partly enforced.
  - Corrections are safe today only because a transcript with corrections cannot be replaced at all: the correction
    table's foreign key is `ON DELETE RESTRICT`.
  - Replacing a transcript deletes its mentions, which cascade, and recounts nothing.
  - The code meant to keep corrections across a re-download has no caller.
- **Check:** none on data; C3 catches a counter left stale.
- **Design owner:** #126 (Transcript Refresh). It must reconcile corrections onto re-timed segments, including in videos
  edited after they were corrected.
- **Receipt:** the 2026-11-26 invariant sweep.

### T7: A corrected transcript's stored full text equals its segments

For every transcript with a corrected segment, the stored full text is its segments' effective text, joined with one
space in segment order, by the rule the full-text rebuild uses.

- **Status:** Violated (measured 2026-11-27: 133 transcripts).
  - The rebuild runs only after batch corrections, never after a single-segment correction.
  - It selects transcripts by the stored flag, so the 80 transcripts behind T1's flag mismatch are never rebuilt.
- **Check:** `T7-stored-full-text`.
- **Observation:** 392 uncorrected transcripts also differ from the rebuild rule (measured 2026-11-27). Their text was
  built at download by another rule, and some was later normalized. They are out of T7's scope.
- **Receipt:** the 2026-11-26 invariant sweep.

## Counting

"Counts" means one of two related rules. The association rule decides whether an entity is linked to a video. The
stored-counter rule decides `mention_count` and `video_count`. They differ only for manual mentions. Both live in
`repositories/entity_mention_repository.py`.

### C1: One rule per kind of count, shared by every surface

A mention that counts as an association on one page counts on all of them.

- **Home:** `_mention_qualifies_as_association` for associations, and `_mention_counts_toward_totals` for the stored
  counters. The latter's docstring explains why manual mentions differ.
- **Status:** Enforced: `tests/unit/architecture/test_asr_provenance_contract.py`,
  `tests/integration/api/test_videos_entity_filter_seam.py`, and
  `test_mention_single_source_fitness.py::test_what_counts_has_one_home`.
- **Check:** none on data; C3 checks the stored counters.
- **Receipt:** #262. Surfaces disagreed about whether an entity was in a video.

### C2: Clean-up never reduces what counts

When overlapping mentions of one entity are reduced to one (deduplication, repair, rebase), the one kept counts if any
of them did. Per entity and video, counted occurrences drop only when a row is proven stale or is a duplicate of another
counted row.

- **Status:** Partly enforced.
  - **The repair and the correction rebase** rank a counted row first. That is guarded by
    `tests/unit/repositories/test_mention_span.py`, and by the `TestWhatCountsIsKept` and `TestAuditMentions` classes in
    `tests/integration/services/test_mention_repair.py`.
  - **`scan --full` still violates it** until disfluency-gap matches count (#405).
- **Root cause:** two shipped rules conflict. Longest-match-wins keeps a disfluency-gap span over the clean name inside
  it, and the counting rules do not count gap spans. What the field does about disfluent mentions, and the intended fix:
  [Disfluency-tolerant matching](entity-name-matching.md#what-the-field-does-and-where-we-stand).
- **Check:** `chronovista entities audit-mentions --save <file>` before the change and `--compare <file>` after it. It
  measures what a known-good snapshot lost, which is the opposite of a violation check.
- **Receipt:** the #426 repair on production, 2026-11-24.
  - 28 occurrences across 21 entities stopped counting, and 6 entities lost a video from `video_count`.
  - Every row-level check passed. The owner found it by looking at an entity's per-video counts.

### C3: Stored entity counters equal a recount

Each entity's `mention_count` and `video_count` equal a recount of its mentions under the stored-counter rule.

- **Home:** `_entity_counter_recount`, shared by `update_entity_counters` (the writer) and the audit.
- **Status:** Partly enforced. The repair's counters are tested, but no guard covers every writer. Replacing a
  transcript's segments, for example, deletes mentions and recounts nothing.
- **Check:** `C3-entity-counters`. It held on 2026-11-27.
- **Receipt:** #89, and the v0.122.0 counter fix.

## Tags

### G1: Tag aliases sit on live tags, with their tag's form

No alias belongs to a merged tag, and every alias of an active tag has that tag's normalized form. Aliases of a
deprecated tag are allowed: deprecating a tag keeps its aliases by design.

- **Status:** Violated (measured 2026-11-27: 7 aliases). The alias-to-entity association path relies on this rule and
  does not check the tag's status.
- **Check:** `G1-alias-placement`.
- **Receipt:** #184 (13 orphaned aliases; two association paths disagreed), and #393.

### G2: A merged tag points to another tag and owns nothing

A merged tag has a target that exists and is not itself, keeps no entity link, and owns no aliases. No entity is linked
to more than one active tag.

- **Status:** Partly enforced: Pydantic validators on the create path only. It held on 2026-11-27.
- **Check:** `G2-merge-state`.
- **Receipt:** the Feature 064 merge rules; the 0.65.0 fix that made undoing a merge restore the entity link.

### G3: Active tag counters equal a recount

Each active tag's `alias_count` is its number of aliases. Its `video_count` is the number of distinct videos tagged with
one of its aliases' raw forms. A merged tag's counts are deliberately frozen.

- **Home:** `tag_alias_count_query` and `tag_video_count_query`, shared by the operator recount and the audit. They are
  guarded by `tests/unit/architecture/test_tag_recount_single_source_fitness.py`. Four older writers still count
  inline.
- **Status:** Violated (measured 2026-11-27: 7 tags). The orphan-alias repair (#185) moved aliases without recounting.
- **Check:** `G3-tag-counters`.
- **Receipt:** the 2026-11-26 invariant sweep.

## Transcript proximity

### P1: Mark the scope stale before removing or re-pointing a mention

Any write that removes or re-points a transcript mention marks the transcript's proximity scope stale first, in the
same transaction. Every correction path takes locks in this order, so a writer that does not can deadlock with them.

- **Status:** Enforced: the producers are counted exactly in
  `tests/unit/architecture/test_proximity_single_source_fitness.py`.
- **Check:** none on data; that guard.
- **Receipt:** Feature 117 (proximity kept current). A review of the #426 repair found it writing in the opposite
  order.

### P2: One rule for which mentions are evidence

The evidence panel and the proximity computation use the same mentions.

- **Home:** `positioned_transcript_mention_qualifies` (three call sites).
- **Status:** Enforced: `test_proximity_single_source_fitness.py`.
- **Check:** none on data; that guard.
- **Receipt:** Feature 117.

### P3: Proximity is keyed per segment pair

`uq_entity_pair_proximity_instance` is per segment pair, so duplicate mentions inside one segment do not change
proximity. A change to that key makes M2 matter for proximity too.

- **Status:** Enforced by the schema.
- **Check:** none on data; the unique constraint.
- **Receipt:** the first #426 write-up assumed duplicates inflated proximity. They do not.

## Changing production data

### D1: Data repairs are operator commands, not migrations

The app container runs `alembic upgrade head` on every start, so a data change inside a migration would run on
production unannounced, with no dry run and no backup.

- **Status:** Not yet enforced (convention).
- **Check:** review: a migration with data changes needs a stated reason.

### D2: A dry run reports exactly what the real run does

- **Status:** Partly enforced. It is enforced for `repair-mentions`
  (`test_mention_repair.py::...::test_a_dry_run_report_equals_the_real_runs_field_by_field`) and for the tag merge
  preview (`test_preview_equals_actual_merge`). For other bulk commands (scan, enrich, recover, seed, the whitespace
  backfill), tests show only that a dry run writes nothing.
- **Check:** each command's own test.
- **Receipt:** the #426 repair: its production dry run and real run agreed exactly. #293: a dry run projected 94,794
  where the real run did 90,294.

### D3: A second run changes nothing

- **Status:** Partly enforced: `repair-mentions` (`test_a_second_run_changes_nothing`, confirmed on production on
  2026-11-24) and the whitespace backfill. Other bulk commands are not covered.
- **Check:** each command's own test.

### D4: Before production, compare what users see

A change to production data is validated on a production copy by comparing the numbers users see, not only the tool's
own measures: counted occurrences and associations per entity and video, and the stored counters. Take a backup first.

- **Status:** Partly enforced. `audit-invariants --save` and `--compare` make the comparison mechanical; running it
  around a change is still process.
- **Check:** the procedure in "How to use it".
- **Receipt:** C2. The tool's own measures (stale 0, duplicates 0, idempotent) all passed while counted occurrences
  fell.

## The public repository

### R1: No library content in committed artifacts

These never appear in code, tests, docs, commit messages, or issue, PR or release text:

- entity names;
- video titles;
- the owner's account identifiers;
- the library's video, channel and playlist IDs;
- Wikidata QIDs.

- **Status:** Partly enforced.
  - **What runs:** `scripts/utilities/check_private_terms.py` runs as a pre-commit and commit-msg hook. It checks added
    lines for library names, and for identifiers matched by salted hash. `make pre-push` runs it over every tracked file
    (`--tree`).
  - **Known gaps:**
    - an identifier split across lines, base64-encoded, or broken by an invisible character is not caught;
    - channel handles and titles are not listed;
    - QIDs are not covered;
    - the term list is local, so CI cannot run the check.
- **Check:** `python scripts/utilities/check_private_terms.py --tree`.
- **Receipt:** the owner's own account identifier was found in 9 tracked test files on 2026-11-26. It had been there
  since August, because the term list held names only. The 2026-11-27 triage took the tree to zero findings.
