# Name Matching, ASR Recovery & Arbitration

The scan turns transcript text into **mentions** — rows tying a named entity to a
place it was said. Three problems make that harder than a substring search, and
this note explains how the matcher handles all three in one pass:

1. the same name is transcribed many ways, including garbled by automatic speech
   recognition (ASR), e.g. a name heard as *"jon smithe"* when the person is
   *John Smithe*;
2. a name can be split across a segment boundary, so neither segment contains it
   whole;
3. a shorter name is a substring of a longer one (*Marlowe* inside *Quade
   Marlowe*), and only one of them should win at a given position.

## One matcher, one pattern

Every form the scan recognises for an entity — its canonical name, its aliases,
and any admitted **ASR-error forms** (see below) — is compiled into a single
diacritic-folded, case-insensitive alternation, `\b(form1|form2|…)\b`. Folding
means an accented occurrence matches an unaccented alias and vice versa; the
`\b` anchors keep *"al"* from matching inside *"always"*. Building the pattern in
one place (`_build_entity_pattern`) is deliberate: the DB-loading path and any
caller that must match provisional names use the *same* rule, so the two matchers
cannot silently diverge.

Because detection folds diacritics, the matcher genuinely cannot tell two forms
that fold alike apart (`pena` vs `peña`). That limit shapes several decisions
below — provenance, alias linkage — rather than being worked around.

## ASR-error recovery, gated

An ASR-error form is a garble a human has confirmed stands for an entity (stored
in `entity_asr_errors`). Admitting these lets the scan recover mentions a clean
name match would miss. But a garble is low-signal, so admission is **gated** —
defence-in-depth, with the gates applied both in SQL when loading forms and again
in the matcher:

- **Multi-word only.** A single-token garble (*"jonsmithe"*) is rejected: one
  token is too collision-prone to trust.
- **No one-character token.** A form with a stray single-character token
  (*"smith a"*) is rejected.
- **Not all common words.** A form whose every token is a stop/common word
  (*"of the"*) is rejected.

A garble that survives the gates joins the entity's alternation like any other
form. **Collision precedence:** if a garble folds to the same value as a real
name of the entity, the real name wins — the garble's fold is subtracted from the
ASR set — so a form that coincides with a name keeps clean-match provenance.

## Suppressing a reviewed form

The gate keeps *low-signal* garbles out, but some admitted forms are still wrong:
a garble that is also a common phrase, an idiom, or a collision with a different
entity can pass every gate and still produce false matches. These are not
gate-sizing problems — the form keeps a distinctive token, so "all common words"
never fires — they need a human verdict. FR-011 adds that: a per-form reviewer
override, the `entity_asr_errors.usable_as_match_pattern` flag.

When a reviewer sets it to `false`, the form is suppressed from **matching** while
staying available to **corrections discovery**. That asymmetry is the whole point:
a wrong suppression costs a recovery, never a correction. The split is enforced by
two readers whose names carry the contract:

- `get_multiword_forms_for_matching` — the scan's match reader, which applies
  `usable_as_match_pattern = true`;
- `get_all_multiword_forms_for_discovery` — the corrections-discovery reader,
  which deliberately does **not** apply the flag.

A mutation-verified architecture guard asserts the ungated reader has exactly one
consumer, so no scan-side read can silently bypass the suppression (the failure
would be invisible — the ungated result is a strict superset, so nothing errors;
the extra matches just look like better recall).

A companion `suppression_reason` column records *why* a form is suppressed:
`zero_signal` for a permanent decision, `mostly_false_redundant` for a provisional
one that may be reversed once finer (video-scoped) disambiguation ships. Without
it, once every flagged row reads `false`, a later "un-suppress" could not tell a
permanent verdict from a temporary one.

Suppression is **prospective**: flagging a form stops it producing *new* matches;
its existing mentions clear on the next `--full` rescan, because the gate is read
at scan time rather than applied as a retroactive delete. The flag is a data-layer
control today — a reviewer-facing surface is a follow-on.

## Provenance: how a mention identifies where it came from

Each mention records a `detection_method`. Two matter here:

- `rule_match` — matched a canonical name or alias (a clean name match);
- `asr_match` — matched an admitted ASR-error form (a recovery).

Provenance lives on `detection_method`, never on `alias_id`: an `asr_match` row
always has `alias_id IS NULL` (an ASR garble is not a name, so it links to no
alias — the model enforces this). Keeping the two values distinct is what makes a
recovery **auditable** (the precision of recovered mentions can be sampled on
their own) and **revertible** (the whole recovery backfill is undone by
`DELETE WHERE detection_method = 'asr_match'`), and it keeps recovered rows out of
the `rule_match` population that regression baselines compare against.

Three detection-method *sets* govern how mentions are counted, deleted, and
spanned. Each has a single committed home so the sites that read it cannot drift
(a drift that has bitten this codebase before — the same literal list copied to
several sites, each failing differently):

| Set | Members | Home | Used by |
|-----|---------|------|---------|
| Transcript-derived | all non-`manual` methods | `_TRANSCRIPT_METHODS` | per-video mention **counts** |
| Rule-scan output | `rule_match`, `asr_match` | `_RULE_SCAN_METHODS` | the `--full` **delete** predicates |
| Spanning-capable | `rule_match`, `user_correction`, `asr_match` | `SPANNING_DETECTION_METHODS` | the cross-segment-span **validator** |

The rule-scan set deliberately **excludes** `user_correction`: corrections are
human-authored and not re-derived by a scan, so a `--full` rescan must never
delete them. It **includes** `asr_match`: a recovered row must be refreshed on a
rescan like a rule match, or — because the re-insert is `ON CONFLICT DO NOTHING`
— a recovered row whose match moved or whose ASR form was unregistered would
survive as a stale/duplicate row *silently*.

Because `user_correction` rows survive the delete, the conflict key
(`entity_id, segment_id, match_start`) cannot stop a scan from recording the same
occurrence again whenever the two rows start on different characters. So both
`--full` passes drop a scan match that overlaps a surviving mention of the same
entity, and the correction writer likewise skips an occurrence an existing mention
already covers (#426). Offsets stay comparable because every correction and revert
moves the segment's mentions with its text (`services/mention_offset_rebase.py`).

Two rules each have one home, guarded by exact-count fitness tests
(`tests/unit/architecture/test_mention_single_source_fitness.py`):

- **Whether a stored mention still reads as its text** is
  `TranscriptTextIndex.mention_reads`. A split name is read across all its segments
  joined, so halves that no longer meet do not read. Before #426 this was answered four
  different ways, and two of them disagreed.
- **Where an entity's name is in a text**, for code other than the scan itself, is
  `EntityMentionScanService.detect_in_text`: the scan's own matching rule (diacritic
  folding, case-sensitive aliases, registered ASR forms, longest-match-wins).

## Surfacing: qualification vs display

Every surface that answers "which videos mention this entity, and how often?"
(the entity's video list, the stored `mention_count`/`video_count`, the per-video
entity breakdown, the video-side panel, the provenance filter) gates on one shared
rule: a mention **qualifies as an association** when its text folds to a visible
name OR its detection method is **name-exempt** — `manual` (hand-asserted) or
`asr_match` (recovered). That rule lives in one place
(`_mention_qualifies_as_association`) that every surface reads, so a recovered
mention counts on all of them or none (the "#262" class of bug, where one surface
counts a mention another doesn't).

The subtlety that made this necessary: the qualification predicate historically
asked a single question — *does the mention text equal a visible name?* — which
silently conflated two different ones: **"is this mention real?"** and **"is its
text a name we can display?"** Those were the same question only because every
detection method until ASR recovery matched a visible name. An `asr_match` garble
is the first mention that is *real* (gated, theft-reviewed, precision-audited) but
whose text is deliberately *not* a name. So the two questions are separated:

- **Qualification** ("is it real?") admits `asr_match` — the recovery counts.
- **Display** ("is its text a name?") is unchanged — these surfaces still show the
  entity's **canonical name**, with the stored garble (`mention_text`, marked
  `detection_method='asr_match'`) available as detail. A transcript *preview*,
  which shows the actual spoken context, shows the garble there because that is
  what the transcript says.

## Arbitration: one longest-match-wins pool

At a given position only one match should win, and the longer one should: *Quade
Marlowe* beats *Marlowe*. The scan resolves this with a longest-match-wins pass
(`_apply_longest_match_wins`) over the full set of raw matches for a transcript.

The subtle part is that the same text is scanned twice — once per segment, and
once over the whole transcript concatenated (to catch names split across a
boundary). Historically those were two independent pools, so a boundary-spanning
match never competed with an overlapping in-segment match of a different entity.
They are now a **single pool**: the cross-segment pass already arbitrates spanning
and in-segment matches together, and when a spanning match wins it **suppresses**
exactly the in-segment mentions it overlaps — and only those. A non-overlapping
occurrence of the shorter name elsewhere in the transcript is kept untouched.

Matching and writing are split on purpose: the pool is widened to *match* every
competing span, then narrowed to the *write* scope after arbitration, so a
scoped single-entity scan still sees the competitors it must lose to.

## Spanning mentions and the `--full` contract

A spanning mention anchors on its first segment and records `end_segment_id` on
its last. The validator admits a span only from a `SPANNING_DETECTION_METHODS`
writer — the "transcript writer" invariant, never title/description/manual. A
boundary-crossing ASR garble therefore keeps its `asr_match` provenance rather
than being downgraded to a clean `rule_match` it is not.

Spanning rows are owned by the per-transcript cross-segment pass, not the
per-segment batch delete, because a span's source segments can fall in different
batches. Both deletes scope to `_RULE_SCAN_METHODS`, so a `--full` rescan refreshes
recovered spans and in-segment rows alike while leaving corrections and manual
links alone.

## Disfluency-tolerant matching

Spoken names are interrupted — *"Quade, uh, Marlowe"*, or a false start. A bounded
gap matcher admits a name split by a short filler (per-language filler lists, e.g.
English *uh/um*, Spanish *este/pues*) or a false start, scoped to the same
candidate entities the regex already considered. It is additive and never widens a
match past its bound.

### What the field does, and where we stand

Speech research has described the structure of a disfluency the same way since
Shriberg's work, on which the Switchboard corpus annotation is built. There is a
**reparandum** (what the speaker abandons), an optional **interregnum** (a filler
such as *uh* or *I mean*), and a **repair** (what they meant), written
`[reparandum + {interregnum} repair]`
([Zayats et al.](https://arxiv.org/pdf/1808.09091v1.pdf);
[Lou & Johnson](https://ar5iv.arxiv.org/html/1604.03209)). Applied to names:

| Transcript | Reparandum | Interregnum | Repair | Intended |
|---|---|---|---|---|
| *Quade Quade Marlowe* (repeat) | *Quade* | (none) | *Quade Marlowe* | Quade Marlowe |
| *Quade uh Marlowe* (filler) | (none) | *uh* | (the name continues) | Quade Marlowe |
| *Quade Mar Marlowe* (false start) | *Mar* | (none) | *Marlowe* | Quade Marlowe |

Four practices follow from the literature:

1. **All three are true mentions of the entity.** The speaker said the name each
   time.
2. **The entity is recognised on the fluent form, and the disfluency is kept as a
   separate annotation, not a reason the mention doesn't count.** Pipelines remove or
   mark disfluencies first, or model both together. Joint models use the entity
   signal to stop real names being deleted as disfluencies
   ([SLUE](https://arxiv.org/pdf/2111.10367);
   [Fillers in SLU](https://arxiv.org/pdf/2301.10761);
   [auxiliary sequence labeling](https://arxiv.org/pdf/2011.04512)). Systems that
   treat fillers as boundaries split one entity into unrecognised fragments
   ([Gladia](https://www.gladia.io/blog/named-entity-recognition-from-call-transcripts-improving-precision)).
3. **Entity spans in speech are where errors concentrate, so precision is measured
   at the entity level before a new kind of evidence is trusted**
   ([Why Aren't We NER Yet?, ACL 2023](https://aclanthology.org/2023.acl-long.98.pdf);
   [Deepgram](https://deepgram.com/blog/named-entity-recognition-voice-transcripts)).
   The ASR-error forms above went through exactly this review before they counted.
4. **The raw text stays as written, and the identified entity and how it was found
   are recorded beside it.** This is general text-annotation practice rather than
   something a speech source prescribes. It is also how `asr_match` already works:
   the stored text is the garble, the detection method is the provenance, and the
   row counts by provenance and can be reverted.

**Where chronovista stands (2026-11-25).**

- **What we follow:** the gap matcher finds all three kinds and stores the raw span,
  stumble included, so highlights are faithful.
- **What we don't:**
  - A gap match is recorded as `rule_match` with its raw text. Its text is not a
    registered name, so it **does not count**: no `mention_count`, no
    entity→video link, no proximity evidence. That breaks practices 1 and 2.
  - Longest-match-wins keeps the gap span over a clean name inside it, so a repeat
    turns a counted mention into an uncounted one, and every `scan --full` does
    this again.
  - The gap span does not record the form it matched (#405), which practice 4 needs.

**The intended fix:**
1. Measure the precision of the existing gap matches by kind (practice 3).
2. Give gap matches their own provenance, carrying the fluent form they matched.
3. Count them by provenance, as `asr_match` rows are counted.

Until then, the mention repair keeps a counted row over an uncounted one, and a
`scan --full` should be bracketed by `entities audit-mentions --save` and
`--compare`.

## Correction-time disambiguation

When a user's transcript correction maps a garble to an entity, the resolver links
it by exact adjacent-token context first, then falls back to the entities already
known in that video, and **skips** (recording a count) when the garble is
genuinely ambiguous — rather than picking an entity arbitrarily, the behaviour it
replaced.

## Rolling it out

Recovery is applied to existing data by a provenance-tagged, revertible backfill
(`entity scan --full` with ASR admission) that writes `asr_match` rows and never
touches `manual` or correction-derived mentions. Because provenance is a first-
class value, the backfill can be audited for precision and reverted whole without
disturbing anything a human authored.

## See also

- [Alias→mention provenance](entity-alias-provenance.md) — how a mention is tied
  to the alias that produced it, and undoable deletion.
- [Resumable entity scan](entity-scan-resumability.md) — how `--full` batches and
  resumes.
- [Recovery provenance](recovery-provenance.md) — deleted-video recovery sources.
