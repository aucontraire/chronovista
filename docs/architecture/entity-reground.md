# Post-Creation Re-Grounding

Grounding links a named entity to a public knowledge base (Wikidata, and through it DBpedia)
so it carries a stable identifier and a set of facts. Originally grounding happened only when
an entity was created. This note explains **re-grounding** — changing or refreshing that link
after creation — and the rules that keep it safe.

## Why it exists

Two things go wrong after an entity is grounded:

- **The link is wrong.** An entity was matched to a namesake, to a work named after a person,
  or was created ungrounded and now needs a link. The curator must be able to point it at the
  correct subject.
- **The facts are missing or stale.** The initial fetch failed, or the source has since
  changed. The curator must be able to pull fresh facts without re-creating the entity.

Both are the same underlying operation — *set the grounding for this entity* — with an
optional target. Given a target match it **re-links**; with no target it **refreshes** the
current link. The UI surfaces this as two affordances ("Change link" and "Refresh") over one
endpoint.

## The no-stale-facts rule

The facts on an entity's page must always correspond to the link shown next to them. A wrong
mix — the old subject's occupation under the new subject's name — is worse than no facts at
all, because it reads as authoritative.

So on a **re-link** the facts and the secondary DBpedia link are **cleared in the same write**
that sets the new identifier. There is no window in which the page shows the new link beside
the old link's facts. The new facts are then fetched in the background; until they land the
page shows the link with empty/pending facts, which is honest.

A **refresh** does not change the link, so its existing facts already belong to the correct
subject. There the facts are left in place and replaced only when the new fetch succeeds — if
the knowledge base is briefly unreachable the curator keeps what they had rather than watching
the entity go blank.

## Why the fetch is fire-and-forget

Fetching facts from the knowledge base is slow and can fail. The endpoint commits the link and
description synchronously and schedules the fact fetch as a detached background task, then
returns immediately. This keeps the action instant and makes it **degrade gracefully**: a
knowledge base outage never fails the re-ground — the link and description are saved, and the
batch resolution pipeline (or a later refresh) fills the facts.

Because the fetch runs after the response, the entity page updates its facts moments later
without a manual reload; the frontend invalidates the entity-detail and entity-list caches on
success.

## Traceability

Every re-ground writes one audit row — `reground` for a link change, `refetch` for a refresh —
recording the previous link, the new link, the previous and new description, and which of
{link, description, facts} changed, plus who performed it. This is a distinct operation type
from an ordinary entity edit (`update`), so the grounding history is legible on its own and
the change is reversible in review.

## What it never touches

Re-grounding mutates only the entity's knowledge-base link, its DBpedia link, its fetched
facts, and (on re-link) its description. It does **not** change the entity's name, aliases,
detected mentions, or tag associations — so every downstream reader (entity→videos,
co-occurrence, association counts, tag lists) returns identical results before and after.

For how the identifier and facts are stored, see [Data model](data-model.md). For the
endpoint contract, see [Entity grounding endpoint](../api/entity-grounding.md). For the
curator workflow, see [Ground an entity in a knowledge base](../user-guide/entity-enrichment.md).
