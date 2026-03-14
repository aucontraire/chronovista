# Transcript Corrections

Guide to finding and fixing ASR (automatic speech recognition) errors in transcripts using `chronovista corrections`.

## Overview

ASR engines frequently misrecognize proper nouns, acronyms, and names — especially in multilingual content. The corrections CLI provides:

- **Find-replace** with substring or regex matching
- **Word boundary regex** (`\b`) for precise targeting
- **Cross-segment matching** for names split across two adjacent segments
- **Batch revert** to undo corrections
- **Dry-run mode** to preview all changes before applying

---

## Quick Start

```bash
# Preview a simple substring replacement
chronovista corrections find-replace \
  --pattern 'amlo' --replacement 'AMLO' --dry-run

# Apply it (with confirmation prompt)
chronovista corrections find-replace \
  --pattern 'amlo' --replacement 'AMLO'

# Undo it
chronovista corrections batch-revert \
  --pattern 'AMLO' --dry-run
```

---

## Find-Replace Modes

### Substring Mode (default)

Matches the pattern as a literal substring anywhere in the segment text. Case-sensitive by default.

```bash
# Exact substring match
chronovista corrections find-replace \
  --pattern 'amlo' --replacement 'AMLO' --dry-run

# Case-insensitive substring match
chronovista corrections find-replace \
  --pattern 'amlo' --replacement 'AMLO' \
  --case-insensitive --dry-run
```

**When to use**: Simple word or phrase replacements where you know the exact text.

**Watch out**: Substring mode matches inside longer words. `--pattern 'amlo'` will also match "k**amlo**ops". Use regex with `\b` word boundaries to avoid this (see below).

### Regex Mode (`--regex`)

Treats the pattern as a Python regular expression. Use this when you need word boundaries, wildcards, or flexible matching.

```bash
# Match "amlo" as a whole word (not inside "kamloops")
chronovista corrections find-replace \
  --regex --pattern '\bamlo\w*' --replacement 'AMLO' --dry-run
```

**Key regex features**:

| Syntax | Meaning | Example |
|--------|---------|---------|
| `\b` | Word boundary | `\bamlo\b` matches "amlo" but not "kamloops" |
| `\w*` | Zero or more word characters | `\bamlo\w*` matches "amlo", "amlo's" |
| `\d+` | One or more digits | `\d+` matches "123" |
| `\s+` | One or more whitespace | `foo\s+bar` matches "foo  bar" |
| `(a\|b)` | Alternation | `(Shane\|Shayne)` matches either spelling |

**Word boundaries (`\b`)** are the most important regex feature for corrections. They ensure you match whole words without accidentally changing longer words that contain your pattern as a substring.

```bash
# WITHOUT \b — dangerous: matches "amlo" inside "kamloops"
chronovista corrections find-replace \
  --regex --pattern 'amlo' --replacement 'AMLO' --dry-run

# WITH \b — safe: only matches "amlo" at word boundaries
chronovista corrections find-replace \
  --regex --pattern '\bamlo\w*' --replacement 'AMLO' --dry-run
```

**Malformed regex**: If your pattern has a syntax error (e.g., unclosed brackets), you get a clear error message instead of a crash:

```bash
chronovista corrections find-replace \
  --regex --pattern '[unclosed' --replacement 'test' --dry-run
# Output: Invalid regex pattern: unterminated character set at position 0
```

---

## Cross-Segment Matching (`--cross-segment`)

### The Problem

ASR engines split audio into segments based on timing, not meaning. A name like "Claudia Sheinbaum" may be split across two segments:

```
Segment 934 (39:46): "...una entrevista, Claudia Shane"
Segment 935 (39:49): "Bound también siendo candidata..."
```

Without `--cross-segment`, you can only match within a single segment. The pattern "Shane Bound" won't be found because it spans two segments.

### The Solution

The `--cross-segment` flag concatenates adjacent segments and matches patterns across the boundary:

```bash
chronovista corrections find-replace \
  --cross-segment \
  --pattern 'Shane Bound' \
  --replacement 'Sheinbaum' \
  --video-id VIDEO_ID --dry-run
```

**How it works**:

1. Fetches all segments in scope (filtered by `--video-id`, `--language`, `--channel`)
2. Groups segments by video and language
3. Pairs strictly consecutive segments (sequence N and N+1, same video, same language)
4. Concatenates each pair's text with a space separator
5. Matches the pattern against the combined text
6. When a match spans the boundary: replacement goes into segment N, matched fragment is removed from segment N+1

### Dry-Run Preview

Cross-segment matches are visually distinguished from single-segment matches:

```
┌──────────┬─────────┬────────┬──────┬────────────────┬───────────────┐
│ Video ID │ Segment │ Start  │ Type │ Current Text   │ Proposed Text │
├──────────┼─────────┼────────┼──────┼────────────────┼───────────────┤
│ JIMXfr.. │ 934     │ 39:46  │ ╶─┐  │ ...Shane       │ ...Sheinbaum  │
│ JIMXfr.. │ 935     │ 39:49  │ ╶─┘  │ Bound tam..    │ también..     │
│ abc123.. │ 42      │ 01:23  │      │ amlo said      │ AMLO said     │
└──────────┴─────────┴────────┴──────┴────────────────┴───────────────┘

Dry run complete: 3 segments would be corrected across 2 videos (1 cross-segment pair).
```

- `╶─┐` marks the first segment in a pair
- `╶─┘` marks the second segment in a pair
- Empty Type cell = single-segment match

### Composing with Other Flags

`--cross-segment` works with all existing flags:

```bash
# Cross-segment + regex + word boundaries
chronovista corrections find-replace \
  --cross-segment --regex \
  --pattern '\bPresident Shane Bum\b' \
  --replacement 'President Sheinbaum' \
  --video-id uajXFlDGTfg --dry-run

# Cross-segment + case-insensitive
chronovista corrections find-replace \
  --cross-segment --case-insensitive \
  --pattern 'shane bound' --replacement 'Sheinbaum' \
  --video-id JIMXfrMtHas --dry-run

# Cross-segment + language filter
chronovista corrections find-replace \
  --cross-segment --language es \
  --pattern 'Shane Bound' --replacement 'Sheinbaum' --dry-run
```

### Pairing Rules

Segments are only paired when ALL of these conditions are met:

- Same video
- Same language code
- Strictly consecutive sequence numbers (N and N+1 — no gaps)
- Neither segment has empty effective text

Segments that are **not** paired:

- Different languages (e.g., segment N is "en", segment N+1 is "es")
- Non-consecutive sequence numbers (e.g., segments 5 and 7 with no segment 6)

### Single-Segment Precedence

If a pattern matches entirely within a single segment, that match takes priority. The segment is corrected as a single-segment match and excluded from any cross-segment pair it would have been part of. This prevents double-matching.

### Unscoped Warning

Running `--cross-segment` without any filter (`--video-id`, `--language`, `--channel`) loads all segments into memory. For large libraries (>5,000 segments), you'll see a warning:

```
Warning: --cross-segment with no scope filter will load ~125,000 segments into memory.
For large libraries this may be slow. Use --video-id, --language, or --channel to
narrow the scope, or pass --yes to proceed.
Continue? [y/N]
```

Use `--yes` to bypass the warning, or add a scope filter.

---

## Reverting Corrections

### Basic Revert

`batch-revert` finds segments whose corrected text matches the pattern and reverts them to their previous version:

```bash
# Preview what would be reverted
chronovista corrections batch-revert \
  --pattern 'Sheinbaum' --video-id JIMXfrMtHas --dry-run

# Apply the revert
chronovista corrections batch-revert \
  --pattern 'Sheinbaum' --video-id JIMXfrMtHas
```

**Important**: The pattern matches against the **corrected** text (what the segment says now), not the original text.

### Cross-Segment Partner Cascade

When you revert a correction that was part of a cross-segment pair, the partner segment is automatically reverted too. This is tracked via a `[cross-segment:partner=N]` marker in the correction audit record.

In dry-run mode, partner segments appear with a "(partner)" label:

```
┌──────────┬─────────┬────────┬───────────────────────┬──────────┐
│ Video ID │ Segment │ Start  │ Corrected Text        │ Note     │
├──────────┼─────────┼────────┼───────────────────────┼──────────┤
│ JIMXfr.. │ 934     │ 39:46  │ ...Sheinbaum          │          │
│ JIMXfr.. │ 935     │ 39:49  │ también siendo..      │ (partner)│
└──────────┴─────────┴────────┴───────────────────────┴──────────┘

Dry run complete: 2 segments would be reverted (1 via cross-segment partner cascade).
```

### Reverting a Specific Segment

To revert only one segment without affecting others that match the same pattern, use a more specific pattern:

```bash
# Too broad — might revert multiple segments
chronovista corrections batch-revert \
  --pattern 'Sheinbaum' --video-id JIMXfrMtHas --dry-run

# More specific — targets only the segment with this exact corrected text
chronovista corrections batch-revert \
  --pattern 'concediera una entrevista, Claudia Sheinbaum' \
  --video-id JIMXfrMtHas --dry-run
```

Always use `--dry-run` first to verify which segments will be affected.

---

## Filtering

All correction commands support scope filters:

| Flag | Description | Example |
|------|-------------|---------|
| `--video-id` | Filter by video ID (repeatable) | `--video-id abc123 --video-id def456` |
| `--language` | Filter by language code | `--language es` |
| `--channel` | Filter by channel ID | `--channel UCxxxxxxxx` |

Filters are combinable and narrow the scope. Using filters is recommended for large libraries to improve performance and avoid unintended changes.

---

## Other Correction Commands

```bash
# View correction statistics
chronovista corrections stats

# Discover recurring correction patterns
chronovista corrections patterns

# Export corrections to CSV or JSON
chronovista corrections export --format json
chronovista corrections export --format csv --video-id VIDEO_ID

# Rebuild full transcript text from corrected segments
chronovista corrections rebuild-text --video-id VIDEO_ID --dry-run
```

---

## Common Workflows

### Fix a misspelled name across all videos

```bash
# 1. Preview with word boundaries to avoid false positives
chronovista corrections find-replace \
  --regex --pattern '\bamlo\b' --replacement 'AMLO' --dry-run

# 2. Apply
chronovista corrections find-replace \
  --regex --pattern '\bamlo\b' --replacement 'AMLO'

# 3. Rebuild transcript text
chronovista corrections rebuild-text
```

### Fix an ASR-split name

```bash
# 1. Find the split in your transcript viewer
#    e.g., "President Shane" + "Bound también..."

# 2. Preview the cross-segment fix
chronovista corrections find-replace \
  --cross-segment \
  --pattern 'Shane Bound' --replacement 'Sheinbaum' \
  --video-id uajXFlDGTfg --dry-run

# 3. Apply
chronovista corrections find-replace \
  --cross-segment \
  --pattern 'Shane Bound' --replacement 'Sheinbaum' \
  --video-id uajXFlDGTfg

# 4. If wrong, revert (partner segment auto-reverted)
chronovista corrections batch-revert \
  --pattern 'Sheinbaum' --video-id uajXFlDGTfg
```

### Bulk fix a pattern across a language

```bash
# Fix all Spanish transcripts where ASR wrote "Shane Baum"
chronovista corrections find-replace \
  --cross-segment --case-insensitive \
  --pattern 'shane baum' --replacement 'Sheinbaum' \
  --language es --dry-run
```

---

## Web UI: Batch Find & Replace

The web frontend provides a visual batch correction interface at `/corrections/batch` that mirrors the CLI workflow with additional features.

### Search & Preview

1. Enter a pattern and replacement text
2. Toggle modes: **Regex**, **Case-insensitive**, **Cross-segment**
3. Optionally filter by language, channel, or specific video IDs
4. Click **Preview** to search — up to 100 matches are displayed

Each match card shows:

- **Video title** as a clickable link to the exact segment in the video detail page
- **Channel name** and **timestamp**
- **Before/after preview** with the matched text highlighted (strikethrough for removed, bold for added)
- **Context segments** (previous and next) always visible for verifying accuracy
- **Cross-segment indicator** (amber connector) for matches spanning adjacent segments
- **"Previously corrected" badge** for segments that already have an active correction

### Selection & Apply

- All matches are **selected by default** with individual checkboxes for deselection
- **Select all / Deselect all** controls in the header
- Cross-segment pairs are linked — toggling one automatically toggles its partner
- The **Apply** button shows a live count: "Apply to N selected"
- Clicking Apply shows an **inline confirmation strip** (not a modal) with pattern, replacement, count, and a reminder that corrections can be individually reverted from the video page
- Choose a **correction type** (spelling, proper_noun, word_boundary, etc.) and optional **note**
- **Auto-rebuild** is on by default — full transcript text is rebuilt after corrections are applied

### Result Summary

After applying, a persistent summary shows:

- **Applied / Skipped / Failed** counts with color coding
- **Deep links** to failed segments for individual review
- **Retry** button for failed segments
- Number of affected videos

### Correction Types

| Type | Description |
|------|-------------|
| `spelling` | Non-name orthographic errors (typos, misspellings) |
| `proper_noun` | Names of people, places, or organizations that ASR misrecognized |
| `context_correction` | Right sound, wrong word — ASR picked a valid word that doesn't fit |
| `word_boundary` | Run-together words or wrongly split compounds (e.g., 'alotof' → 'a lot of') |
| `formatting` | Punctuation, capitalization, or spacing corrections |
| `profanity_fix` | ASR garbled or censored profanity that needs restoration |
| `other` | Corrections that don't fit other categories |

---

### Entity Linking

When correcting ASR errors for entity names, you can optionally link the correction to a named entity. This creates entity mentions for every corrected segment, so you don't have to run a separate `entities scan` afterward.

#### How It Works

1. Type a replacement in the "Replace with" field (e.g., "AMLO")
2. The **entity autocomplete** appears below, showing matching entities from your database
3. Select an entity to link — a **pill/badge** appears showing the entity name and type
4. Click the external link icon on the pill to view the entity detail page (opens in a new tab)
5. Click **×** on the pill to remove the entity link and revert to plain text replacement

#### Mismatch Warning

If the replacement text does not match the selected entity's canonical name or any of its registered aliases, an **amber warning** appears:

> ⚠️ "AMLO" is not the canonical name or a registered alias for this entity.
> The entity link will still be recorded, but future scans may not match this form.
> To add it as an alias, click the 🔗 icon above to open the entity detail page. Or proceed as-is.

This warning is **non-blocking** — you can still apply the correction. But the unregistered text form won't be picked up by `entities scan` later.

To resolve the mismatch, open the entity detail page and add the replacement text as an alias (e.g., add "AMLO" as a `name_variant` alias for "Andrés Manuel López Obrador").

#### What Happens on Apply

- Entity mentions with `detection_method=user_correction` are created for each corrected segment
- Mentions are created within the same transaction as the correction (wrapped in a savepoint — mention failure does not roll back the correction)
- Duplicate mentions (same entity + same segment) are handled with `ON CONFLICT DO NOTHING`
- A `correction_id` FK links mentions back to the correction that created them

#### What Happens on Revert

- When you revert a correction that was linked to an entity, all entity mentions with that `correction_id` are automatically deleted
- Mention counters are recalculated after deletion
- Mentions created by `entities scan` (`detection_method=rule_match`) are not affected by correction reverts

#### Entity Linking is Optional

The autocomplete is always optional. You can still type plain replacement text without selecting an entity. Entity linking only applies to the batch corrections page — the inline segment editor does not support it.
