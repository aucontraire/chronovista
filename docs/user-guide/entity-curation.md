# Fix an entity that matches the wrong things

Entity detection is rule-based: a name and its aliases are matched against
transcripts, titles and descriptions. When an alias collides with ordinary
language, that produces mentions the entity never earned.

This guide covers the loop for fixing it — **see the evidence, decide, rebuild**
— and, importantly, when *not* to reach for each tool.

## Recognising the problem

The signal is a mention count that looks too high for how often the subject
actually comes up, especially for an entity whose short name is also a word:
*Hope*, *Faith*, *Grace*, *Will*, *Summer*, *Justice*, *River*.

Open the entity's detail page and look at the videos it claims. If titles appear
that have nothing to do with the subject, the alias is over-matching.

## Step 1 — read the evidence

Every machine-detected mention stores a **context snippet**: roughly 150
characters of the surrounding text. That snippet is the whole basis for the
decision, because the matched text alone cannot distinguish a name from a word —
both are the same string.

```sql
SELECT mention_text, mention_source, mention_context
FROM entity_mentions
WHERE entity_id = '<entity-uuid>'
  AND detection_method = 'rule_match'
ORDER BY random() LIMIT 20;
```

Sample rather than skim, and sample from **transcripts specifically** — they are
usually the largest source, and they behave differently from titles.

!!! note "Contexts are stored from the corrected transcript"
    Where a segment has a correction, the snippet comes from the corrected text,
    so what you read is what the app displays. Accents are preserved as written.

## Step 2 — choose the right tool

Three tools, and picking the wrong one costs you real mentions.

### Exclusion patterns — for a handful of known phrases

Good when the false positives cluster into a few recognisable collocations —
a place name that contains the entity name, a fixed idiom.

Bad when the alias is simply an ordinary word. You cannot enumerate every
construction English will put it in, and a pattern list that is *nearly*
complete still leaks.

### Match case — for an alias where capitalisation separates the two senses

The **Match case** switch on an alias row restricts that one alias to its exact
capitalisation. It applies to that alias only; the entity's other aliases and its
canonical name are unaffected.

**Check the evidence before using it.** Whether case is a reliable discriminator
differs per entity, and it is not predictable from the alias text:

| What the contexts show | Right call |
|---|---|
| lowercase occurrences are nearly all the ordinary word | **Match case** removes a lot of noise cheaply |
| lowercase occurrences are mostly the subject, just uncapitalised | **Leave it off** — you would discard real mentions |

The second case is common and easy to miss. Automatic transcription drops
capitalisation from proper nouns often enough that in a real library, one entity
had 36 lowercase occurrences of which only 3 were genuinely the ordinary word —
turning on Match case there would have lost far more than it saved.

### Removing the alias — when it earns nothing

If nearly every match is wrong and the subject is reliably named some other way,
delete the alias. Check first how many mentions use it: if the short form is how
people actually refer to the subject, removing it discards most of your coverage.

## Step 3 — rebuild

**Changing a rule does not change existing mentions.** Matching is applied when a
scan runs, and an incremental scan only *adds* — it never retracts what an
earlier rule matched. So any subtractive change needs a full rebuild.

Press **Rescan Mentions** on the entity detail page. It always rebuilds rather
than adding, so there is no mode to choose. Toggling **Match case** triggers it
for you.

From the CLI, for one entity:

```bash
chronovista entities scan --full --entity-id <entity-uuid> \
  --sources transcript,title,description
```

!!! tip "Your own work is safe"
    A rebuild deletes and regenerates **machine-detected** mentions only.
    Mentions you added by hand, and those derived from your transcript
    corrections, are untouched. The delete and the rebuild also run in one
    transaction, so an interrupted scan leaves the entity exactly as it was.

Expect minutes rather than seconds: transcript segments are not indexed by
entity, so even a single-entity rescan reads all of them.

## Step 4 — confirm

Re-read the contexts from Step 1. The false positives should be gone and the
genuine mentions still present — the second half matters as much as the first,
since a rule that removes everything is not an improvement.

## What this doesn't solve

**A name that is genuinely ambiguous in the same casing** — two different people
with the same name, or a word used as both a name and a noun with identical
capitalisation. Neither exclusion patterns nor case sensitivity separates those,
because the text really is identical. Those need manual review of individual
mentions.

## See also

- [Find entity intersections](entity-intersection.md) — querying entities once they are accurate
- [Correct transcripts](corrections.md) — fixing a misheard name so its mentions are found at all
- [Run the REST API](rest-api.md) — doing any of this programmatically
