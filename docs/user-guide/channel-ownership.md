# See which channels an entity operates

Some of the people and organisations in your library *run* YouTube channels. The app
surfaces that "**operates**" relation on two detail pages — so you can move between an
entity and the channels it runs, and between a channel and whoever operates it — and lets
you **add links by hand** where the imported data falls short.

## Overview

"Operates" links come from **two places**, kept distinct by provenance:

- **Imported** (per Wikidata) — a knowledge base records that an entity runs a channel, via
  its YouTube-channel-id identifier; refreshed by re-fetching, like any other enrichment.
- **Added by you** — a link you assert by hand, for the cases the import misses: an owner
  with no knowledge-base entry, one whose channel isn't recorded there, or one who runs
  several channels when only one is listed.

Both appear together, each labelled with where it came from. A hand-added link is **never**
shown as if the knowledge base said it, and nothing you add is ever written back to the
knowledge base — your assertions live in the app only. "Operates" is **not** a claim that
the entity appears in any given video; that is the separate, per-video
[channel cast](../architecture/channel-cast.md) relation it seeds. Ownership is also **not
person-only**: an organisation, a place, or a person can operate a channel.

This guide covers:

- The **Operates** panel on an entity's page, and adding a channel by hand
- The **Operated by** panel on a channel's page, and assigning an owner
- Removing a link you added
- How **external** channels (ones you don't have) are shown
- Reading and writing it via the REST API

## On an entity: the "Operates" panel

An entity detail page shows an **Operates** panel listing the YouTube channels that entity
runs. Each channel carries a provenance badge — **per Wikidata** or **you added** — and is
one of two kinds:

- **In your library** — shown with its title and linked straight to its channel page.
- **External** — a channel the entity runs but that you haven't ingested. It is shown with
  a **not in library** marker and an outbound link to the channel on YouTube, so you can
  still reach it without it masquerading as an in-app page.

An entity that operates nothing shows an empty panel; a 404 only means the entity itself
doesn't exist.

### Adding a channel by hand

The panel has an **add** control. Paste either a raw channel ID (the `UC…` form) or a full
`youtube.com/channel/…` URL — the app extracts the ID locally, so no lookup is made. The
channel need not be in your library; external and defunct channels are exactly what hand-adding
is for. A link you add shows the **you added** badge immediately.

The add is refused, with a clear reason, when it would be redundant:

- if the knowledge base already records that channel for the entity ("already recorded from
  Wikidata"), or
- if you've already added it ("already added").

An `@handle` or `/c/` custom URL is **not** accepted — those don't contain the channel ID,
and resolving them would require a network lookup that this feature deliberately avoids. Use
the `UC…` ID or the `/channel/` URL.

!!! note "A hand-added link is a local assertion"
    Adding a channel records *your* claim that the entity runs it. It never edits Wikidata
    and never pretends to be imported data — the badge always tells the two apart.

## On a channel: the "Operated by" panel

A channel detail page shows an **Operated by** panel listing the entities that operate it,
each with a provenance badge and linked to its entity page with a type badge. Because
ownership is not person-scoped, an operator may be an organisation as readily as a person.

The panel has an **assign owner** control: give an entity and it is recorded as operating
this channel (the mirror of adding from the entity side — the same link, the other door).
The entity must already exist; assigning does **not** create entities, so if the one you
want isn't there yet, create it first. Redundant assignments are refused with the same
"already recorded" / "already added" reasons.

!!! warning "Operates is not appears-in"
    "Operated by" is who *runs* the channel, not who is *in* its videos. A channel's host
    appearing in its episodes is the separate [channel cast](../architecture/channel-cast.md)
    relation; a company operating a channel says nothing about who is on screen.

## Removing a link you added

A **remove** control appears only on links you added (the **you added** rows), on either
panel. Imported links have no remove control: removing one would be pointless because the
next enrichment refresh would restore it. Removing a hand-added link takes it off both the
entity and the channel views at once.

## Via the REST API

```bash
# Read — channels an entity operates (each with provenance + in-library flag):
GET    /api/v1/entities/{entity_id}/channels
# Read — entities that operate a channel (each with provenance):
GET    /api/v1/channels/{channel_id}/operators

# Add by hand — entity side (body: {"channel_ref": "<UC… id or /channel/ URL>"}):
POST   /api/v1/entities/{entity_id}/channels
# Add by hand — channel side (body: {"entity_id": "<uuid>"}):
POST   /api/v1/channels/{channel_id}/operators

# Remove a hand-added link (either side):
DELETE /api/v1/entities/{entity_id}/channels/{channel_id}
DELETE /api/v1/channels/{channel_id}/operators/{entity_id}
```

Each read item carries a `provenance` of `wikidata` or `manual`. A redundant add returns
`409` with the reason; an unparseable `channel_ref` returns `422`; adding for an entity that
doesn't exist returns `404`. A `DELETE` of a link that isn't a hand-added one returns `404`
(imported links are not removable here).

## See also

- [Channel cast](../architecture/channel-cast.md) — the channel-level "who fronts this
  channel" relation that the ownership link seeds, and why it never becomes a per-video
  mention.
- [See what a channel is about](channel-entities.md) — the entities that *appear on* a
  channel's videos, ranked by distinctiveness (a different question from who operates it).
- [Ground entities in a knowledge base](entity-enrichment.md) — where the imported
  ownership assertion comes from.
