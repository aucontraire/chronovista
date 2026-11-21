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
| `/health` | GET | Health check (no auth) |
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

**`GET /graph/connect/evidence`** → `ConnectionEvidence` (Feature 114). The transcript passages
behind a pair's co-occurrence (the evidence panel). Unlike the three endpoints above, this one is
**Postgres-backed** (it reads `entity_mentions` / `transcript_segments`), so there is no servability
gate and no 503.

| Param | Type | Default | Notes |
|---|---|---|---|
| `a` | UUID | required | First entity id. |
| `b` | UUID | required | Second entity id. Must differ from `a`. |
| `limit` | int 1–50 | 12 | Max video items per page. |
| `offset` | int ≥ 0 | 0 | Pagination offset over the ordered videos. |

Each item is one **video**: a `representative` (the video's minimum-separation co-mention — language,
the mention pair, the rendered passage(s), the segment separation) plus `other_language_variants`
(the same pair in the video's other co-occurring languages, for an expander) and the video/channel
titles. There is no cross-video collapse — every co-occurring video is a row (closest-first;
`cooccurring_language_count` = 1 + the expander count). The response reports `total_available`
(distinct co-occurring **videos** — the pagination total), `raw_cooccurrence_count` (the
`(video, language)` transcript count, giving "spoken together in N videos (M transcripts)"), `offset`,
and `truncated`. When the pair has no transcript passage it returns `items: []` and names the
non-transcript `basis_when_empty` (`title` / `description` / `tag` / `manual`) — set only when
`total_available == 0`; an empty page with `total_available > 0` is past the end, not "no
co-occurrence". RFC-7807: **422** for `a == b`, **404** for an entity id absent from the database. No
**503** — it reads live Postgres, which is why its view can be briefly fresher than the graph snapshot.

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
