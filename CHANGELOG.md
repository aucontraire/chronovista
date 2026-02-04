# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

_No changes yet._

## [0.13.0] - 2026-02-03

### Added

#### Feature 010: FastAPI REST API Foundation

A complete RESTful API server for programmatic access to chronovista data.

**New CLI Command: `api start`**

Start the REST API server:

```bash
chronovista api start                # Start on default port 8000
chronovista api start --port 8765    # Custom port
chronovista api start --reload       # Development mode
```

**11 API Endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/health` | GET | Health check (no auth required) |
| `/api/v1/videos` | GET | List videos with pagination and filtering |
| `/api/v1/videos/{video_id}` | GET | Get video details |
| `/api/v1/videos/{video_id}/transcript/languages` | GET | List available transcript languages |
| `/api/v1/videos/{video_id}/transcript` | GET | Get full transcript |
| `/api/v1/videos/{video_id}/transcript/segments` | GET | Get transcript segments (paginated) |
| `/api/v1/search/segments` | GET | Full-text search across transcripts |
| `/api/v1/preferences/languages` | GET | Get language preferences |
| `/api/v1/preferences/languages` | PUT | Update language preferences |
| `/api/v1/sync/{operation}` | POST | Trigger sync operation |
| `/api/v1/sync/status` | GET | Get sync status |

**Key Features:**

- **Shared Authentication**: API uses CLI's OAuth tokens - authenticate once with `chronovista auth login`
- **Interactive Documentation**: Swagger UI at `/docs`, ReDoc at `/redoc`
- **OpenAPI Specification**: Available at `/openapi.json`
- **Full-text Search**: Search across all transcripts with before/after context
- **Pagination**: All list endpoints support `limit` and `offset` parameters
- **CORS Support**: Configurable for frontend development

**Technical Details:**

- FastAPI with async SQLAlchemy integration
- Pydantic V2 response schemas with strict validation
- Token-based auth via CLI OAuth cache
- Comprehensive error handling with standard error schema
- 207 integration tests for API endpoints

## [0.11.0] - 2026-01-29

### Added

#### Feature 008: Transcript Segment Table

Added a dedicated `transcript_segments` table for precise timestamp-based transcript queries and navigation.

**Database Changes:**

- **New Table**: `transcript_segments` with columns:
  - `id` (BIGINT, primary key)
  - `video_id` (VARCHAR(20), FK to video_transcripts)
  - `language_code` (VARCHAR(20), FK to video_transcripts)
  - `text` (TEXT): Segment text content
  - `start_time` (FLOAT): Segment start time in seconds
  - `duration` (FLOAT): Segment duration in seconds
  - `end_time` (FLOAT): Computed end time for range queries
  - `sequence_number` (INTEGER): Order within transcript
  - `has_correction` (BOOLEAN): Indicates manual corrections
- **Performance Indexes**:
  - Composite index on `(video_id, language_code, start_time)` for timestamp lookups
  - Index on `end_time` for range queries
- **Backfill Migration**: Automatically populates segments from existing `raw_transcript_data`

**New CLI Commands: Timestamp-Based Queries**

Query transcript segments by timestamp to find what was said at specific moments:

```bash
# Get segment at specific timestamp
chronovista transcript segment VIDEO_ID 5:00
chronovista transcript segment VIDEO_ID 5:00 --format json

# Get context around timestamp (default: 30s window)
chronovista transcript context VIDEO_ID 5:00
chronovista transcript context VIDEO_ID 5:00 --window 60

# Get segments in time range
chronovista transcript range VIDEO_ID 1:00 5:00
chronovista transcript range VIDEO_ID 0:00 10:00 --format srt
```

**Technical Details:**

- Segments auto-created when syncing transcripts via `sync transcripts` command
- Repository-level integration: `VideoTranscriptRepository.create_or_update()` automatically creates segments from `raw_transcript_data`
- Idempotent segment creation: existing segments deleted before inserting new ones
- Supports flexible timestamp formats: `MM:SS`, `HH:MM:SS`, `MM:SS.ms`, or raw seconds

#### Feature 007: Transcript Timestamp Preservation

Persist raw transcript data with timestamps to enable future timestamp-based navigation features.

**Database Changes:**

- **5 New Columns** on `video_transcripts` table:
  - `raw_transcript_data` (JSONB): Complete API response with timestamps and segments
  - `has_timestamps` (BOOLEAN, default true): Quick filter for timestamp availability
  - `segment_count` (INTEGER): Number of transcript segments
  - `total_duration` (FLOAT): Total transcript duration in seconds
  - `source` (VARCHAR(50)): Transcript source identifier (youtube_transcript_api, manual_upload, etc.)
- **4 Performance Indexes**:
  - Partial index on `has_timestamps` for fast filtering
  - B-tree indexes on `segment_count`, `total_duration`, `source`

**New CLI Command: `sync transcripts`**

Download and store transcripts for videos in your database:

```bash
# Sync transcripts for all videos without transcripts
chronovista sync transcripts

# Sync specific video(s)
chronovista sync transcripts --video-id VIDEO_ID
chronovista sync transcripts --video-id ID1 --video-id ID2

# Preview without downloading
chronovista sync transcripts --dry-run

# Limit number of videos processed
chronovista sync transcripts --limit 50

# Specify language preference (fallback to available)
chronovista sync transcripts --language es --language en

# Force re-download existing transcripts
chronovista sync transcripts --force
```

**Technical Details:**

- Transcripts stored with full timestamp data for each segment
- Automatic language fallback when preferred language unavailable
- Integration with youtube-transcript-api v1.2.2+
- Feature 007 data populated via `VideoTranscriptRepository.create_or_update()`

#### Feature 006: Dependency Injection Container

Introduced a centralized Dependency Injection (DI) Container for managing service and repository lifecycles across the application.

**Key Changes:**

- **DI Container** (`src/chronovista/container.py`): Centralized management of service and repository instances
- **Factory Methods**: 10 repository types with transient instance creation:
  - `CategoryRepository`, `ChannelRepository`, `PlaylistMembershipRepository`
  - `PlaylistRepository`, `SubscriptionRepository`, `TagRepository`
  - `TopicRepository`, `TranscriptRepository`, `VideoRepository`, `VideoTagRepository`
- **Singleton Services**: `YouTubeService` and `TranscriptService` via `@cached_property` for efficient reuse
- **Wired Factory Methods**: Automatic dependency injection for:
  - `EnrichmentService` (with YouTubeService dependency)
  - `TopicSeeder` (with TopicRepository dependency)
  - `CategorySeeder` (with CategoryRepository dependency)
- **Request Scoping**: Support for future API layer with `RequestContext`, `request_scope()`, and `request_context` context variable
- **Test Isolation**: Container reset functionality via `reset()` method for clean test state
- **Comprehensive Tests**: 34 unit tests covering all container functionality
- **Test Fixtures**: Mock injection support with `mock_youtube_service` and `container_reset` fixtures

#### Feature 005: Playlist ID Consolidation

Consolidated playlist identification into a single `playlist_id` field that serves as the canonical identifier for all playlists.

**Key Changes:**

- **Single Source of Truth**: `playlist_id` now supports all playlist types:
  - YouTube IDs (PL prefix, 30-50 chars) e.g., `PLdU2XMVb99xMxwMeeLWDqmyW8GFqpvgVC`
  - Internal IDs (int_ prefix, 36 chars) e.g., `int_5d41402abc4b2a76b9719d911017c592`
  - System playlists (LL, WL, HL) for Liked, Watch Later, History
- **Simplified Architecture**: Removed redundant columns:
  - `youtube_id` - consolidated into `playlist_id`
  - `link_status` - now derived from `playlist_id` prefix
  - `unresolvable_reason` - feature removed
- **ID-Based Import**: Playlists from Google Takeout are now imported by unique YouTube ID (not deduplicated by title)
- **Enhanced Takeout Parsing**: Now extracts additional metadata from `playlists.csv`:
  - `Playlist Create Timestamp` → `published_at`
  - `Playlist Visibility` → `privacy_status`

**Playlist Commands:**

- `chronovista playlist list`: Show all playlists with link status (derived from ID prefix)
- `chronovista playlist list --linked`: Show only YouTube-linked playlists (PL/LL/WL/HL prefix)
- `chronovista playlist list --unlinked`: Show only internal playlists (int_ prefix)
- `chronovista playlist show <playlist_id>`: Show detailed playlist information

**Technical Details:**

- Link status determined by `playlist_id` prefix (PL/LL/WL/HL = linked, int_ = unlinked)
- Database migration expands `playlist_id` from VARCHAR(36) to VARCHAR(50)
- All playlists imported with unique IDs - no title-based deduplication

### Changed

- Refactored `enrich.py` CLI commands to use container pattern for service instantiation
- Refactored `sync_commands.py` to use container (removed module-level instantiation anti-pattern)
- Refactored `seed.py` CLI commands to use container pattern for seeder instantiation
- Updated `repositories/__init__.py` to export `PlaylistMembershipRepository`
- Refactored CLI commands to use sync command framework with SyncResult and transformers
- Added ABC interfaces for service layer

### Removed

- Module-level repository instantiation from `sync_commands.py`
- Direct 8-dependency manual wiring in CLI commands (replaced with container pattern)

### Fixed

- Removed unused imports in CLI commands (ChannelEnrichmentError, ErrorCategory, display_error_panel, etc.)
- Fixed import sorting with isort
