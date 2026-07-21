# System Design

Detailed component design and service architecture.

## Service Architecture

chronovista's business logic lives in concrete service classes under
`src/chronovista/services/`. Services are **plain classes** that receive their
collaborators (repositories, the `YouTubeService` client, a database session)
via their constructors — there is no service-locator or global registry. Only
three services sit behind ABC interfaces (see [Service Interfaces](#service-interfaces)).

```
                              Service Layer
+-----------------------------------------------------------------------------+
|                                                                             |
|  Ingestion & Sync            Transcripts & Corrections                      |
|  +----------------------+    +-------------------------------+              |
|  | YouTubeService       |    | TranscriptService             |              |
|  | TakeoutService       |    | TranscriptCorrectionService   |              |
|  | TakeoutSeedingService|    | BatchCorrectionService        |              |
|  | EnrichmentService    |    | SegmentService                |              |
|  +----------------------+    +-------------------------------+              |
|                                                                             |
|  Tags & Entities             Topics & Analytics                             |
|  +----------------------+    +-------------------------------+              |
|  | TagNormalizationSvc  |    | TopicAnalyticsService         |              |
|  | TagManagementService |    | TopicGraphService             |              |
|  | TagBackfillService   |    | ImageCacheService             |              |
|  | EntityMentionScanSvc  |    | OnboardingService             |              |
|  | PhoneticMatcher      |    |                               |              |
|  +----------------------+    +-------------------------------+              |
|                                                                             |
|  Recovery (services/recovery/)                                              |
|  +--------------------------------------------------------------+          |
|  | RecoveryOrchestrator  ChannelRecoveryOrchestrator            |          |
|  | CDXClient   PageParser   RateLimiter                         |          |
|  +--------------------------------------------------------------+          |
|                                                                             |
+-----------------------------------------------------------------------------+
                                    |
                                    v
                         Repository Layer  ->  PostgreSQL
```

> For the exhaustive, always-current list of service classes and their public
> methods, see the generated [Code reference](../reference/code/). This page
> describes the design; the reference documents the surface.

## Service Interfaces

Most services are concrete classes with no abstract base. Three services are
defined against ABC interfaces in `services/interfaces/`, because they wrap
external systems and benefit from being swappable in tests:

| Interface | Implementation | Wraps |
|-----------|----------------|-------|
| `YouTubeServiceInterface` | `YouTubeService` | YouTube Data API v3 |
| `TranscriptServiceInterface` | `TranscriptService` | `youtube-transcript-api` + captions |
| `TakeoutServiceInterface` | `TakeoutService` | Google Takeout archive parsing |

Example (`youtube_service_interface.py`):

```python
class YouTubeServiceInterface(ABC):
    @abstractmethod
    async def get_video_details(self, video_id: VideoId) -> Video | None: ...

    @abstractmethod
    async def get_channel_details(self, channel_id: ChannelId) -> Channel | None: ...

    @abstractmethod
    async def download_caption(self, caption_id: str, fmt: str = "srt") -> str | None: ...

    @abstractmethod
    async def check_credentials(self) -> bool: ...
```

## Recovery Services

The recovery subsystem (`services/recovery/`) reconstructs metadata for deleted
or unavailable videos and channels from the Internet Archive's Wayback Machine.

### RecoveryOrchestrator

Coordinates deleted video recovery via the Wayback Machine:

```
1. Check video eligibility (must exist, must not be AVAILABLE)
2. Query CDX API for archived snapshots
3. Iterate snapshots (max 20, 600s timeout)
4. Extract metadata via PageParser (JSON -> meta tags -> Selenium)
5. Apply three-tier overwrite policy
6. Create stub channels for unknown channel_ids (FK safety)
7. Update video record and persist recovered tags
```

### CDXClient

Async client for the Wayback Machine CDX API:

- File-based caching with a configurable TTL (`cdx_cache_ttl_hours` setting)
- Separate cache keys per year filter (`{video_id}_from2018.json`)
- Exponential backoff retry (3 retries, base 2s)
- Rate limit handling (60s pause on 429)
- Configurable date range filtering (`--start-year`/`--end-year`)
- Sort order: newest-first by default, oldest-first when `from_year` is set

### PageParser

Extracts metadata from archived YouTube video pages using three strategies:

1. **JSON extraction** — Parses `ytInitialPlayerResponse` embedded JavaScript for title, description, channel, tags, view count, upload date, category, thumbnail
2. **Meta tag fallback** — Parses Open Graph (`og:`) and `itemprop` HTML meta tags via BeautifulSoup (covers pre-2017 pages lacking JSON)
3. **Selenium fallback** — Optional rendering for pre-2017 pages requiring JavaScript (requires `selenium` + `webdriver-manager`)

Includes removal notice detection (playability status, title checks, body text patterns) to skip archived pages that show "Video unavailable" instead of real content. It also extracts channel title and ID from video pages to drive automatic channel recovery.

### ChannelRecoveryOrchestrator

Coordinates channel-level archive recovery:

```
1. Load all deleted/unavailable videos for the channel
2. Iterate videos through RecoveryOrchestrator
3. Extract channel metadata from recovered video pages (auto-channel recovery)
4. Apply two-tier overwrite policy for the channel record:
   - Immutable fields: fill-if-NULL only (title, description)
   - Mutable fields: overwrite-if-newer (thumbnail, subscriber count)
5. Return per-video recovery outcomes with summary statistics
```

### Recovery Dependency Injection

Recovery dependencies are wired via `get_recovery_deps()` in `api/deps.py`. It
returns a **tuple**, not a bundle object:

```python
def get_recovery_deps() -> tuple[CDXClient, PageParser, RateLimiter]:
    """Provide the CDX client, page parser, and shared rate limiter."""
    ...
```

The `RateLimiter` is a module-level singleton (`RateLimiter(rate=40.0)`) so the
Wayback Machine rate limit is respected across all concurrent requests, while a
fresh `CDXClient` and `PageParser` are created per call. The endpoint constructs
the orchestrator from these three dependencies plus the request-scoped database
session.

### Idempotency Guard

Recovery endpoints enforce a 5-minute idempotency window. If `recovered_at` is
within the last 5 minutes, the endpoint returns the existing result without
re-querying the Wayback Machine. This prevents redundant CDX/page-fetch cycles
from duplicate requests or UI retries.

## Repository Layer

Data access follows the repository pattern with a two-tier generic base in
`repositories/base.py`.

### Base Repository

`BaseRepository` is an ABC declaring the async contract;
`BaseSQLAlchemyRepository` is the concrete generic implementation that every
specialized repository extends.

```python
class BaseRepository(
    ABC, Generic[ModelType, CreateSchemaType, UpdateSchemaType, IdType]
):
    @abstractmethod
    async def create(self, session: AsyncSession, *, obj_in: CreateSchemaType) -> ModelType: ...

    @abstractmethod
    async def get(self, session: AsyncSession, id: IdType) -> ModelType | None: ...

    @abstractmethod
    async def get_multi(self, session: AsyncSession, *, skip: int = 0, limit: int = 100) -> list[ModelType]: ...

    @abstractmethod
    async def update(self, session: AsyncSession, *, db_obj: ModelType, obj_in: UpdateSchemaType) -> ModelType: ...

    @abstractmethod
    async def delete(self, session: AsyncSession, *, id: IdType) -> ModelType | None: ...
```

`BaseSQLAlchemyRepository` adds `exists(session, id) -> bool` alongside the
concrete implementations.

### Specialized Repositories

There is one repository per persisted entity (~21 in total). Representative
examples:

| Repository | Entity | Key Features |
|------------|--------|--------------|
| `ChannelRepository` | Channel | Subscription tracking, availability status |
| `VideoRepository` | Video | Multi-language fields, recovery columns |
| `VideoTranscriptRepository` | VideoTranscript | Quality scoring, language codes |
| `TopicCategoryRepository` | TopicCategory | Hierarchical structure |
| `UserVideoRepository` | UserVideo | Watch history |
| `CanonicalTagRepository` / `TagAliasRepository` | Canonical tags / aliases | Tag normalization joins |
| `NamedEntityRepository` / `EntityMentionRepository` | Entities / mentions | Entity knowledge base |

## Data Enrichment Pipeline

```
Google Takeout
     |
     v
+--------------------+
| Parse Takeout Files|  TakeoutService
| - watch-history.html/json
| - subscriptions.csv
| - playlists.csv
+--------+-----------+
         |
         v
+--------------------+
| Seed the Database  |  TakeoutSeedingService / SeedingOrchestrator
| - Videos, Channels, Playlists, UserVideos
+--------+-----------+
         |
         v
+--------------------+
| Enrich via the API |  EnrichmentService
| - videos.list()
| - channels.list()
| - Rate limited, priority-tiered
+--------+-----------+
         |
         v
+--------------------+
| Store in Database  |
| - Upsert logic
| - FK integrity
| - Deduplication
+--------------------+
```

## Rate Limiting Strategy

The YouTube Data API client (`YouTubeService`) is async and batches requests
(up to 50 IDs per `videos.list`/`channels.list` call). Request pacing is
governed by the `api_rate_limit`, `concurrent_requests`, `request_timeout`,
`retry_attempts`, and `retry_backoff` settings. The recovery subsystem uses its
own `RateLimiter` for Wayback Machine traffic.

### Retry Logic

Transient failures are retried with exponential backoff (via `tenacity`):

```python
@retry(
    retry=retry_if_exception_type((YouTubeAPIError, NetworkError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    before_sleep=before_sleep_log(logger, logging.WARNING),
)
async def fetch_with_retry(self, video_id: str):
    ...
```

## Configuration Management

Configuration is **environment-based** (Pydantic `Settings`, `BaseSettings`);
there is no YAML configuration file. See [Configuration](../getting-started/configuration.md)
for the full list of environment variables.

```python
class Settings(BaseSettings):
    youtube_api_key: str = Field(default="")
    youtube_client_id: str = Field(default="")
    youtube_client_secret: str = Field(default="")
    database_url: str = Field(...)
    oauth_redirect_uri: str = Field(...)
    data_dir: Path = Field(default=Path("./data"))

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")
```

Language preferences are **not** stored in a config file — they live in the
`user_language_preferences` database table and are managed through the
`languages` CLI command group and the `UserLanguagePreferenceRepository`.

## Error Handling

### Custom Exceptions

All first-class errors derive from `ChronovistaError` (`src/chronovista/exceptions.py`):

```python
class ChronovistaError(Exception):
    """Base exception for all chronovista errors."""


class AuthenticationError(ChronovistaError): ...
class QuotaExceededException(ChronovistaError): ...
class YouTubeAPIError(ChronovistaError): ...
class RecoveryError(ChronovistaError): ...          # -> CDXError, PageParseError, RecoveryDependencyError
class APIError(ChronovistaError): ...               # -> NotFoundError, BadRequestError, ConflictError, ...
```

The `APIError` subtree maps onto HTTP responses (RFC 7807 problem details); the
`RecoveryError` subtree covers the Wayback Machine recovery path.

### Error Recovery

Services degrade gracefully around external APIs — a failed item is logged and
skipped rather than aborting a whole batch, and transient failures are retried
with backoff before being surfaced.

## See Also

- [Architecture Overview](overview.md) - High-level design
- [Data Model](data-model.md) - Database schema
- [API Integration](api-integration.md) - YouTube API details
- [Code Reference](../reference/code/) - Generated service/repository docs
