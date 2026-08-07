# Tags and aliases are not the same thing

Both attach a video to an entity. Both look like "other names for this subject".
They are different relationships, stored differently, and confusing them
produces bugs that no test notices, because each half behaves correctly on its
own.

This page explains why they are separate and what follows from that.

---

## The two relationships

**An entity alias is a pattern for finding a name in text.** Mention detection
scans transcripts, titles and descriptions for each alias and records a
*mention* — a position in a specific video, with a timestamp when the source is a
transcript. Aliases are curated: someone decided this string denotes this
subject.

**A canonical tag is a grouping of the strings uploaders typed.** YouTube tags
are freeform, so the same subject arrives as a dozen spellings. Normalization
folds those into one canonical tag, and linking that tag to an entity makes every
video carrying any of its spellings count toward the entity — an *association*,
with no position, because the tag applies to the video as a whole.

| | Entity alias | Canonical tag |
|---|---|---|
| Table | `entity_aliases` | `canonical_tags` + `tag_aliases` |
| Produced by | a curator deciding | an uploader typing |
| Used for | detecting a name **in text** | associating a **whole video** |
| Result | a mention, often with a timestamp | an association, no position |
| Text quality | must read as a name | uploader convention: `#hb2024`, `harbour board interview clip` |

## Why the source matters

An alias is used as a **matching rule**. Add `HB` as an alias and every
transcript containing "HB" now claims a mention of Harbour Board — including the
ones about hydraulic brakes.

Tag forms are not written to be matched against prose. They are SEO strings,
show titles, hashtags, and truncations. A form that is perfectly good for
grouping videos is often a poor pattern for finding a name in a sentence.

That asymmetry is the whole reason these are two relationships and not one:
**the same string can be a correct tag and an incorrect alias.**

---

## How a video reaches an entity

Two independent paths, meeting only at the entity:

```
       ┌── mention path ─────────────────────────────────┐
       │  transcript / title / description text          │
       │     ↓ matched against entity_aliases            │
       │  entity_mentions  (position, timestamp)         │
       └────────────────────────────────────┐            │
                                            ↓            ↓
                                        named_entities
                                            ↑
       ┌── association path ─────────────────┘
       │  video_tags.tag  (the raw string on the video)
       │     ↓ matched on raw_form
       │  tag_aliases  ← the spellings; this is the association
       │     ↓ canonical_tag_id
       │  canonical_tags.entity_id
       └──────────────────────────────────────
```

A video can arrive by either path or both. Counting it once is why the entity
page reports `sources` per video rather than summing two numbers.

## Two pointers on a tag, easily conflated

A canonical tag carries two nullable references that mean unrelated things:

```
canonical_tags
├── entity_id       ──→ named_entities     "this tag REPRESENTS an entity"
└── merged_into_id  ──→ canonical_tags     "this tag IS another tag"
```

| | Changes the tag's status? | Keeps its spellings? | Still in search? |
|---|---|---|---|
| **Link** (`entity_id`) | no — stays `active` | yes | yes, unless excluded |
| **Merge** (`merged_into_id`) | yes — becomes `merged` | no, they move to the target | no |

A merge ends the tag's separate existence. A link does not touch it. This is why
a merged tag disappears from search on its own while a linked one does not, and
why "add this tag to an entity" has to mean *merge* when the entity already has
a tag: linking a second one leaves two active tags claiming the same entity, each
holding its own spellings, each still offered for selection.

---

## What follows

**One active canonical tag per entity.** Anything else means the entity's videos
are split across groups, and counting code has to decide which tag is "the" one.
Adding a tag to an entity that already has one merges rather than links, so the
invariant holds by construction.

**A merged tag keeps nothing.** Its spellings move to the target and its
`entity_id` is cleared. It exists as a tombstone for history and undo. Its stored
video count is deliberately *not* recomputed — that frozen number is what the tag
contributed when it was folded in, and it is shown as "brought N videos" for
exactly that reason. Recomputing it would read as zero and imply the tag brought
nothing.

**Tag operations never write aliases.** Attaching a tag to an entity does not
teach the entity a new name. This was got wrong once: linking created an alias
from the tag's form, producing zero-occurrence entries that polluted the
detection ruleset with strings nobody says aloud. The tag's form belongs to the
association path; putting it on the detection path is a category error, however
convenient it looks.

**Semantic precision survives merging.** Following ADR-003, a place name and the
adjective derived from it stay separate tags — they denote different things even
though one is built from the other, and a video about the cuisine is not a video
about the country. Merging is for the same subject spelled differently, not for
subjects that are merely related. A programme named after a person is a
judgement call, not a rule, and the system does not make it for you.

---

## Where this bites

The failures are quiet, because each component is individually correct:

- **An entity with aliases but no tag** looks fully curated and silently omits
  every tag-only video.
- **An entity with two linked tags** reports counts that depend on which tag the
  reader happened to query.
- **An alias created from a tag form** produces mentions in unrelated videos, or
  more often none at all — an entry with zero occurrences that nobody notices.
- **A merge in the wrong direction** moves the surviving tag's identity to the
  one that does not hold the entity link, and the entity's associations vanish
  without an error.

Each of those has occurred. None produced a failing test at the time.

---

## See also

- [Make an entity count the videos its tags are on](../user-guide/entity-tags.md)
- [Fix an over-matching entity](../user-guide/entity-curation.md) — the alias
  side of the same page
- [Data model](data-model.md) — the tables underneath
- ADR-003 — tag normalization, and where the precision rule comes from
