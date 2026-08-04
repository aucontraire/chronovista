# Find what entities have in common

Filter your library to the videos where **several entities all appear**, exclude the ones you don't want, and discover connections you didn't know to look for.

## Overview

Entity filtering used to be single-entity only: you could browse everything mentioning one person, but not ask what two people have in **common**. That question is the entry point to most relationship-oriented things a library can tell you — which episodes cover both a person and a place, which conversations bring two guests together, which videos discuss a topic without ever mentioning the obvious counterpart.

This guide covers three things:

- Filtering the videos list to an **intersection** of entities
- **Excluding** entities to cut noise out of a result
- Following the **"appears with"** panel to find connections

Everything here is read-only. Nothing you do changes a mention, an entity, or a video.

## Filter to an intersection

On the **Videos** page, open the filter panel and use **Mentions all of**.

1. Type at least two characters into the entity search.
2. Pick an entity. The list narrows immediately.
3. Add another. It narrows further.

The filter is an **AND**: a video qualifies only if *every* entity you list has at least one mention in it. Adding entities always shrinks the result, never grows it.

Each result row shows what it matched:

```
Knowledge Graph or Vector Database... Which is Better?
GraphRAG (23)   from 5:43     Knowledge Graph (22)   from 1:39
```

The number in parentheses is how many times that entity is mentioned in that video. The timestamp is the **first** mention, so you can jump straight to the part you want. An entity mentioned only in a video's title or description has no timestamp — nothing is shown rather than a misleading `0:00`.

!!! tip "Results are ranked by relevance"
    With an entity filter active and no sort chosen, results order by total mentions across your chosen entities — the videos most *about* them first. Pick any sort yourself and your choice is kept; it is never overridden.

## Exclude entities

**Excluding** is the disambiguation tool. Use it when one entity keeps dragging in videos about something else.

Add entities under **Excluding**. A video mentioning *any* excluded entity is removed, regardless of how many required entities it matches. Exclusion is an **OR** — the opposite of the required set.

Exclusion works on its own, with no required entities at all. That answers a different and useful question: *"show me everything that isn't about this."*

An entity cannot be both required and excluded. The request is rejected with an explanation rather than silently returning nothing.

## Restrict to transcript mentions

Mentions come from three places: the **transcript**, the video **title**, and the **description**. By default all three count.

Tick **Transcript only** to require that the entity was actually *said*, not merely listed in metadata. This is the difference between a video that discusses someone and a video that tagged them.

!!! note "Manual corrections always survive this filter"
    Every mention you added or corrected by hand is transcript-sourced, so restricting to transcript keeps all of them. It never discards your own work — that would invert the point of the setting.

## Follow the "appears with" panel

Open any entity's detail page and scroll to **Appears with**. It lists the entities sharing the most videos with this one:

```
Redacted        3296 videos
Redacted             1474 videos
Redacted            1301 videos
```

Click any of them and you land on the videos list filtered to **both** entities — that exact set of shared videos. The number in the panel and the number you land on are the same number, by construction.

This is the discovery path: you don't need to know what to search for. Open an entity you care about, see what it keeps company with, and follow whatever surprises you.

If **Transcript only** is active, the panel honours it and carries it forward, so the count and the page it opens are computed under one definition.

## Share a filtered view

Everything lives in the page address — required entities, exclusions, and the transcript-only setting. Copy the URL and it reproduces the same result set, ordering, and total:

```
/videos?entity_id=<id>&entity_id=<id>&min_evidence=transcript
```

It survives refresh and back-navigation, so browser history works the way you expect.

## Reading the colours

Entities are colour-coded by type, and the convention is the same everywhere:

| Where | The pill contains |
|---|---|
| **Entities** page, entity detail header | The **type** — "Person", "Place" — this is the legend |
| Everywhere else | The entity's **name**, in that type's colour |

The Entities page is where the convention is taught; every other surface applies it. Screen readers are told the type on every surface regardless of which form is shown.

## Via the REST API

The same capability is available directly. See the [REST API guide](rest-api.md) for the full parameter list.

```bash
# Videos mentioning BOTH entities
curl "http://localhost:8765/api/v1/videos?entity_id=<id-a>&entity_id=<id-b>"

# ...excluding a third, transcript mentions only
curl "http://localhost:8765/api/v1/videos?entity_id=<id-a>&exclude_entity_id=<id-c>&min_evidence=transcript"

# What appears alongside an entity
curl "http://localhost:8765/api/v1/entities/<id>/co-occurring"
```

## Limits and edge cases

- **Ten entities per set.** Required and excluded are counted separately, and both count toward the videos list's overall filter cap.
- **An intersection matching nothing** shows an empty state that tells you so, distinct from an error and from an unfiltered library.
- **Duplicates are harmless.** Asking for the same entity twice is treated as asking once.
- **Unavailable videos** are excluded by default, as everywhere else. Tick *Show unavailable content* to include them; entity matching itself is unaffected by availability.
- **Mentions, not tags.** The intersection works on entity *mentions*. A tag associating an entity with a video is not an utterance and carries no timestamp, so it does not qualify.

## What this doesn't do yet

**Temporal proximity** — "both entities discussed within 30 seconds of each other" — is not available. It is the strongest form of this query and it is computable from data already stored, so it may arrive later. The per-entity timestamps this feature exposes are exactly what such a filter would need.

## See also

- [Work with transcripts](transcripts.md) — where transcript mentions come from
- [Correct transcripts](corrections.md) — fixing a misheard name so its mentions are found
- [Analyze topics](topic-analytics.md) — the other axis for slicing your library
