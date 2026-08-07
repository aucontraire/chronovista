# Make an entity count the videos its tags are on

An entity's page says it appears in a handful of videos, but you know there are
far more. The **Appears with** panel is empty while the header claims hundreds.
Or you created the entity by hand and its video count has been stuck at zero
ever since.

The usual cause is that no canonical tag points at the entity. This page shows
how to attach one, fold the variant spellings into it, and undo any of that.

---

## What is actually missing

Two different things put a video next to an entity, and they fail in different
ways:

| | What it does | Where you fix it |
|---|---|---|
| **Alias** | detects the entity's name in transcripts, titles, descriptions | the **Aliases** section |
| **Tag** | associates videos the uploader tagged | the **Tags** section |

An entity with no linked tag is invisible to every video whose only connection
is a tag — no matter how many aliases it has. Rebuilding mentions will not help,
because there is no mention to find.

If you are unsure which of the two you are missing, see
[Tags and aliases are not the same thing](../architecture/tags-and-aliases.md).

---

## Attach the first tag

On the entity's page, find **Tags**. If nothing is linked it says so:

> *No tag is linked to this entity — videos tagged with its name are not counted
> toward it.*

That sentence is the diagnosis.

1. Type at least two characters into **Search tags**.
2. Pick the tag that names this entity.
3. Click **Attach**.

The confirmation states the consequence, and the header's video count moves:

> Linked "Harbour Board" — 3 videos now count toward Harbour Board.

**Only unattached tags are listed.** A tag already representing another entity
does not appear, because attaching it here would take it from that entity. The
entity's own tag does not appear either — a tag cannot be merged into itself.

---

## Fold in the variants

Most subjects are tagged several ways: a misspelling, an abbreviation, a form
with punctuation. Each of those is its own canonical tag, and each holds videos
the entity is not counting.

Search for one and attach it exactly as above. Because the entity already has a
tag, this time the chosen tag is **merged into it**:

> Merged "Harbour Brd" into "Harbour Board" — 4 videos now count toward Harbour
> Board.

Three things follow from that wording:

- **The entity's existing tag always survives**, whichever is larger. If the
  entity's tag holds 6 videos and the one you attach holds 30, the 6-video tag
  is still the one that remains — it is the tag the entity is known by.
- **The merged tag stops existing separately.** Its spellings move across, and it
  disappears from search. Attaching it again is not possible, and not needed.
- **No alias is created.** Tags associate videos; they do not teach the entity a
  new name to look for. If you also want the variant detected in transcripts,
  add it under **Aliases** deliberately.

Repeat for each variant. The tag's variation count grows as it absorbs them.

---

## See what a tag has absorbed

Once a tag has merged tags beneath it, a control appears:

**Show 2 merged tags**

Expanding it lists them:

```
Harbour Board   12 videos · 4 variations
  ↳ Harbour Brd (brought 3 videos)      Un-merge
  ↳ Harbour Auth (brought 1 video)      Un-merge
```

"Brought" is literal. A merged tag holds no videos of its own any more — the
number is what it contributed when it was folded in. **Do not add those numbers
to the parent's**: the same video may have carried several of the spellings, and
it is only counted once.

---

## Undo a mistake

Both operations are reversible from the page, and they are named differently
because they do different things:

| | Acts on | Result |
|---|---|---|
| **Un-merge** | a tag inside the group | it becomes an independent tag again, and reappears in search |
| **Unlink** | the entity's own tag | the entity is left with no tag at all |

### Un-merge

Click **Un-merge** beside any absorbed tag. Its spellings return to it and it
becomes searchable, so you can attach it somewhere else if it was on the wrong
entity.

**If it was folded in alongside others, you will be asked to confirm.** Merges
are reversed as a whole operation, so restoring one restores everything that
came in with it:

> Un-merging 'Harbour Brd' also restores 2 other tags, because they were merged
> in one operation: Harbour Auth, HB.

The message names them, because whether that is acceptable depends on which ones
come back. Most merges fold a single tag and ask nothing.

### Unlink

Click **Unlink** beside the entity's tag. The tag is not deleted or deprecated —
it returns to the searchable pool, which is how you move a tag attached to the
wrong entity.

**Unlink is refused while anything is merged into that tag**, and says so:

> 1 tag is merged into 'Harbour Board'. Un-merge it first — its raw forms live on
> this tag, so unlinking would take its videos from this entity too.

Un-merge them first, then unlink.

---

## When something looks wrong

**"This entity has 2 tags representing it."**
A legacy state: two tags were linked separately before this was possible.
Attaching another is blocked, because there is no single tag to merge into.
Unlink one of them, then attach it again so it merges properly.

**A tag you expected is not offered.**
It already represents an entity, or it has been merged into another tag. Both are
deliberate. Search for it on the **Merge Tags** screen to see where it went.

**The video count did not move.**
The tag's videos may already have been reaching the entity through mentions. The
tag path and the mention path overlap; a video counts once either way.

**The tag's name changed capitalisation when you attached it.**
Attaching title-cases a tag whose form was not already title-cased. This affects
the tag's display form, not the entity's name.

---

## What this doesn't solve

- **Videos that are not tagged at all.** If the uploader never tagged the video,
  no tag can associate it. That is what aliases and mention detection are for.
- **A tag that means something adjacent.** A programme named after a person is
  not that person; merging it makes the taxonomy claim they are the same thing.
  Whether that is acceptable is a judgement about your library, not a rule.
- **Moving a tag between entities in one step.** Unlink it from the first entity,
  then attach it to the second.

---

## See also

- [Fix an over-matching entity](entity-curation.md) — when the problem is
  aliases matching too much, not tags missing
- [Tags and aliases are not the same thing](../architecture/tags-and-aliases.md)
  — why these are two relationships and not one
- [Run the REST API](rest-api.md) — the endpoints behind this page
