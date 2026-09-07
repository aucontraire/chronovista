# Alias→Mention Provenance & Undoable Deletion

An entity alias is a name variant the scan matches against transcripts, titles, and
descriptions to produce **mentions**. Deleting an alias should not leave those mentions
behind as a phantom, and a mistaken deletion should be reversible. This note explains how a
mention is tied to the alias that produced it, and how deletion is made safe to undo.

## Why a recorded link

When the scan detects a mention it knows which alias matched — but historically it recorded
only the entity and the matched text, not the alias. "This alias's mentions" was therefore
*derived* at delete time by folding the mention text and the alias name to a case- and
accent-insensitive form (`lower(unaccent(...))`) and comparing. That derivation has two
weaknesses:

- **It drifts on rename.** The fold is recomputed from the alias's *current* name, so once an
  alias is renamed the frozen mention text no longer folds to it, and the derived match misses
  mentions that alias genuinely produced.
- **It cannot separate a fold-collision.** The fold is coarser than the stored normalized
  form (which keeps tilde/cedilla), so two aliases like `pena` and `peña` fold identically.

Recording the alias on the mention (`entity_mentions.alias_id`) fixes the first: it is a
stable fact that survives a rename. It cannot fix the second — and neither can anything else,
because **detection itself folds diacritics**, so the matcher genuinely cannot tell `pena`
from `peña`. When a matched span folds to more than one of the entity's aliases the scan
records **no link** (NULL) rather than guessing; deletion then falls back to the derived fold
with a guard that keeps any mention another surviving alias still covers.

Manual and correction-derived mentions are never alias output, so they never carry a link and
are never removed by an alias deletion.

## How deletion decides what to remove

Deleting an alias removes the entity's auto-detected (`rule_match`) mentions that are EITHER
recorded against that alias (`alias_id`) OR unlinked and matched by the fold while not covered
by another surviving alias. The recorded link is preferred, so a delete targets exactly that
alias's mentions even after a rename; the fold is the fallback for rows created before the
link was recorded (a one-time `backfill-alias-links` populates those where unambiguous).

## Why deletion is reversible

Because a delete destroys machine-detected mentions, a wrong click was previously only
recoverable by re-adding the alias and re-scanning — which cannot reconstruct the exact prior
state. So a deletion is now recorded as one `alias_delete` operation whose rollback payload
captures the removed alias and the removed mention rows. Undo re-creates both and recomputes
the entity's counters, reusing the same operation-log + undo machinery as entity edits and
re-grounding.

The undo is deliberately conservative:

- **Idempotent** — an operation already undone cannot be undone again.
- **No partial restore** — if a colliding alias was created since the deletion, restoring
  would violate the entity's normalized-name uniqueness, so the undo is refused whole and the
  entity is left exactly as it was.
- **Degrades gracefully** — a removed mention whose transcript segment has since been deleted
  is skipped (its foreign key would reject it); the alias and every still-valid mention are
  restored regardless, never a hard failure that blocks recovery.

## What it never changes

A delete or undo touches only the alias and its auto-detected mentions. The entity's name,
description, other aliases, hand-made mentions, and correction-derived mentions are untouched —
so every downstream reader (entity→videos, co-occurrence, association counts) returns to its
prior state after an undo.

See the [Alias operations reference](../api/entity-alias-operations.md) for the endpoints and
the [entity-curation how-to](../user-guide/entity-curation.md) for the workflow.
