# See which channels an entity operates

Some of the people and organisations in your library *run* YouTube channels, and a
knowledge base often records which. The app surfaces that "**operates**" relation on
two detail pages, so you can move between an entity and the channels it runs — and
between a channel and whoever operates it.

## Overview

"Operates" is an **imported assertion**: it comes from a knowledge base's record that
an entity runs a particular channel (and is refreshed by re-fetching, like any other
enrichment). It is **not** a claim that the entity appears in any given video — that
is a separate, per-video fact, and the channel-level *cast* relation it seeds is
explained in [Channel cast](../architecture/channel-cast.md). Ownership is also **not
person-only**: an organisation, a place, or a person can operate a channel.

This guide covers:

- The **Operates** panel on an entity's page
- The **Operated by** panel on a channel's page
- How **external** channels (ones you don't have) are shown
- Reading it via the REST API

## On an entity: the "Operates" panel

An entity detail page shows an **Operates** panel listing the YouTube channels that
entity runs. Each channel is one of two kinds:

- **In your library** — shown with its title and linked straight to its channel page.
- **External** — a channel the knowledge base lists but that you haven't ingested.
  It is shown as a plain, labelled "external" item, **not** a link, so a channel you
  don't have never looks like a broken one.

!!! note "Why external channels still appear"
    Seeing that someone runs a channel you *don't* have is useful on its own — it's a
    pointer to content you might want to add. Actually finding and ingesting those
    channels is a separate job (channel discovery), so the panel reports them plainly
    rather than pretending they're navigable.

An entity that operates nothing shows an empty panel; a 404 only means the entity
itself doesn't exist.

## On a channel: the "Operated by" panel

A channel detail page shows an **Operated by** panel listing the entities that operate
it, each linked to its entity page with a type badge. Because ownership is not
person-scoped, an operator may be an organisation as readily as a person — the badge
tells them apart. A channel with no recorded operator shows an empty panel.

!!! warning "Operates is not appears-in"
    "Operated by" is who *runs* the channel, not who is *in* its videos. A channel's
    host appearing in its episodes is the separate [channel cast](../architecture/channel-cast.md)
    relation; a company operating a channel says nothing about who is on screen. The
    two are kept deliberately distinct.

## Via the REST API

```bash
# Channels an entity operates (each flagged in-library or external):
GET /api/v1/entities/{entity_id}/channels

# Entities that operate a channel (any entity type):
GET /api/v1/channels/{channel_id}/operators
```

The entity endpoint returns each channel id with its title and an `in_library` flag
(the title is present exactly when the channel is in your library); the channel
endpoint returns each operating entity with its type and name. Both are read-only,
and a missing entity or channel returns a 404.

## See also

- [Channel cast](../architecture/channel-cast.md) — the channel-level "who fronts this
  channel" relation that the ownership link seeds, and why it never becomes a per-video
  mention.
- [See what a channel is about](channel-entities.md) — the entities that *appear on* a
  channel's videos, ranked by distinctiveness (a different question from who operates it).
- [Ground entities in a knowledge base](entity-enrichment.md) — where the imported
  ownership assertion comes from.
