# Entity Grounding Endpoint

> **Version**: 1.0.0
> **Last Updated**: 2026-09-05

`POST /api/v1/entities/{entity_id}/grounding`

A single action for changing an existing entity's knowledge-base grounding. It **re-links**
the entity to a chosen Wikidata match, or — with no match given — **refreshes** the facts for
the entity's current link. It never changes the entity's name, aliases, detected mentions, or
tag associations.

Requires authentication (same dependency as the other `/entities` routes).

---

## Request

Path parameter:

| Name | Type | Description |
|------|------|-------------|
| `entity_id` | string (UUID) | The named entity to re-ground. |

Body (`GroundingRequest`):

```jsonc
{
  "approved_identifier": { "source": "wikidata", "id": "Q00000000" },  // optional; omit/null = refresh
  "description": "curator-confirmed description text"                   // optional; re-link only, ignored on refresh
}
```

| Field | Type | Notes |
|-------|------|-------|
| `approved_identifier` | object \| null | Present → **re-link**. `source` is `"wikidata"`; `id` is the QID. Omitted/null → **refresh**. |
| `description` | string \| null | Applied on re-link only (max 5000 chars; `""` allowed to clear). Ignored on refresh. |

### Re-link (`approved_identifier` present)

Sets `external_ids.wikidata` as **verified**, applies `description` when provided, clears the
old facts and old DBpedia link, and schedules a background fetch that re-fills facts and
re-resolves DBpedia. The previous link's facts are never returned against the new link.

### Refresh (`approved_identifier` omitted/null)

Re-fetches facts for the entity's **current** link. The link and description are unchanged;
the existing facts stay visible until the background fetch replaces them.

---

## Responses

### 200 OK

Returns the updated entity detail — the same shape as
[`GET /api/v1/entities/{entity_id}`](index.md), wrapped in a `data` envelope. `enrichment.properties`
MAY be `{}` with facts still pending (never the previous link's facts).

```jsonc
{
  "data": {
    "entity_id": "…",
    "canonical_name": "…",
    "description": "…",
    "enrichment": {
      "grounded": true,
      "identifiers": [ { "source": "wikidata", "id": "Q…", "url": "…", "verified": true } ],
      "properties": { }
    }
  }
}
```

### Error responses

All errors follow [RFC 7807 Problem Details](error-responses.md).

| Status | When |
|--------|------|
| **400** | Refresh requested on an entity with **no current Wikidata link** to re-fetch from. |
| **404** | No entity with `entity_id` (including a malformed UUID). |
| **422** | Body fails `GroundingRequest` validation (e.g. `approved_identifier.source` is not `"wikidata"`). |

---

## Guarantees

- **No stale facts** — on a link change the response's `properties` is either the new link's
  facts or empty/pending, never the previous link's.
- **Cross-feature stability** — this endpoint never changes the entity's name, aliases,
  mentions, or tags; `GET /entities/{id}/videos`, `/co-occurring`, and the association counts
  return identical results before and after.
- **Audited** — every call writes one operation-log row (`reground` or `refetch`) with the
  before/after link and description and the actor.
- **Graceful degradation** — if the knowledge base is unavailable the call still succeeds
  (link and description are committed); facts fill on a later attempt.

For the conceptual background, see
[Post-creation re-grounding](../architecture/entity-reground.md).
