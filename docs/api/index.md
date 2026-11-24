# API Reference

Comprehensive API documentation for chronovista.

## Overview

This section contains detailed API documentation for all chronovista modules, generated from source code docstrings.

## REST API

chronovista provides a RESTful HTTP API for programmatic access.

### Starting the Server

```bash
chronovista api start --port 8000
```

### Base URL

```
http://localhost:8000/api/v1/
```

### Authentication

All endpoints except `/health` require authentication. The API shares OAuth tokens with the CLI.

### Endpoints Overview

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check (no auth). Includes `proximity_worker`: the [transcript proximity](../architecture/transcript-proximity.md) worker's `state` (`running`, `stopped`, `crashed`, `disabled`) and `last_cycle_at` |
| `/videos` | GET | List videos |
| `/videos/{id}` | GET | Get video details |
| `/videos/{id}/transcript` | GET | Get transcript |
| `/videos/{id}/transcript/segments` | GET | Paginated segments |
| `/videos/{id}/transcript/languages` | GET | Available languages |
| `/videos/{id}/transcript/segments/{seg_id}/corrections` | GET, POST | Segment correction history / submit correction |
| `/videos/{id}/transcript/segments/{seg_id}/corrections/revert` | POST | Revert latest segment correction |
| `/videos/{id}/playlists` | GET | Playlists containing video |
| `/videos/{id}/entities` | GET | Entities associated with video, through any source (mentions, tag, manual) |
| `/videos?entity_id=` | GET | Videos mentioning **all** listed entities (repeat the key; add `exclude_entity_id` and `min_evidence`) |
| `/videos/{id}/alternative-url` | PATCH | Set alternative URL for unavailable video |
| `/channels` | GET | List channels |
| `/channels/{id}` | GET | Get channel details |
| `/channels/{id}/videos` | GET | Videos by channel |
| `/playlists` | GET | List playlists |
| `/playlists/{id}` | GET | Get playlist details |
| `/playlists/{id}/videos` | GET | Videos in playlist |
| `/topics` | GET | List topics |
| `/topics/{id}` | GET | Get topic details |
| `/topics/{id}/videos` | GET | Videos by topic |
| `/categories` | GET | List categories |
| `/categories/{id}` | GET | Get category details |
| `/categories/{id}/videos` | GET | Videos in category |
| `/tags` | GET | List tags |
| `/tags/{tag}` | GET | Get tag details |
| `/tags/{tag}/videos` | GET | Videos with tag |
| `/canonical-tags` | GET | List canonical tags (with prefix search and fuzzy suggestions) |
| `/canonical-tags/{normalized_form}` | GET | Get canonical tag detail with aliases |
| `/canonical-tags/{normalized_form}/videos` | GET | Videos across all raw tag variations |
| `/canonical-tags/resolve` | GET | Resolve raw tag form to canonical tag |
| `/entities` | GET | List named entities |
| `/entities/{id}` | GET | Get entity details |
| `/entities/{id}/videos` | GET | Videos associated with entity (filter by `source`, multi-select over `manual`/`transcript`/`title`/`description`/`tag`) |
| `/entities/{id}/aliases` | POST | Add alias to entity |
| `/entities/{id}/co-occurring` | GET | Entities sharing videos with this entity |
| `/graph/health` | GET | Connection-graph serving state (`ServingHealth`) |
| `/graph/entities` | POST | Which of the given entity ids are present in the graph |
| `/graph/connect` | GET | How two entities connect (`a`, `b`, `max_hops`, `max_category_size`) |
| `/graph/connect/passages` | GET | Discussion passages where two entities are mentioned within a window (`a`, `b`, `window`, `limit`, `offset`) |
| `/graph/connect/passages/farther` | GET | Videos where both are spoken, but never within the window (`a`, `b`, `window`, `limit`, `offset`) |
| `/graph/neighborhood` | GET | Explore the bounded neighbourhood subgraph around one or two entities (`seed`, `radius`, `limit`, `ceiling`, `edge_types`, `max_category_size`) |
| `/corrections/batch/preview` | POST | Preview batch find-replace matches |
| `/corrections/batch/apply` | POST | Apply batch corrections to selected segments |
| `/corrections/batch/rebuild-text` | POST | Rebuild transcript text for affected videos |
| `/search/segments` | GET | Search transcripts |
| `/search/titles` | GET | Search video titles |
| `/search/descriptions` | GET | Search video descriptions |
| `/images/channels/{id}` | GET | Proxied channel avatar (cached locally) |
| `/images/videos/{id}` | GET | Proxied video thumbnail (cached locally) |
| `/preferences/languages` | GET, PUT | Language preferences |
| `/sync/{operation}` | POST | Trigger sync |
| `/sync/status` | GET | Sync status |
| `/videos/{id}/recover` | POST | Recover video metadata via Wayback Machine |
| `/channels/{id}/recover` | POST | Recover channel metadata via Wayback Machine |

### Connection Graph (Feature 113)

Four read-only endpoints back the web [Connection Explorer](../user-guide/connection-explorer.md) —
its **Connect** mode (the single pruned path between two entities) and its **Explore** mode (the
bounded neighbourhood subgraph around one or two entities). All require auth and read the production
connection graph (a separate Neo4j datastore, not Postgres).

**`GET /graph/health`** → `ServingHealth`. Reports whether the graph may be served. Degrades
gracefully: an unreachable graph returns `servable: false`, never a 500.

```json
{
  "status": "complete",
  "loaded_at": "2026-11-18T09:30:00+00:00",
  "declared_layers": ["observed", "semantic", "categories", "reviewed"],
  "servable": true
}
```

| Field | Type | Meaning |
|---|---|---|
| `status` | `"complete"` \| `"loading"` \| `null` | Build state: complete (servable), rebuilding, or never loaded. |
| `loaded_at` | string \| null | ISO-8601 time the current build completed, if any. |
| `declared_layers` | string[] | Layers this build was configured to contain. |
| `servable` | bool | True iff `status == "complete"` **and** every declared layer is present. |

**`POST /graph/entities`** → `{ "present": [uuid, …] }`. Given `{ "entity_ids": [uuid, …] }` (at most
500), returns the subset present in the graph — for the graph-present-only picker. On an unavailable
graph returns an empty set.

**`GET /graph/connect`** → `GraphConnection`. Query parameters:

| Param | Type | Default | Notes |
|---|---|---|---|
| `a` | UUID | required | First entity id. |
| `b` | UUID | required | Second entity id. Must differ from `a`. |
| `max_hops` | int ≥ 3 | 3 | Reach of the knowledge-base search (a lower value reliably returns nothing, so it is rejected). |
| `max_category_size` | int ≥ 1 | 500 | Specificity floor — shared categories broader than this are ignored. |

The response carries the reviewed verdict (if any), one chain per connecting kind in by-kind order,
the `searched_max_hops` it used, and `any_truncated` (the knowledge-base search hit its hop bound
without connecting). This endpoint refuses a non-servable graph — see the error responses below.

**`GET /graph/neighborhood`** → `GraphSubgraph` (Feature 115). The bounded neighbourhood around one
or two seed entities — Explore mode's subgraph of nodes and edges across every relationship kind,
rather than a single path. Query parameters:

| Param | Type | Default | Notes |
|---|---|---|---|
| `seed` | UUID (repeatable) | required | One or two seed entity ids. |
| `radius` | int 1–2 | 1 | How many hops out from the seeds to gather. |
| `limit` | int ≥ 1 | 60 | Neighbours added per load — a legible initial view. |
| `ceiling` | int ≥ `limit` | 250 | Hard cap on total nodes; expansion accumulates up to it. |
| `edge_types` | string (repeatable) | all | Restrict to these relationship / trust kinds. |
| `max_category_size` | int ≥ 1 | 500 | Specificity floor for category edges, as in `/graph/connect`. |

Each edge carries its server-assigned trust **layer** (verified / category / co-occurrence) and its
stored direction; when the node cap binds, co-occurrence edges are dropped before verified ones. Like
`/graph/connect`, this endpoint refuses a non-servable graph — see the error responses below.

**`GET /graph/connect/passages`** → `PairPassages` (Feature 118). The evidence panel's data: a pair's
**discussion passages** for one window, built from the transcript proximity records, so the videos
listed are exactly the videos the measurement reports. Postgres-backed; no 503. See
[Discussion passages](../architecture/transcript-proximity.md#discussion-passages-what-the-evidence-panel-shows)
for the rule.

| Param | Type | Default | Notes |
|---|---|---|---|
| `a` | UUID | required | First entity id. |
| `b` | UUID | required | Second entity id. Must differ from `a`. |
| `window` | int | 30 | Seconds between the two mentions' starts: 15, 30, 60 or 120. |
| `limit` | int 1–50 | 12 | Max videos per page. |
| `offset` | int ≥ 0 | 0 | Pagination offset over the ordered videos. |

`items` are videos, closest co-mention first (ties by video id), each with **every** grouped passage in
time order. A grouped passage carries its `variants`, one per language passage; `variants[0]` leads,
chosen by the caller's language preferences, else the closest. A variant has its time range,
`co_mention_count`, its `closest` moment (both mentions, oriented to `a` and `b`, and up to six segments
of corrected text with `is_context` marking the segment after a mention), its `other_moments` (times
and gaps only) and `name_list`. Totals cover every video, never just the page, and are identical across
pages and when `a` and `b` are swapped: `video_count` (the pagination total), `passage_count` (grouped
passages), `channel_count` (a video with no channel counts once as unknown), `closest_gap_seconds`,
and `farther_video_count` (not in the totals). State: `pending_scopes`, `failed_scopes` (video,
language, titles) and `state`, which is one of `passages`, `not_computed`, `no_transcript` (with
`basis_when_empty` when a tag, title or description links them) or `no_passage_in_window`.
`passage_rule_version` names the rule. **422** for `a == b` or an unsupported `window` (standard
validation body, naming the parameter), **404** for an unknown entity id. It never answers 409: without
an established identity the variants are ordered closest first.

**`GET /graph/connect/passages/farther`** → `FartherVideos` (Feature 118). The videos behind
`farther_video_count`: both entities spoken in the same transcript language, never within the window.
Same `a`, `b` and `window` as above; `limit` 1–100 (default 20), `offset`. Items are nearest first
(`nearest_gap_seconds`, then video id), with the language and `nearest_start_time` of the closest moment;
`total` equals the passages response's `farther_video_count` for the same pair and window.

`GET /graph/connect/evidence` (Feature 114) was retired: use `/graph/connect/passages`.

### Interactive Documentation

- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`

For detailed usage, see [REST API User Guide](../user-guide/rest-api.md).

## Module Structure

```
chronovista/
|-- models/           # Pydantic data models
|-- repositories/     # Data access layer
|-- services/         # Business logic
|-- cli/              # Command-line interface
|-- config/           # Configuration
|-- auth/             # Authentication
```

## Quick Links

The CLI, REST API, and code (models, repositories, services) reference is
auto-generated from the source at build time. See the [Reference](../reference/)
section:

- **[CLI](../reference/cli.md)** — every `chronovista` command, generated from the Typer app
- **[REST API](../reference/api/index.md)** — endpoints by tag, generated from the OpenAPI schema
- **[Code](../reference/code/)** — Pydantic models, DB models, services, and repositories (mkdocstrings)

## Type Safety

All APIs use strict typing with Pydantic V2:

```python
from chronovista.models import Video, Channel
from chronovista.repositories import VideoRepository

# Full type hints
async def get_video(repo: VideoRepository, video_id: str) -> Video | None:
    return await repo.find_by_id(video_id)
```

## Async Support

chronovista is async-first:

```python
async with session_factory() as session:
    repo = VideoRepository(session)
    videos = await repo.find_all()
```

## Error Handling

The API uses [RFC 7807 Problem Details](https://www.rfc-editor.org/rfc/rfc7807) for all error responses:

- [Error Responses](error-responses.md) - Complete RFC 7807 format reference
- [Migration Guide](rfc7807-migration.md) - Migrating from legacy error format

All error responses include:

- `Content-Type: application/problem+json`
- `X-Request-ID` header for request correlation
- Structured error body with `type`, `title`, `status`, `detail`, `code`, and `request_id`

```python
from chronovista.exceptions import (
    ChronovistaError,
    AuthenticationError,
    QuotaExceededError,
)

try:
    await service.sync()
except QuotaExceededError:
    logger.warning("API quota exceeded")
```
