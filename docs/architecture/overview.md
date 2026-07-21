# Architecture Overview

High-level architecture of chronovista.

## System Context

chronovista is a personal YouTube data analytics platform that provides comprehensive access to YouTube engagement history through a hybrid approach combining Google Takeout data imports, live YouTube Data API integration, and Wayback Machine recovery for deleted content.

```
+-------------------+  +-------------------+  +-------------------+  +-------------------+
|   User (CLI/Web)  |  |  Google Takeout   |  |   YouTube API     |  | Wayback Machine   |
+--------+----------+  +--------+----------+  +--------+----------+  +--------+----------+
         |                      |                      |                      |
         v                      v                      v                      v
+-----------------------------------------------------------------------------------------+
|                              chronovista                                                 |
|                                                                                          |
|  +---------------+  +---------------+  +---------------+  +------------------+           |
|  |  CLI Layer    |  |  REST API     |  |  Repository   |  | Recovery Service |           |
|  |  (Typer)      |  |  (FastAPI)    |  |    Layer      |  | (CDX + Parser)   |           |
|  +-------+-------+  +-------+-------+  +-------+-------+  +--------+---------+           |
|          |                  |                  |                    |                     |
|          v                  v                  v                    v                     |
|  +----------------------------------------------------------------------+                |
|  |                       PostgreSQL Database                            |                |
|  +----------------------------------------------------------------------+                |
+-----------------------------------------------------------------------------------------+
```

## Design Principles

### Domain-Driven Design

Core domain entities with rich business logic:

- **Channel** - YouTube channel with metadata and subscription tracking
- **Video** - Video with multi-language support and content restrictions
- **Transcript** - Multi-language transcript with quality indicators
- **Topic** - YouTube topic classification system

### Layered Architecture

Clear separation between layers:

| Layer | Responsibility | Technology |
|-------|----------------|------------|
| CLI | User interaction | Typer, Rich |
| REST API | HTTP interface | FastAPI, Pydantic |
| Service | Business logic | Python async |
| Repository | Data access | SQLAlchemy |
| Database | Persistence | PostgreSQL |

### Repository Pattern

Data access is abstracted behind a generic base. `BaseRepository` (an ABC in
`repositories/base.py`) declares the async contract, and
`BaseSQLAlchemyRepository` provides the concrete implementation that every
specialized repository extends:

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

### Dependency Injection

Loose coupling between components enables testing and flexibility. Services
receive their collaborators (repositories, the `YouTubeService` client, a
database session) rather than constructing them. In the REST API, FastAPI's
`Depends()` wires these together per request — for example, the recovery
endpoints obtain their dependencies from `get_recovery_deps()` in
`api/deps.py`.

## Component Overview

### CLI Layer

Typer-based command-line interface:

- Rich formatting and progress bars
- Command groups (auth, sync, topics, takeout)
- Error handling and user feedback

### REST API Layer

FastAPI-based HTTP interface:

- 70+ versioned operations under `/api/v1/` (see the generated [REST API reference](../reference/api/index.md))
- OAuth integration with CLI token cache
- OpenAPI documentation (Swagger, ReDoc)
- Pydantic V2 response schemas
- Pagination, filtering, and RFC 7807 error handling

### Service Layer

Business logic lives in concrete service classes under `services/`. Most are
plain classes; only three (`TakeoutService`, `TranscriptService`,
`YouTubeService`) sit behind ABC interfaces in `services/interfaces/`.
Representative services:

- **YouTubeService** - YouTube Data API v3 client wrapper
- **TranscriptService** - Fetch and download transcripts
- **TakeoutService** / **TakeoutSeedingService** - Parse and seed Google Takeout archives
- **EnrichmentService** (`services/enrichment/`) - Metadata enrichment via the API
- **TagNormalizationService** / **TagManagementService** - Canonical tag pipeline and curation
- **EntityMentionScanService** - Named-entity mention detection in transcripts
- **TranscriptCorrectionService** / **BatchCorrectionService** - Correction workflows
- **TopicAnalyticsService** / **TopicGraphService** - Topic analytics and relationship graphs
- **Recovery orchestrators** (`services/recovery/`) - Wayback Machine video/channel recovery, plus `CDXClient`, `PageParser`, and `RateLimiter`

### Repository Layer

Data access abstractions (all extending `BaseSQLAlchemyRepository`):

- **ChannelRepository** - Channel data
- **VideoRepository** - Video data
- **VideoTranscriptRepository** - Transcript storage
- **TopicCategoryRepository** - Topic classification
- **UserVideoRepository** - Watch history
- **CanonicalTagRepository** / **TagAliasRepository** - Tag normalization
- **NamedEntityRepository** / **EntityMentionRepository** - Entity knowledge base

...and ~14 more, one per persisted entity.

### Database Layer

PostgreSQL with async SQLAlchemy:

- Multi-language schema
- Optimized indexing
- Foreign key integrity
- JSON field support

## Data Flow

### Sync Operation

```
1. User: chronovista sync all
           |
           v
2. CLI Layer: Parse command, validate args
           |
           v
3. Service Layer: Coordinate sync operations
           |
           +---> YouTube API: Fetch data
           |
           +---> Transform: Pydantic models
           |
           v
4. Repository: Validate and persist
           |
           v
5. Database: Store with integrity checks
```

### Takeout Import

```
1. User: chronovista takeout seed /path
           |
           v
2. TakeoutParser: Parse JSON/CSV files
           |
           v
3. DataEnrichment: Fetch API metadata
           |
           v
4. Repository: Upsert with deduplication
           |
           v
5. Database: Store historical data
```

### REST API Request

```
1. Client: GET /api/v1/videos
           |
           v
2. FastAPI: Validate auth, parse params
           |
           v
3. Dependencies: Get DB session, verify OAuth
           |
           v
4. Repository: Query with filters
           |
           v
5. Response: Serialize with Pydantic
```

## Key Patterns

### Async-First Design

All I/O operations are async:

```python
async def sync_videos(self, channel_id: str) -> List[Video]:
    async with self.session_factory() as session:
        videos = await self.youtube_api.get_channel_videos(channel_id)
        for video in videos:
            await self.video_repo.save(video)
        return videos
```

### Type Safety

Strict typing with Pydantic:

```python
class Video(BaseModel):
    video_id: VideoId
    channel_id: ChannelId
    title: str
    duration: int
    made_for_kids: bool
```

### Error Handling

Graceful degradation with retry logic:

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10)
)
async def fetch_video(self, video_id: str) -> Video:
    ...
```

### Recovery API Request

```
1. Client: POST /api/v1/videos/{video_id}/recover
           |
           v
2. FastAPI: Validate auth, parse year filters
           |
           v
3. Dependencies: get_recovery_deps() → (CDXClient, PageParser, RateLimiter)
           |
           v
4. Idempotency Guard: Skip if recovered within 5 minutes
           |
           v
5. Orchestrator: CDX query → PageParser → overwrite policy
           |
           v
6. Response: RecoveryResult with recovered fields
```

### Channel Archive Recovery

```
1. Client: POST /api/v1/channels/{channel_id}/recover
           |
           v
2. FastAPI: Validate auth, parse params
           |
           v
3. ChannelRecoveryOrchestrator: Iterate channel's deleted videos
           |
           +---> Per-video: CDX query → PageParser → overwrite
           +---> Auto-channel recovery: extract channel metadata from video pages
           |
           v
4. Two-Tier Overwrite: immutable fill-if-NULL, mutable overwrite-if-newer
           |
           v
5. Response: ChannelRecoveryResult with per-video outcomes
```

### Recovery Operation (CLI)

```
1. User: chronovista recover video --video-id VIDEO_ID
           |
           v
2. CLI Layer: Parse command, validate args
           |
           v
3. CDXClient: Query Wayback Machine CDX API for snapshots
           |
           +---> Filter by date range (--start-year/--end-year)
           |
           +---> Cache results locally (24h TTL)
           |
           v
4. PageParser: Fetch and parse archived YouTube page
           |
           +---> JSON extraction (ytInitialPlayerResponse)
           |
           +---> Meta tag fallback (og: tags, itemprop)
           |
           +---> Optional Selenium fallback (pre-2017 pages)
           |
           v
5. Orchestrator: Apply three-tier overwrite policy
           |
           +---> Immutable fields: fill-if-NULL only
           +---> Mutable fields: overwrite-if-newer
           +---> NULL protection: never blank existing values
           |
           v
6. Repository: Update video + persist recovered tags
```

## See Also

- [System Design](system-design.md) - Detailed component design
- [Data Model](data-model.md) - Database schema
- [API Integration](api-integration.md) - YouTube API details
