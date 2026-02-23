# Changelog

All notable changes to chronovista will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- MkDocs documentation setup with Material theme
- Comprehensive user guide and API reference
- Architecture documentation

## [0.32.0] - 2026-02-23

### Added
- **Feature 029: Tag Normalization Backfill Pipeline (ADR-003 Phase 2)**
  - `TagBackfillService` bulk normalization pipeline processing 141,163 tags into 124,686 canonical groups
  - `chronovista tags normalize` CLI command with `--batch-size` option and Rich progress bar
  - `chronovista tags analyze` CLI command with `--format` (table/json) for pre-backfill preview and collision review
  - `chronovista tags recount` CLI command with `--dry-run` for recalculating `alias_count` and `video_count`
  - SQLAlchemy Core `INSERT ... ON CONFLICT DO NOTHING` bulk inserts with pre-generated UUIDv7 primary keys
  - Two-pass `video_count` computation: insert with 0, then single SQL `UPDATE ... FROM (subquery JOIN)`
  - Collision detection flagging diacritic-affected merges (e.g., México/Mexico) for manual review
  - `KNOWN_FALSE_MERGE_PATTERNS` (5 entries: café, résumé, cliché, naïve, rapé) for analysis display labels
  - Per-batch transaction commits (1,000 records/batch) with idempotent re-run support
  - `get_distinct_tags_with_counts()` repository method for bulk tag extraction

### Fixed
- Tag normalization idempotency bug: `normalize("##")` → `"#"` but `normalize("#")` → `None`; changed single `#` strip to `lstrip("#")`

### Technical
- 145 new tests (37 unit + 12 integration + 17 CLI + Hypothesis property-based)
- 5,255 total tests passing with 0 regressions
- mypy strict compliance (0 errors)
- No new dependencies

## [0.31.0] - 2026-02-22

### Added
- **Feature 028a: Tag Normalization Schema & Core Service (ADR-003 Phase 1)**
  - 5 new tables: `named_entities`, `entity_aliases`, `canonical_tags`, `tag_aliases`, `tag_operation_logs` with UUIDv7 PKs, 15 indexes, all CHECK/UNIQUE/cascade constraints
  - 9-step `TagNormalizationService.normalize()` pipeline with three-tier selective diacritic stripping (8 safe Tier 1 marks stripped, Tier 2/3 preserved)
  - `selective_strip_diacritics()` standalone utility for reuse in future phases
  - `select_canonical_form()` with `str.istitle()` preference, frequency tiebreaker, alphabetical `min()` deterministic tiebreaker
  - 6 new `(str, Enum)` types: `EntityType` (8), `EntityAliasType` (6), `TagStatus` (3), `CreationMethod` (4), `DiscoveryMethod` (5), `TagOperationType` (5)
  - Pydantic V2 Base/Create/Update/Full models for all 4 main entities with state invariant validators (FR-027, FR-028)
  - 4 new repositories inheriting `BaseSQLAlchemyRepository` with ORM model aliasing
  - 5 factory-boy factories for test data generation

### Technical
- 189 new tests (71 service + 28 schema + 66 model + 24 repository)
- Hypothesis property-based tests (500 examples each) for idempotency and Tier 1 absence invariants
- 98% coverage across all new modules; 5,183 total tests with 0 regressions
- mypy strict compliance (0 errors)
- New dependency: `uuid_utils` v0.14.1

## [0.30.0] - 2026-02-19

### Added
- **Feature 027: Unified Filter & Sort System**
  - Shared `SortDropdown`, `FilterToggle` components and `useUrlParam` hooks across all 5 list pages
  - Backend `sort_by`, `sort_order`, and boolean filter params on videos, playlists, channels, and channel videos endpoints
  - Shared `SortOrder` enum for all routers; deterministic secondary sort by PK on all sorted endpoints
  - `is_subscribed` added to `ChannelListItem` schema; subscription filter tabs on Channels page
  - `FilterPills` extended with boolean pill support (Liked, Has transcripts)
  - ARIA live region announcements, scroll-to-top on filter change, focus management on all pages
  - 93 new backend tests (unit + integration), 132+ new frontend tests

### Removed
- `PlaylistSortDropdown.tsx` replaced by generic `SortDropdown`

## [0.29.0] - 2026-02-19

### Added
- **Feature 026: Local Image Cache Proxy**
  - Backend image proxy caching YouTube channel avatars and video thumbnails locally to eliminate 429 rate-limit errors
  - `ImageCacheService` with async fetch, atomic writes, magic-byte content type detection, and `.missing` marker files
  - Filesystem storage under `cache/images/` with two-character prefix sharding for video thumbnails
  - `asyncio.Semaphore(5)` concurrent fetch limiting with dual timeouts (2s on-demand, 10s warming)
  - `ImageQuality` enum: `default`, `mqdefault`, `hqdefault`, `sddefault`, `maxresdefault`
  - `GET /api/v1/images/channels/{channel_id}` proxy endpoint for channel avatars
  - `GET /api/v1/images/videos/{video_id}?quality=mqdefault` proxy endpoint for video thumbnails
  - `X-Cache` response header (`HIT`, `MISS`, `PLACEHOLDER`) and appropriate `Cache-Control`
  - `chronovista cache warm` CLI command with Rich Progress, `--type`, `--quality`, `--limit`, `--delay`, `--dry-run`
  - `chronovista cache status` CLI command with Rich table display
  - `chronovista cache purge` CLI command with `--type`, `--force`, and unavailable content warning
  - Enrichment invalidation hook: auto-deletes cached avatar when channel `thumbnail_url` changes
  - Frontend: all YouTube CDN URLs replaced with proxy URLs in ChannelCard, ChannelDetailPage, VideoCard, VideoDetailPage, PlaylistVideoCard
  - Video thumbnails added to VideoCard (`mqdefault`), VideoDetailPage (`sddefault`), and PlaylistVideoCard (`mqdefault`)
  - Client-side SVG placeholder fallback on image load error

### Fixed
- Wayback page parser failing to extract `channel_id` from pre-2020 YouTube archive pages (added `data-channel-external-id` and `<a>` anchor tag fallback extraction)

### Technical
- 108 new backend tests (45 service + 22 router + 31 CLI + 10 integration)
- 94 new frontend tests across 4 component test files
- 96 page parser tests (4 new for channel_id fallback extraction)
- Zero new third-party dependencies
- mypy strict compliance (0 errors)
- TypeScript strict mode (0 errors)

## [0.28.0] - 2026-02-17

### Added
- **Feature 025: Recovery API & Channel Archive Recovery**
  - `POST /api/v1/videos/{video_id}/recover` endpoint with year filter params and structured `RecoveryResult` response
  - `POST /api/v1/channels/{channel_id}/recover` endpoint with `ChannelRecoveryResult` response
  - `recovered_at` and `recovery_source` fields in video and channel detail API responses
  - Channel metadata recovery from Wayback Machine (title, description, subscriber count, video count, thumbnail, country)
  - Auto-channel recovery triggered during video recovery when channel is unavailable
  - CDX client `fetch_channel_snapshots()` with separate cache namespace
  - Page parser `extract_channel_metadata()` with JSON extraction and meta tag fallback
  - Channel recovery orchestrator with three-tier overwrite policy
  - Backend idempotency guard (5-minute window) preventing duplicate recovery calls
  - Recovery dependency injection via `get_recovery_deps()` in `deps.py`
  - "Recover from Web Archive" button on video and channel detail pages
  - "Re-recover from Web Archive" label when previously recovered
  - Year filter UI with collapsible "Advanced Options" section and validation
  - Zustand v5 recovery store with `persist` middleware for session-level state
  - Elapsed time counter during recovery ("Recovering... 1m 23s elapsed")
  - Cancel button with `AbortController` integration
  - `beforeunload` warning during active recovery
  - AppShell recovery indicator banner with entity link and elapsed time
  - Toast notifications for recovery completion (green) and failure (red) with 8s auto-dismiss
  - localStorage hydration UX with backend polling for orphaned sessions
  - SPA navigation guard (`useBlocker` modal) on video and channel detail pages
  - CLI `chronovista recover` channel recovery statistics in batch summary
  - Transcript panel conditionally rendered based on transcript availability (supports deleted videos with manual transcripts)
  - React Router v7 `startTransition` future flag opt-in

### Components
- `RecoverySession` Zustand store (`frontend/src/stores/recoveryStore.ts`)
- `RecoveredChannelData` and `ChannelRecoveryResult` Pydantic models
- Recovery indicator banner in AppShell
- Toast notification system for recovery events
- Navigation guard modal ("Stay"/"Leave")

### Fixed
- Recovery timeout mismatch: frontend `apiFetch` now accepts per-call timeout override (660s for recovery vs 10s default)
- `sessions.get is not a function` error on localStorage hydration (added `merge` callback for Map deserialization)
- 404 errors for `/transcript/languages` on deleted videos (gated on `transcript_summary.count > 0`)
- Transcript languages endpoint now passes `include_unavailable=true` for deleted video support

### Technical
- 1,739 passing frontend tests across 71 files
- 4,500+ passing backend tests
- 246 recovery-specific backend tests
- Zustand v5 (~3KB gzipped) for app-level recovery state
- mypy strict compliance (0 errors)
- TypeScript strict mode (0 errors)

## [0.27.0] - 2026-02-15

### Added
- **Feature 024: Wayback Video Recovery**
  - CDX API client with caching, retry logic, and `--start-year`/`--end-year` temporal anchor filtering
  - Page parser extracting metadata from `ytInitialPlayerResponse`/`ytInitialData` JSON with BeautifulSoup fallback
  - Recovery orchestrator with three-tier overwrite policy and stub channel creation for FK safety
  - `chronovista recover video` CLI command with single/batch modes, dry-run, and Rich output
  - Recovered titles displayed in frontend instead of generic "Unavailable Video" text
  - Unavailable videos visible by default across video list, channel, and playlist views

### Fixed
- Foreign key violation when recovered `channel_id` references a missing channel
- CDX client and page parser retry on transient connection errors

## [0.26.0] - 2026-02-13

### Added
- **Feature 023: Deleted Content Visibility**
  - Replaced boolean `deleted_flag` on videos with 7-value `availability_status` enum (available, unavailable, private, deleted, terminated, copyright, tos_violation)
  - Added `availability_status` and recovery tracking columns to channels table
  - Three-step atomic Alembic migration: add columns → backfill → drop `deleted_flag` (fully reversible)
  - Multi-cycle unavailability detection for videos (`enrich run`) and channels (`enrich channels`)
  - Two-cycle confirmation prevents false positives from transient API errors
  - Automatic restoration when previously unavailable content reappears in API
  - Recovery metadata: `recovered_at`, `recovery_source`, `unavailability_first_detected`
  - `include_unavailable` query parameter on 14 list/search endpoints
  - `PATCH /api/v1/videos/{video_id}/alternative-url` endpoint
  - `UnavailabilityBanner` component with status-specific messages for 12 statuses (6 video + 6 channel)
  - `AvailabilityBadge` component for list view status indicators
  - Alternative URL input form on unavailable video detail pages
  - "Include unavailable content" toggle on Videos and Search pages
  - Muted styling for unavailable items in list views
  - WCAG 2.1 AA accessibility on all new components

### Components
- `UnavailabilityBanner` - Status-specific banner with ARIA `role="status"` and `aria-live="polite"`
- `AvailabilityBadge` - Colored status badge for list items
- `AlternativeUrlForm` - URL input for unavailable video detail pages

### Fixed
- Playlist video list 500 error from `.value` on string `availability_status`
- Search results showing all videos as "Unavailable" due to missing `availability_status` in search schemas
- Channel enrichment skipping deleted channels due to batch-level exception handling

### Technical
- 4,447 passing backend tests
- 1,300+ passing frontend tests
- 273 `deleted_flag` references replaced across 44 files
- mypy strict compliance (0 errors)
- TypeScript strict mode (0 errors)

## [0.25.0] - 2026-02-12

### Added
- **Feature 022: Search-to-Transcript Deep Link Navigation**
  - Click search results to navigate directly to matched transcript segments
  - Deep link URL parameters: `lang`, `seg`, `t` for language, segment ID, and timestamp
  - `useDeepLinkParams` hook for extraction, validation, and cleanup
  - Automatic scroll-to-segment with `scrollIntoView` centering
  - Timestamp-based nearest-segment fallback when segment ID not yet loaded
  - Backend `start_time` filter for precise single-API-call seeking into long transcripts
  - Virtualization-aware pre-scroll for transcripts with 500+ segments
  - 3-second yellow highlight with fade-out animation on target segment
  - Reduced motion support (instant highlight without transition)
  - Screen reader announcement and programmatic focus on navigation
  - Auto-expand transcript panel on deep link arrival
  - Language fallback notice when requested language unavailable
  - URL cleanup via `history.replaceState` to avoid scroll-to-top

### Fixed
- Transcript panel scroll-to-top on URL cleanup (replaced `setSearchParams` with `history.replaceState`)
- Deep link accuracy for long transcripts (replaced offset estimation with backend `start_time` filter)

### Technical
- 1,403 passing frontend tests across 59 files
- Deep link test suite: 52 tests covering scroll, highlight, fallback, and edge cases

## [0.24.0] - 2026-02-11

### Added
- **Feature 021: Multi-Section Search**
  - Search across video titles and descriptions alongside transcript segments
  - New `/search/titles` and `/search/descriptions` backend endpoints
  - Snippet generation for description matches (~200 chars, word-boundary trimmed)
  - `useSearchTitles` and `useSearchDescriptions` hooks
  - `VideoSearchResult` and `SearchSection` components
  - Functional search type toggle checkboxes with at-least-one enforcement
  - URL state persistence for enabled types (`types=` parameter)
  - Per-type ARIA announcements for accessibility
  - Removed "Coming Soon" placeholders (Tags, Topics, Channels)

### Changed
- Search page background aligned with AppShell (`bg-slate-50`)
- Section headings use `text-slate-900 font-bold` for consistent contrast
- Removed `dark:` variants from search components to match app-wide light theme

### Fixed
- Generator return type in `test_fuzzy.py` for mypy strict compliance

### Technical
- 1,240 passing frontend tests across 54 files
- 56 passing backend search API tests
- WCAG 2.1 AA accessibility compliance

## [0.23.0] - 2026-02-10

### Added
- **Feature 020: Video Classification Filters**
  - Tag autocomplete with ARIA combobox pattern and keyboard navigation
  - Fuzzy "Did you mean?" suggestions for typo correction (Levenshtein distance ≤2)
  - Topic combobox with hierarchical parent/child relationships
  - Category dropdown for YouTube's 32 predefined categories
  - Filter pills with accessible remove buttons
  - Rate limiting for tag autocomplete (50 req/min)
  - Database index on video_tags(tag) for fast autocomplete
  - New `suggestions` field in TagListResponse for fuzzy matches

### Components
- `TagAutocomplete` - Accessible tag search with fuzzy suggestions
- `TopicCombobox` - Hierarchical topic selector
- `CategoryDropdown` - Category filter dropdown
- `ClassificationSection` - Combined classification filters
- `FilterPills` - Active filter display with remove buttons

### Hooks
- `useTags` - Tag autocomplete with debounced search and suggestions

### Technical
- New utility module: `src/chronovista/utils/fuzzy.py`
- `levenshtein_distance()` and `find_similar()` functions
- 24 unit tests for fuzzy matching
- 927 passing frontend tests
- WCAG 2.1 AA accessibility compliance

## [0.22.0] - 2026-02-09

### Added
- **Feature 019: Playlist Navigation & Discovery**
  - Paginated playlist grid at `/playlists` with infinite scroll
  - Filter tabs: All, YouTube-Linked, Local
  - Sort dropdown: Title (A-Z/Z-A), Date Added (Newest/Oldest), Video Count (Most/Least)
  - Playlist detail page at `/playlists/:playlistId` with video list
  - Privacy badge (Public/Private/Unlisted) and type badge (YouTube/Local)
  - Description truncation with "Show more/less" toggle
  - Deleted video indicators in playlist video lists
  - "View on YouTube" link for linked playlists
  - "In Playlists" section on video detail page
  - `GET /videos/{video_id}/playlists` endpoint
  - Sort parameters added to playlist list endpoint

### Components
- `PlaylistsPage` - Playlist grid with filters and sorting
- `PlaylistDetailPage` - Playlist detail with video list
- `PlaylistCard` - Playlist card with metadata
- `PlaylistVideoCard` - Video card with position badge
- `PlaylistFilterTabs` - Filter tab selector
- `PlaylistSortDropdown` - Sort option selector
- `PrivacyBadge` - Privacy status indicator
- `PlaylistTypeBadge` - YouTube/Local type indicator
- `PlaylistMembershipList` - Video-to-playlist chips

### Hooks
- `usePlaylists` - Playlist list with infinite scroll, filter, and sort
- `usePlaylistDetail` - Single playlist fetch
- `usePlaylistVideos` - Playlist videos with infinite scroll
- `useVideoPlaylists` - Playlists containing a video

### Technical
- 896 passing frontend tests
- 0 TypeScript errors
- URL state sync for filters and sort options

## [0.21.0] - 2026-02-08

### Added
- **Feature 018: Transcript Search Page**
  - Full-text search across all transcript segments with infinite scroll
  - Debounced search input (300ms) with 2-character minimum
  - Multi-word queries with implicit AND matching
  - Query term highlighting in search results
  - Context display (text before/after matching segments)
  - Language filter dropdown with all available languages from full result set
  - Regional variant support preserving BCP-47 codes (e.g., "en-US", "es-MX")
  - Human-readable language names (e.g., "English (US)" instead of "en-US")
  - URL state sync for shareable/bookmarkable search URLs
  - WCAG 2.1 AA accessibility compliance

### Components
- `SearchPage` - Main search container with filters
- `SearchInput` - Debounced search input
- `SearchResultList` - Infinite scroll results with virtualization
- `SearchResultCard` - Individual result display with highlighting
- `SearchFilters` - Language filter panel with responsive design
- `SearchEmptyState` - Initial and no-results states
- `SearchErrorState` - Error display with retry button
- `SearchResultSkeleton` - Loading skeleton

### Hooks
- `useSearchSegments` - Infinite scroll search with TanStack Query

### Fixed
- **Transcript Language Switching**: Video detail page now correctly switches between transcript languages with case-insensitive BCP-47 matching
- **Language Filter Dropdown**: Shows only languages that exist in search results
- **Filter Panel Visibility**: Remains visible even with 0 results

### Changed
- **Page Titles**: Browser tabs now show descriptive titles
  - `/videos` → "Videos - ChronoVista"
  - `/search` → "Search - ChronoVista"
  - `/channels` → "Channels - ChronoVista"

### Technical
- 706 passing frontend tests
- 4,302 passing backend tests
- mypy strict compliance (0 errors)
- TanStack Query v5 with `useInfiniteQuery`

## [0.20.0] - 2026-02-06

### Added
- **Feature 017: Channel Navigation & Discovery**
  - Channels list page at `/channels` with infinite scroll pagination
  - Channel cards displaying thumbnail, name, and video count
  - Channel detail page at `/channels/:channelId` with full metadata
  - Subscription status badge ("Subscribed" / "Not Subscribed")
  - Videos section with infinite scroll on channel detail
  - Clickable channel link in video detail page
  - Graceful handling of missing metadata (placeholders, fallback text)
  - 404 page for non-existent channels with navigation options
  - TanStack Query retry configuration (3 attempts, exponential backoff)
  - Scroll restoration for back navigation
  - Reduced motion CSS support (`prefers-reduced-motion`)
  - WCAG 2.1 AA contrast-compliant color tokens
  - Browserslist config (Chrome/Firefox/Edge 100+, Safari 15.4+)

### Components
- `ChannelCard` - Channel card with thumbnail, name, video count
- `VideoGrid` - Reusable video grid extracted from VideoList
- `ChannelDetailPage` - Full channel detail view

### Hooks
- `useChannels` - Channels list with infinite scroll
- `useChannelDetail` - Single channel fetch with 404 handling
- `useChannelVideos` - Channel videos with infinite scroll

### Accessibility
- Keyboard navigation for all interactive elements
- ARIA labels on channel cards and navigation
- Focus management on page navigation
- Screen reader announcements for loading states

### Technical
- React Router v6 dynamic routes
- TanStack Query v5 with `useInfiniteQuery`
- Tailwind CSS 4.x custom color tokens
- 393 passing frontend tests

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
- [Frontend README](../../frontend/README.md) - Setup, tech stack, extraction guide
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
