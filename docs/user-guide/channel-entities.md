# See what a channel is about

Every channel detail page has an **Entities** panel: the named entities that appear across that channel's videos, ranked by how **distinctive** each one is to this channel — and pinnable to filter the channel's videos down to what you care about.

## Overview

A channel's videos mention a lot of entities. Listing them by raw frequency is not very useful: the same handful of high-volume entities show up on *every* channel, so a frequency list makes every channel look the same and buries what actually characterises *this* one.

The Entities panel ranks by **distinctiveness** instead, so the top of the list reflects what the channel is really about. It is read-only until you pin — nothing here changes an entity, a mention, or a video.

This guide covers:

- Reading the **distinctiveness** ranking (and why it isn't a video-count list)
- The **"Also appears"** group
- **Pinning** entities to filter the channel's videos
- Large channels and performance

## The list is ranked by distinctiveness, not video count

!!! warning "This is not a "most videos first" list"
    Entities are **not** ordered by how many of the channel's videos they appear in. They are ordered by **distinctiveness**: the share of that entity's *total* appearances (across your whole library) that fall on **this** channel.

    `share = videos on this channel / videos everywhere`

An entity that appears in **40 of this channel's 60 videos** — and in only 45 videos across your entire library — has a distinctiveness share of **40 / 45 ≈ 89%**. It is strongly *this channel's* subject.

An entity that appears in **50 of this channel's videos** but in **5,000 videos** library-wide has a share of **50 / 5,000 = 1%**. It shows up here, but it shows up everywhere — it doesn't tell you much about this channel.

So the **89%** entity ranks **above** the **1%** entity, even though the second one appears in *more* of the channel's videos. That inversion is the whole point: it surfaces the channel's host, recurring subjects, and defining topics ahead of library-wide background noise.

Each row shows the entity's name and type, the number of this channel's videos it appears in, and its distinctiveness as a percentage (shares below 1% read as `<1%`).

!!! note "What "appears" means"
    An entity "appears" on a video through the same definition used everywhere else in the app: a **mention** (transcript, title, or description) **or** a **tag** association. So the counts here agree with the entity's counts on its own detail page and in the [entity intersection](entity-intersection.md) — a video associated only through a tag is still counted.

## The "Also appears" group

Entities that appear in **exactly one** of the channel's videos are held out of the distinctiveness ranking and listed separately under **Also appears**. A single-video entity trivially scores 100% distinctiveness, which would otherwise dominate the top of the list without meaning anything. They are still here — just grouped where they belong. When there are none, the group is omitted.

## Pin entities to filter the channel's videos

Each entity has a **pin** control. Pinning one filters the channel's video list to just the videos associated with that entity; pinning more narrows to the videos associated with **all** of them (an **AND**).

1. Pin an entity. The channel's video list narrows to that entity's videos on this channel.
2. Pin another. The list narrows further — an AND never grows the result.
3. Use **Clear pinned entities** to remove them all at once.

The pinned state lives in the **URL**, so the filtered view is shareable, survives a reload, and works with browser back/forward. Pinning composes with the channel page's existing sort and filters — it adds to the current view rather than resetting it.

!!! tip "The count you see is the count you get"
    The per-entity video count shown in the panel and the number of videos the pinned filter returns are the **same number**, by construction — both come from the one association definition. Pinning an entity that reads "40 videos" returns exactly those 40 videos (including any that are unavailable, so the two figures always match).

If a pinned combination matches no videos, you get an explicit empty state with a way to unpin.

## Large channels

Channels with more than ten associated entities show the **top 10** by distinctiveness with a **Show all N** control that reveals the rest (including the "Also appears" group). Fewer than ten, and the full list shows with no control.

!!! note "Entity-dense channels take a moment"
    Ranking is computed live over every entity on the channel, so a channel with a few hundred associated entities can take a few seconds to load the panel — the distinctiveness denominator is measured across your whole library for each one. Typical channels (well under a hundred entities) are fast. This is expected, not an error.

## Via the REST API

```bash
# Ranked entities for a channel
GET /api/v1/channels/{channel_id}/entities

# The pinned filter is the standard videos endpoint, scoped to the channel.
# include_unavailable=true keeps the count and the result in agreement.
GET /api/v1/videos?channel_id={channel_id}&entity_id={E}&entity_id={F}&include_unavailable=true
```

The `/channels/{id}/entities` response lists each entity with its channel video count, its library-wide count, and the derived distinctiveness share; the ranked group comes first, then the "also appears" group.

## See also

- [Find what entities have in common](entity-intersection.md) — the entity intersection the pinned filter reuses
- [Attach tags to an entity](entity-tags.md) — tag associations count toward these rankings
- [Fix an over-matching entity](entity-curation.md) — if an entity is pulling in videos it shouldn't
</content>
