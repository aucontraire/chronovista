# Changelog

All notable changes to chronovista will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- MkDocs documentation setup with Material theme
- Comprehensive user guide and API reference
- Architecture documentation

## [0.19.0] - 2026-02-06

### Added
- **Feature 016: Video Detail Page with Transcript Display**
  - Dedicated video detail page at `/videos/:videoId` route
  - Browser tab title shows "Channel Name - Video Title"
  - Absolute date display (e.g., "Jan 15, 2024") instead of relative time
  - Full BCP-47 language codes in transcript selector (e.g., "EN-gb" vs "EN")
  - Collapsible transcript panel with expand/collapse animation
  - WAI-ARIA tabs pattern for language selection with keyboard navigation
  - Quality indicators (checkmarks) for manual/CC transcripts
  - View mode toggle between Segments and Full Text views
  - Infinite scroll with virtualized segments (50 initial + 25 subsequent batches)
  - 150ms debounced language switching with request cancellation
  - `prefers-reduced-motion` support for animations

### Components
- `VideoDetailPage` - Main detail page with video metadata
- `TranscriptPanel` - Collapsible transcript container
- `LanguageSelector` - Language tab selector with ARIA attributes
- `ViewModeToggle` - Segments/Full Text toggle
- `TranscriptSegments` - Virtualized segment list with infinite scroll
- `TranscriptFullText` - Continuous prose view

### Hooks
- `useVideoDetail` - Fetch video metadata
- `useTranscriptLanguages` - Fetch available transcript languages
- `useTranscript` - Fetch full transcript text
- `useTranscriptSegments` - Infinite scroll for transcript segments
- `usePrefersReducedMotion` - Detect reduced motion preference

### Accessibility
- WCAG 2.1 AA compliant focus indicators
- `aria-expanded`, `aria-controls` on toggle buttons
- `role="tablist"` and `role="tab"` for language selector
- `aria-live="polite"` announcements for language changes
- Keyboard navigation (Arrow keys, Home/End, Tab)

### Technical
- React Router v6 dynamic route with `useParams`
- TanStack Query v5 with `useInfiniteQuery`
- `@tanstack/react-virtual` v3.10+ for windowed virtualization
- Design tokens in `frontend/src/styles/tokens.ts`
- 255 passing frontend tests

## [0.18.0] - 2026-02-06

### Added
- **Feature 015: Navigation Shell & Application Layout**
  - Persistent sidebar navigation with Videos, Search, and Channels links
  - Active state highlighting with distinct visual styling
  - Client-side routing using React Router v6 (`createBrowserRouter`)
  - Browser history support (back/forward buttons work correctly)
  - Bookmarkable URLs for all routes (`/videos`, `/search`, `/channels`)
  - 404 page for invalid routes with navigation back to Videos
  - Root path (`/`) redirects to `/videos`
  - Responsive sidebar: 240px with labels at ≥1024px, 64px icons-only below
  - Tooltips on sidebar icons at smaller screen sizes
  - Error boundary for graceful page error handling

### Components
- `AppShell` - CSS Grid layout wrapper with sidebar + content area
- `Sidebar` - Navigation sidebar with `<nav aria-label="Main navigation">`
- `Header` - App header with "Chronovista" title
- `NavItem` - Navigation link with `aria-current="page"` for active state
- `ErrorBoundary` - Error boundary with fallback UI
- Icon components: `VideoIcon`, `SearchIcon`, `ChannelIcon`
- Placeholder pages: `SearchPage`, `ChannelsPage`, `NotFoundPage`

### Accessibility
- WCAG 2.1 AA compliant focus indicators
- 44×44px minimum touch targets
- Keyboard navigation (Tab/Shift+Tab)
- Proper ARIA attributes on all navigation elements

### Technical
- React Router v6.22.0 with `createBrowserRouter` API
- CSS Grid layout: `grid-cols-[auto_1fr]`
- Inline SVG icons (no external dependencies)
- Existing video list functionality preserved at `/videos`

## [0.17.0] - 2026-02-05

### Added
- **Feature 014: Frontend Foundation with Vite + React**
  - Modern React 19 frontend for web-based video browsing
  - Vite 6.x build tool with hot module replacement
  - TypeScript 5.x in strict mode for type safety
  - Tailwind CSS 4.x for utility-first styling
  - TanStack Query v5 for async state management with infinite scroll
  - Orval 7.x for OpenAPI to TypeScript client generation
  - New Makefile targets: `make dev` (both servers), `make generate-api` (TypeScript types)
  - Video list view with loading skeletons, error states, empty state
  - CORS middleware for FastAPI backend
  - Extractable architecture via `git subtree split -P frontend`

### Technical
- Frontend runs on port 8766, backend on port 8765
- Auto-generated TypeScript types from OpenAPI specification
- Intersection Observer for 80% scroll trigger (infinite scroll)
- Environment-configurable API base URL for deployment flexibility

### Documentation
- [Frontend README](../frontend/README.md) - Setup, tech stack, extraction guide
- Frontend quick start: `cd frontend && npm install && make dev`

## [0.16.0] - 2026-02-05

### Added
- **Feature 013: RFC 7807 API Response Standardization**
  - All error responses now follow [RFC 7807 Problem Details](https://www.rfc-editor.org/rfc/rfc7807) format
  - New `Content-Type: application/problem+json` for all error responses
  - `X-Request-ID` header on all responses for request correlation and debugging
  - Client-provided request IDs are echoed back; server generates UUID v4 if not provided
  - Structured error response with fields: `type`, `title`, `status`, `detail`, `instance`, `code`, `request_id`
  - Validation errors (422) include `errors` array with field-level details
  - OpenAPI schema now exposes `ProblemDetail`, `ValidationProblemDetail`, and `FieldError` schemas

### Changed
- **BREAKING**: Error response format changed from `{"error": {"code": "...", "message": "..."}}` to RFC 7807 flat structure
- All 20+ API endpoints now include `X-Request-ID` header in responses
- Error responses use `application/problem+json` instead of `application/json`

### Technical
- New `RequestIdMiddleware` for async-safe request ID propagation via `contextvars`
- New exception classes: `AuthorizationError`, `RateLimitError`, `ExternalServiceError`
- Shared OpenAPI response definitions in `src/chronovista/api/routers/responses.py`
- 44 new tests for RFC 7807 compliance
- Full mypy strict compliance maintained

### Documentation
- [Error Responses Reference](api/error-responses.md) - Complete RFC 7807 format documentation
- [Migration Guide](api/rfc7807-migration.md) - Guide for updating clients to new error format

## [0.15.0] - 2026-02-05

### Added
- **Feature 012: Content Classification APIs**
  - REST API endpoints for categories: list, detail, videos-by-category (`/api/v1/categories`)
  - REST API endpoints for tags: list, detail, videos-by-tag (`/api/v1/tags`)
  - Categories sorted by video_count descending (32 YouTube predefined categories)
  - Tags sorted by video_count descending (139,763 unique tags)
  - Full pagination support with limit (1-100), offset parameters
  - Proper 404 handling for invalid category IDs and nonexistent tags
  - URL-encoded special characters in tags supported (e.g., spaces, hashtags)
  - Completes the "classification trifecta" with Topics (F011), Categories, and Tags

### Technical
- 33 new integration tests for category and tag endpoints
- Pydantic V2 response schemas with strict mode
- mypy strict compliance (0 errors)

## [0.14.0] - 2026-02-04

### Added
- **Feature 011: Complete Entity API Coverage**
  - REST API endpoints for channels: list, detail, videos-by-channel (`/api/v1/channels`)
  - REST API endpoints for playlists: list, detail, videos-by-playlist (`/api/v1/playlists`)
  - REST API endpoints for topics: list, detail, videos-by-topic (`/api/v1/topics`)
  - Standardized error handling with ErrorCode enum and centralized exception handlers
  - Support for topic IDs with slashes (e.g., `/m/098wr`) using path converter

### Changed
- Retrofitted existing F010 endpoints (videos, transcripts, search, preferences, sync) to use typed exceptions
- All 20 API endpoints now return consistent ErrorResponse format

### Fixed
- Topic IDs containing slashes now work correctly in URL paths
- Removed orphaned YouTube category IDs from topic_categories table (they belong in video_categories)

## [0.13.0] - 2026-02-03

### Added
- **Feature 010: FastAPI REST API Foundation**
  - RESTful API server via `chronovista api start` command
  - 11 endpoints covering videos, transcripts, search, preferences, and sync
  - Key endpoints:
    - `GET /api/v1/health` - Health check (no auth required)
    - `GET /api/v1/videos` - List videos with pagination and filtering
    - `GET /api/v1/videos/{video_id}` - Get video details
    - `GET /api/v1/videos/{video_id}/transcript` - Get full transcript
    - `GET /api/v1/videos/{video_id}/transcript/segments` - Paginated segments
    - `GET /api/v1/search/segments` - Full-text transcript search with context
    - `GET/PUT /api/v1/preferences/languages` - Language preferences
    - `POST /api/v1/sync/{operation}` - Trigger sync operations
  - OAuth integration - shares CLI authentication
  - OpenAPI documentation at `/docs` (Swagger UI) and `/redoc`
  - Pydantic V2 response schemas with pagination
  - CORS support for frontend development

### Technical
- FastAPI with async SQLAlchemy integration
- Token-based auth via CLI OAuth cache
- 207 integration tests for API endpoints
- Comprehensive error handling with standard error schema

## [0.11.0] - 2026-01-29

### Added
- **Feature 008: Transcript Segment Table (Phase 2)**
  - New `transcript_segments` table for timestamp-based transcript queries
  - Each segment stores: text, start_time, duration, end_time, sequence_number
  - Composite foreign key to video_transcripts (video_id, language_code)
  - Automatic segment creation when syncing transcripts
  - Idempotent backfill migration for existing transcripts
- **New CLI Commands: `transcript segment/context/range`**
  - `transcript segment <video_id> <timestamp>` - Get segment at specific time
  - `transcript context <video_id> <timestamp> --window 30` - Get segments around a timestamp
  - `transcript range <video_id> <start> <end>` - Get all segments in time range
  - Multiple output formats: human-readable, JSON, SRT
  - Half-open interval semantics for precise timestamp queries
- **Timestamp Format Support**
  - Flexible input: `1:30`, `01:30`, `1:30.5`, `90` (seconds)
  - Formatted output: `4:57`, `1:30:45` for hours

### Technical
- TranscriptSegmentRepository with optimized timestamp queries
- Repository `create_or_update` now auto-creates segments from raw_transcript_data
- 9 new unit tests for segment creation
- Integration tests for CLI transcript commands
- Performance indexes on start_time and end_time columns

## [0.10.0] - 2026-01-27

### Added
- **Feature 007: Transcript Timestamp Preservation**
  - 5 new columns on `video_transcripts` table:
    - `raw_transcript_data` (JSONB): Complete API response with timestamps
    - `has_timestamps` (BOOLEAN): Quick filter for timestamp availability
    - `segment_count` (INTEGER): Number of transcript segments
    - `total_duration` (FLOAT): Total transcript duration in seconds
    - `source` (VARCHAR): Transcript source identifier
  - 4 performance indexes for metadata queries
- **New CLI Command: `sync transcripts`**
  - Download transcripts for videos in your database
  - Options: `--video-id`, `--language`, `--limit`, `--force`, `--dry-run`
  - Automatic language fallback when preferred language unavailable
  - Full timestamp data preserved in JSONB format

### Technical
- Repository `create_or_update` method for idempotent transcript storage
- Performance-tested for 10,000+ transcripts (<2.5s query response)

## [0.8.0] - 2026-01-21

### Added
- Playlist ID Consolidation: `playlist_id` is now the single source of truth
  - YouTube IDs (PL prefix, 30-50 chars)
  - Internal IDs (int_ prefix, 36 chars)
  - System playlists (LL, WL, HL)
- Enhanced Takeout parsing extracts additional metadata from playlists.csv
- ID-based playlist import (no title-based deduplication)
- ABC interfaces for service layer
- Sync command framework with SyncResult and transformers

### Changed
- Refactored CLI commands to use sync command framework
- Link status now derived from `playlist_id` prefix

### Removed
- `youtube_id` column (consolidated into `playlist_id`)
- `link_status` column (now derived from prefix)
- `unresolvable_reason` column (feature removed)
- `PlaylistLinkStatus` enum

## [0.7.0] - 2026-01-16

### Added
- Channel data integrity improvements
- Type-safe repository operations
- Comprehensive channel enrichment

## [0.6.0] - 2026-01-07

### Added
- Google Takeout database seeding
- Playlist membership seeding with position tracking
- Video recovery from historical takeouts

## [0.5.0] - 2025-12-15

### Added
- Topic analytics with 17 specialized commands
- Graph visualization export (DOT/JSON)
- Interactive CLI components

## [0.1.0] - 2025-10-01

### Added
- Initial release
- CLI interface with Typer
- YouTube Data API integration
- Google Takeout import and processing
- Multi-language transcript support
- PostgreSQL database with async SQLAlchemy
- Comprehensive test suite (90%+ coverage)
- Pydantic V2 models with strict validation
- Rate-limited API client with retry logic

### Technical
- Layered architecture (CLI, Service, Repository, Database)
- Async-first design
- mypy strict mode compliance
- Factory-based test data generation
- Docker-based development database
