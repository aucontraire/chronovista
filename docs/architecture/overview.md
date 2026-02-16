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

Abstracted data access with swappable implementations:

```python
class VideoRepository(ABC):
    @abstractmethod
    async def save(self, video: Video) -> None: ...

    @abstractmethod
    async def find_by_id(self, video_id: VideoId) -> Optional[Video]: ...
```

### Dependency Injection

Loose coupling between components enables testing and flexibility:

```python
class SyncService:
    def __init__(
        self,
        video_repo: VideoRepository,
        youtube_api: YouTubeAPIClient,
    ):
        self.video_repo = video_repo
        self.youtube_api = youtube_api
```

## Component Overview

### CLI Layer

Typer-based command-line interface:

- Rich formatting and progress bars
- Command groups (auth, sync, topics, takeout)
- Error handling and user feedback

### REST API Layer

FastAPI-based HTTP interface:

- 11 versioned endpoints under `/api/v1/`
- OAuth integration with CLI token cache
- OpenAPI documentation (Swagger, ReDoc)
- Pydantic V2 response schemas
- Pagination and error handling

### Service Layer

Business logic services:

- **AuthService** - OAuth authentication
- **SyncService** - Data synchronization
- **TranscriptService** - Multi-language transcript management
- **TopicService** - Topic analytics
- **TakeoutService** - Google Takeout processing
- **RecoveryOrchestrator** - Wayback Machine video recovery coordination
- **CDXClient** - Wayback Machine CDX API client with caching and retry
- **PageParser** - Archived YouTube page metadata extraction

### Repository Layer

Data access abstractions:

- **ChannelRepository** - Channel data
- **VideoRepository** - Video data
- **TranscriptRepository** - Transcript storage
- **TopicRepository** - Topic classification
- **UserVideoRepository** - Watch history

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

### Recovery Operation

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
