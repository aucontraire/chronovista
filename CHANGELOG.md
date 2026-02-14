# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

_No changes yet._

## [0.26.0] - 2026-02-13

### Added

#### Feature 023: Deleted Content Visibility

Replace the boolean `deleted_flag` on videos with a rich `availability_status` enum, add availability tracking to channels, and surface unavailable content with informational banners instead of hiding it.

**Database Migration:**
- New `availability_status` column on videos (VARCHAR(20), default `'available'`) replacing `deleted_flag`
- New `availability_status` column on channels with recovery tracking columns
- Three-step atomic migration: add columns → backfill from `deleted_flag` → drop `deleted_flag`
- Fully reversible via `alembic downgrade`
- Btree indexes on `videos.availability_status` and `channels.availability_status`
- Playlist `deleted_flag` intentionally unchanged (R8 scope decision)

**Availability Status Enum (7 values):**
- `available`, `unavailable`, `private`, `deleted`, `terminated`, `copyright`, `tos_violation`

**Multi-Cycle Unavailability Detection:**
- Videos not found during `enrich run` get `pending_confirmation` on first cycle, confirmed `unavailable` on second
- Channels not found during `enrich channels` follow the same two-cycle confirmation pattern
- Automatic restoration when previously unavailable content reappears in API responses
- Recovery metadata tracking: `recovered_at`, `recovery_source`

**API Changes:**
- Video and channel detail endpoints now return unavailable records with `availability_status` (instead of 404)
- `include_unavailable` query parameter added to 14 list/search endpoints across 8 routers
- `availability_status` field added to all video/channel list item and search result schemas
- New `PATCH /api/v1/videos/{video_id}/alternative-url` endpoint for setting alternative URLs on unavailable videos

**Frontend:**
- `UnavailabilityBanner` component with status-specific messages, icons, and colors for 6 video + 6 channel statuses
- `AvailabilityBadge` component for status indicators in list views
- Alternative URL input form on unavailable video detail pages
- "Include unavailable content" toggle on Videos page and Search page
- Muted styling (opacity + strikethrough) for unavailable items in lists
- WCAG 2.1 AA accessibility: `role="status"`, `aria-live="polite"`, keyboard-operable toggles, visible focus indicators

### Fixed
- Playlist video list 500 error: removed `.value` call on string `availability_status` from DB
- Search results incorrectly showing all videos as "Unavailable": added missing `availability_status` field to search schemas and queries
- Channel enrichment not detecting deleted channels: `get_channel_details` now returns empty list for batch lookups instead of raising exception that short-circuited per-channel detection

### Technical
- 4,447 passing backend tests
- 1,300+ passing frontend tests
- 273 `deleted_flag` references replaced across 44 files
- mypy strict compliance (0 errors)
- TypeScript strict mode (0 errors)

## [0.25.0] - 2026-02-12

### Added

#### Feature 022: Search-to-Transcript Deep Link Navigation

Click a search result to navigate directly to the matched transcript segment on the video detail page, with scroll-to-segment, highlight, and URL-based deep linking.

**Deep Link URL Parameters:**
- `lang` parameter for auto-selecting transcript language
- `seg` parameter for targeting a specific segment by database ID
- `t` parameter as timestamp fallback when segment ID unavailable
- `useDeepLinkParams` hook for extraction, validation, and cleanup

**Scroll-to-Segment Navigation:**
- Automatic scroll to target segment with `scrollIntoView` centering
- Timestamp-based nearest-segment fallback when segment ID not in loaded data
- Backend `start_time` filter for precise single-API-call seeking into long transcripts
- Virtualization-aware pre-scroll for transcripts with 500+ segments

**Visual Feedback:**
- 3-second yellow highlight with fade-out animation on target segment
- Reduced motion support (instant highlight without transition)
- Screen reader announcement on navigation completion
- Programmatic focus management for highlighted segment

**Search Result Integration:**
- Deep link URLs generated in `SearchResult` component with `lang`, `seg`, `t` params
- Auto-expand transcript panel on deep link arrival
- Language fallback notice when requested language unavailable
- URL cleanup via `history.replaceState` after navigation completes

### Fixed
- Transcript panel scroll-to-top on URL cleanup (replaced `setSearchParams` with `history.replaceState` to bypass `ScrollRestoration`)
- Deep link navigation accuracy for long transcripts (replaced offset estimation with backend `start_time` filter)

## [0.24.0] - 2026-02-11

### Added

#### Feature 021: Multi-Section Search

Search across video titles and descriptions alongside transcript segments, with stacked sectioned layout, parallel independent loading, and toggle checkboxes.

**Title & Description Search:**
- New `/search/titles` and `/search/descriptions` backend endpoints with ILIKE pattern matching
- Snippet generation (~200 chars centered around first match, word-boundary trimmed)
- `useSearchTitles` and `useSearchDescriptions` TanStack Query hooks
- `VideoSearchResult` component for title/description result cards with highlighted matches
- `SearchSection` reusable wrapper with header count display, loading spinner, and inline error with retry

**Search Type Toggles:**
- Functional checkboxes for Transcripts, Video Titles, and Descriptions
- At-least-one enforcement (last remaining checkbox becomes disabled)
- URL state persistence via `types=` parameter (comma-separated)
- Per-type ARIA announcement: "Found 3 title, 12 description, and 847 transcript matches"

**UI Polish:**
- Removed "Coming Soon" placeholders for Tags, Topics, Channels (handled by Videos page faceted filters)
- Updated search placeholder and hero text for multi-section context
- Result counts displayed on all three filter checkboxes
- Consistent `bg-slate-50` background matching other pages

### Changed
- Search page background aligned with AppShell (`bg-slate-50` instead of `bg-gray-50`)
- Section headings use `text-slate-900 font-bold` for consistent contrast
- Removed `dark:` color variants from search components to match app-wide light theme

### Fixed
- Generator return type in `tests/unit/utils/test_fuzzy.py` (mypy strict compliance)

## [0.23.0] - 2026-02-10

### Added

#### Feature 020: Video Classification Filters

Filter and browse videos by tags, topics, and categories with accessible UI components and fuzzy search suggestions.

**Tag Autocomplete (T029, T049b):**
- ARIA combobox pattern with role="combobox", aria-expanded, aria-autocomplete="list"
- Debounced search (300ms) using useTags hook
- Maximum tag limit validation (10 tags)
- Keyboard navigation (Arrow Up/Down, Enter, Escape, Tab, Home/End)
- Filter pills with remove buttons
- **Fuzzy "Did you mean?" suggestions** when no exact matches found
- Levenshtein distance algorithm for typo correction (max distance: 2)
- Backend returns up to 10 suggestions; frontend shows first 3 unselected

**Topic Combobox:**
- Hierarchical topic selection with parent/child relationships
- ARIA combobox with listbox pattern

**Category Dropdown:**
- YouTube's 32 predefined categories
- Simple select dropdown with ARIA attributes

**Backend Enhancements:**
- Rate limiting for tag autocomplete (50 req/min)
- Fuzzy suggestion query with length-based filtering for performance
- Database index on video_tags(tag) for fast autocomplete
- New `suggestions` field in TagListResponse schema

**New Utility Module:**
- `src/chronovista/utils/fuzzy.py` with `levenshtein_distance()` and `find_similar()`
- Modularized from language_commands.py for reuse across codebase

**Testing:**
- 24 unit tests for fuzzy matching utilities
- Frontend component tests with accessibility validation
- Error handling and retry button tests

### Technical
- 927 passing frontend tests
- mypy strict compliance (0 errors)
- WCAG 2.1 AA accessibility compliance

## [0.22.0] - 2026-02-09

### Added

#### Feature 019: Playlist Navigation & Discovery

Browse and navigate playlists with filtering, sorting, and video-to-playlist discovery.

**Playlist Browsing (User Story 1 - P1):**
- Paginated grid of playlists at `/playlists` route
- Filter tabs: All, YouTube-Linked, Local
- Sort dropdown: Title (A-Z/Z-A), Date Added (Newest/Oldest), Video Count (Most/Least)
- Infinite scroll with 25 playlists per page
- Loading skeleton, empty state, and error state with retry
- Privacy badge (Public/Private/Unlisted) and type badge (YouTube/Local)

**Playlist Details (User Story 2 - P2):**
- Playlist detail page at `/playlists/:playlistId`
- Header with title, description, video count, privacy, published date
- Description truncation with "Show more/less" toggle
- Ordered video list with position badges (#1, #2, etc.)
- Deleted video indicators (opacity + strikethrough)
- "View on YouTube" link for linked playlists
- Back navigation and 404 handling

**Video-to-Playlist Navigation (User Story 3 - P3):**
- "In Playlists" section on video detail page
- Clickable playlist chips linking to playlist details
- Conditional rendering (hidden when video is in no playlists)

**Backend:**
- `GET /videos/{video_id}/playlists` endpoint
- Sort parameters (`sort_by`, `sort_order`) added to playlist list endpoint

**Testing:**
- 140+ new tests for playlist components, hooks, and pages
- Fixed TypeScript errors in existing test files

## [0.21.0] - 2026-02-08

### Added

#### Feature 018: Transcript Search Page

Full-text search across all transcript segments with language filtering and infinite scroll.

**Search Features:**

- **Search Input**: Debounced text input (300ms) with 2-character minimum
- **Multi-Word Queries**: Implicit AND matching for multiple search terms
- **Infinite Scroll**: Load more results automatically as user scrolls
- **Result Highlighting**: Query terms highlighted in search results
- **Context Display**: Shows text before and after matching segments

**Language Filter:**

- **Available Languages Dropdown**: Shows all languages in full result set (not just loaded results)
- **Regional Variant Support**: Preserves BCP-47 regional codes (e.g., "en-US", "es-MX") for dialect context
- **Case-Insensitive Matching**: Language filter works regardless of case variations
- **Human-Readable Names**: Displays "English (US)" instead of raw "en-US" codes

**URL State Sync:**

- **Shareable URLs**: Query and language filter synced to URL parameters (`?q=search&language=en`)
- **Browser History**: Back/forward navigation restores search state
- **Bookmarkable**: Direct links to specific searches work correctly

**Accessibility (WCAG 2.1 AA):**

- Skip link to search results
- ARIA live region for search status announcements
- `aria-busy` on results region during loading
- Semantic landmark structure (header, main, complementary)
- Keyboard navigation support

**New Components:**

| Component | Path | Purpose |
|-----------|------|---------|
| `SearchPage` | `pages/SearchPage.tsx` | Main search container |
| `SearchInput` | `components/SearchInput.tsx` | Debounced search input |
| `SearchResultList` | `components/SearchResultList.tsx` | Infinite scroll results |
| `SearchResultCard` | `components/SearchResultCard.tsx` | Individual result display |
| `SearchFilters` | `components/SearchFilters.tsx` | Language filter panel |
| `SearchEmptyState` | `components/SearchEmptyState.tsx` | Initial/no-results states |
| `SearchErrorState` | `components/SearchErrorState.tsx` | Error display with retry |
| `SearchResultSkeleton` | `components/SearchResultSkeleton.tsx` | Loading skeleton |

**New Hook:**

| Hook | Purpose |
|------|---------|
| `useSearchSegments` | Infinite scroll search with TanStack Query |

**Backend Enhancements:**

- Added `available_languages` field to search API response
- Case-insensitive language filtering with `func.lower()`
- Optimized language extraction query for accurate dropdown population

### Fixed

- **Transcript Language Switching**: Video detail page now correctly switches between transcript languages
  - Backend: Added case-insensitive matching for BCP-47 language codes (RFC 5646 compliant)
  - Frontend: Fixed query parameter name mismatch (`language_code` → `language`)
- **Language Filter Dropdown**: Now shows only languages that actually exist in search results
- **Filter Panel Visibility**: Language filter panel remains visible even with 0 results

### Changed

- **Page Titles**: Browser tabs now show descriptive titles for easier navigation
  - `/videos` → "Videos - ChronoVista"
  - `/search` → "Search - ChronoVista"
  - `/channels` → "Channels - ChronoVista"

### Technical

- 706 passing frontend tests
- 4,302 passing backend tests
- mypy strict compliance (0 errors)
- TanStack Query v5 with `useInfiniteQuery` for search pagination

## [0.20.0] - 2026-02-06

### Added

#### Feature 017: Channel Navigation & Discovery

Frontend feature enabling users to browse channels, view channel details with subscription status and videos, and navigate from video detail to channel pages.

**User Story 1: Browse All Channels (MVP)**

- Channels list page at `/channels` route
- Channel cards displaying thumbnail, name, and video count (in database)
- Infinite scroll pagination with Intersection Observer
- Loading skeletons during data fetch
- Empty state when no channels exist
- Channels sorted by video count (descending, from API)

**User Story 2: View Channel Details**

- Channel detail page at `/channels/:channelId` route
- Channel header with thumbnail, name, description
- Metadata display: subscriber count, video count (from YouTube), country
- Subscription status badge ("Subscribed" / "Not Subscribed")
- Videos section with infinite scroll
- Graceful handling of missing metadata (placeholders, fallback text)
- 404 page for non-existent channels with navigation options

**User Story 3: Navigate from Video to Channel**

- Channel name in video detail is now a clickable link
- Hover state indicating clickability
- "Unknown Channel" fallback for null channels

**New Components:**

| Component | Path | Purpose |
|-----------|------|---------|
| `ChannelCard` | `components/ChannelCard.tsx` | Channel card for list display |
| `VideoGrid` | `components/VideoGrid.tsx` | Reusable video grid (extracted from VideoList) |
| `ChannelDetailPage` | `pages/ChannelDetailPage.tsx` | Channel detail view |

**New Hooks:**

| Hook | Purpose |
|------|---------|
| `useChannels` | Channels list with infinite scroll |
| `useChannelDetail` | Single channel fetch with 404 handling |
| `useChannelVideos` | Channel videos with infinite scroll |

**Infrastructure:**

- **TanStack Query**: Retry configuration (3 attempts, exponential backoff for 5xx/network errors)
- **Scroll Restoration**: Preserves position on back navigation via React Router
- **Reduced Motion**: CSS support for `prefers-reduced-motion` preference
- **WCAG 2.1 AA**: Contrast-compliant color tokens for subscription status
- **Browser Support**: Browserslist config for Chrome/Firefox/Edge 100+, Safari 15.4+

**Accessibility (WCAG 2.1 AA):**

- Keyboard navigation for all interactive elements
- ARIA labels on channel cards and navigation elements
- Focus management on page navigation
- Visible focus indicators
- Screen reader announcements for loading states

**Edge Cases Handled:**

- EC-001: Missing thumbnail → placeholder image
- EC-002: Missing description → "No description available"
- EC-003: Channel with 0 videos → empty state message
- EC-004: Missing metadata → hide unavailable fields
- EC-005: Non-existent channel → 404 page with navigation
- EC-006: Long channel names → truncation with ellipsis
- EC-007: Infinite scroll timeout → inline error with retry
- EC-008: Partial page load → independent retry for videos section

**Technical Details:**

- React Router v6 dynamic routes
- TanStack Query v5 with `useInfiniteQuery`
- Tailwind CSS 4.x with custom color tokens
- TypeScript strict mode (0 errors)
- 393 passing tests

## [0.19.0] - 2026-02-06

### Added

#### Feature 016: Video Detail Page with Transcript Display

A dedicated video detail page with comprehensive metadata display and multi-language transcript support.

**Video Detail Features:**

- **Browser Tab Title**: Shows "Channel Name - Video Title" for easy tab identification
- **Absolute Date Display**: Upload dates shown as "Jan 15, 2024" instead of relative "1 week ago"
- **Full Language Codes**: Transcript language selector shows full BCP-47 codes (e.g., "EN-gb" vs "EN") to distinguish variants
- **Video Metadata**: Title, channel, upload date, duration, view count, like count, description, tags
- **Watch on YouTube**: External link button with proper `target="_blank"` and `rel="noopener noreferrer"`
- **Back Navigation**: Consistent "Back to Videos" links

**Transcript Panel Features:**

- **Collapsible Panel**: Expand/collapse with CSS-only 200ms animation
- **Language Selector**: WAI-ARIA tabs pattern with keyboard navigation (Arrow keys, Home/End)
- **Quality Indicators**: Checkmark (✓) badge for manual/CC transcripts
- **View Mode Toggle**: Switch between Segments and Full Text views
- **Infinite Scroll**: Virtualized segments with 50 initial + 25 subsequent batch loading
- **Debounced Language Switch**: 150ms debounce with request cancellation

**Accessibility (WCAG 2.1 AA):**

- `prefers-reduced-motion` support for expand/collapse animation
- `aria-expanded`, `aria-controls` on toggle button
- `role="tablist"` and `role="tab"` for language selector
- `aria-live="polite"` announcements for language changes
- Visible focus indicators on all interactive elements

**New Components:**

| Component | Path | Purpose |
|-----------|------|---------|
| `VideoDetailPage` | `pages/VideoDetailPage.tsx` | Main detail page |
| `TranscriptPanel` | `components/transcript/TranscriptPanel.tsx` | Collapsible transcript container |
| `LanguageSelector` | `components/transcript/LanguageSelector.tsx` | Language tab selector |
| `ViewModeToggle` | `components/transcript/ViewModeToggle.tsx` | Segments/Full Text toggle |
| `TranscriptSegments` | `components/transcript/TranscriptSegments.tsx` | Virtualized segment list |
| `TranscriptFullText` | `components/transcript/TranscriptFullText.tsx` | Continuous prose view |

**New Hooks:**

| Hook | Purpose |
|------|---------|
| `useVideoDetail` | Fetch video metadata |
| `useTranscriptLanguages` | Fetch available transcript languages |
| `useTranscript` | Fetch full transcript text |
| `useTranscriptSegments` | Infinite scroll for transcript segments |
| `usePrefersReducedMotion` | Detect reduced motion preference |

**New Route:**

- `/videos/:videoId` - Video detail page with transcript panel

**Technical Details:**

- React Router v6 dynamic route with `useParams`
- TanStack Query v5 with `useInfiniteQuery` for segments
- `@tanstack/react-virtual` v3.10+ for windowed virtualization
- Design tokens extracted to `frontend/src/styles/tokens.ts`
- 255 passing tests (24 new tests for this feature)

## [0.18.0] - 2026-02-06

### Added

#### Feature 015: Navigation Shell & Application Layout

A persistent navigation shell with sidebar, header, and client-side routing for the React frontend.

**Navigation Features:**

- **Persistent Sidebar**: Left navigation bar visible on all pages with icons for Videos, Search, and Channels
- **Active State Highlighting**: Current page indicated with `bg-slate-800`, white text, and 3px blue left border
- **Client-Side Routing**: React Router v6 with `createBrowserRouter` for instant page transitions
- **Browser History Support**: Back/forward buttons work correctly; page refresh preserves route
- **Bookmarkable URLs**: Direct URL access to `/videos`, `/search`, `/channels`
- **404 Page**: Invalid routes show "Page Not Found" with link back to Videos
- **Root Redirect**: `/` redirects to `/videos`

**Responsive Design:**

| Breakpoint | Sidebar Width | Display |
|------------|---------------|---------|
| ≥1024px | 240px | Icons + labels |
| <1024px | 64px | Icons only + tooltips on hover |

**Accessibility (WCAG 2.1 AA):**

- `<nav aria-label="Main navigation">` landmark
- `aria-current="page"` on active nav item
- `aria-hidden="true"` on decorative icons
- 44×44px minimum touch targets
- Keyboard navigation (Tab/Shift+Tab)
- Visible focus ring (`ring-2 ring-blue-500`)

**Error Handling:**

- Error boundary wraps page content
- Fallback UI with error message, "Try Again" button, and link to `/videos`
- Navigation shell remains functional during page errors

**New Components:**

| Component | Path | Purpose |
|-----------|------|---------|
| `AppShell` | `components/layout/AppShell.tsx` | CSS Grid layout wrapper |
| `Sidebar` | `components/layout/Sidebar.tsx` | Navigation sidebar |
| `Header` | `components/layout/Header.tsx` | App header with "Chronovista" title |
| `NavItem` | `components/layout/NavItem.tsx` | Navigation link with active state |
| `ErrorBoundary` | `components/ErrorBoundary.tsx` | Error boundary with fallback UI |
| `VideoIcon` | `components/icons/VideoIcon.tsx` | SVG icon component |
| `SearchIcon` | `components/icons/SearchIcon.tsx` | SVG icon component |
| `ChannelIcon` | `components/icons/ChannelIcon.tsx` | SVG icon component |

**New Pages:**

| Page | Route | Status |
|------|-------|--------|
| Search | `/search` | Placeholder ("Coming Soon") |
| Channels | `/channels` | Placeholder ("Coming Soon") |
| NotFound | `/*` | 404 error page |

**Visual Design:**

- Sidebar: `bg-slate-900`
- Active nav: `bg-slate-800`, `text-white`, `border-l-[3px] border-blue-500`
- Inactive nav: `text-slate-400`, hover: `bg-slate-800/50`
- Header: `bg-white`, 64px height, `border-b border-slate-200`
- Content area: `bg-slate-50`

**Technical Details:**

- React Router v6.22.0 with `createBrowserRouter` API
- CSS Grid layout: `grid-cols-[auto_1fr]`
- `RouterProvider` wraps `QueryClientProvider`
- Route configuration in `frontend/src/router/index.tsx`
- Existing video list functionality preserved at `/videos`

## [0.17.0] - 2026-02-05

### Added

#### Feature 014: Frontend Foundation with Vite + React

A modern React-based web frontend for browsing your video library, built with clean separation patterns for future extraction.

**Tech Stack:**

| Technology | Version | Purpose |
|------------|---------|---------|
| Vite | 6.x | Build tool and dev server |
| React | 19.x | UI framework |
| TypeScript | 5.x | Type-safe JavaScript (strict mode) |
| Tailwind CSS | 4.x | Utility-first styling |
| TanStack Query | 5.x | Async state management |
| Orval | 7.x | OpenAPI to TypeScript client generation |

**New Makefile Targets:**

```bash
make dev            # Start both backend (8765) and frontend (8766)
make dev-backend    # Backend only
make dev-frontend   # Frontend only
make generate-api   # Regenerate TypeScript client from OpenAPI
```

**Key Features:**

- **Video List View**: Browse videos with infinite scroll pagination (25 items/page)
- **Auto-Generated Types**: TypeScript types from FastAPI's OpenAPI spec via Orval
- **State Components**: Loading skeletons, contextual error messages, empty state guidance
- **CORS Support**: Backend accepts requests from frontend dev server
- **Extractable Architecture**: `git subtree split -P frontend` produces standalone repo

**Frontend Structure:**

```
frontend/
├── src/
│   ├── api/          # API configuration
│   ├── components/   # VideoCard, LoadingState, ErrorState, EmptyState
│   ├── hooks/        # useVideos with infinite scroll
│   ├── pages/        # HomePage
│   └── types/        # TypeScript interfaces
├── vite.config.ts    # Vite + Tailwind v4 plugin
└── orval.config.ts   # API client generation
```

**Environment Variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `CHRONOVISTA_API_PORT` | 8765 | Backend API port |
| `CHRONOVISTA_FRONTEND_PORT` | 8766 | Frontend dev server port |
| `VITE_API_BASE_URL` | `http://localhost:8765/api/v1` | API base URL for frontend |

**Prerequisites:**

- Node.js 22.x LTS or 20.x LTS (22.x recommended for Orval compatibility)
- npm 10.x or higher

**Quick Start:**

```bash
cd frontend && npm install
make dev              # Starts both servers
open http://localhost:8766
```

See [`frontend/README.md`](frontend/README.md) for detailed documentation.

## [0.16.0] - 2026-02-05

### Added

#### Feature 013: RFC 7807 API Response Standardization

**BREAKING CHANGE**: All API error responses now use the RFC 7807 Problem Details format.

This feature standardizes error responses across all API endpoints, providing a consistent, machine-readable format that enables better error handling and debugging.

**Key Changes:**

| Aspect | Before | After |
|--------|--------|-------|
| Content-Type | `application/json` | `application/problem+json` |
| Response Structure | Custom nested format | RFC 7807 flat structure |
| Request Correlation | None | `X-Request-ID` header |

**New Error Response Format:**

```json
{
  "type": "https://api.chronovista.com/errors/NOT_FOUND",
  "title": "Resource Not Found",
  "status": 404,
  "detail": "Video 'xyz' not found",
  "instance": "/api/v1/videos/xyz",
  "code": "NOT_FOUND",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Request ID Correlation:**

- Every response includes an `X-Request-ID` header
- Clients can provide their own correlation ID (echoed in response)
- Server generates UUID v4 if no client ID provided
- Request ID included in both headers and error response body

**Supported Error Codes:**

- `NOT_FOUND` (404)
- `BAD_REQUEST` (400)
- `VALIDATION_ERROR` (422) - includes field-level `errors` array
- `NOT_AUTHENTICATED` (401)
- `NOT_AUTHORIZED` (403)
- `CONFLICT` (409)
- `RATE_LIMITED` (429) - includes `Retry-After` header
- `INTERNAL_ERROR` (500)
- `DATABASE_ERROR` (500)
- `EXTERNAL_SERVICE_ERROR` (502)
- `SERVICE_UNAVAILABLE` (503)

**Migration Required:**

Clients must update error parsing logic. See [Migration Guide](src/chronovista/docs/api/rfc7807-migration.md) for before/after examples and client integration snippets.

**Documentation:**

- [API Error Responses](src/chronovista/docs/api/error-responses.md) - Complete RFC 7807 reference
- [Migration Guide](src/chronovista/docs/api/rfc7807-migration.md) - Client migration guide

## [0.15.0] - 2026-02-05

### Added

#### Feature 012: Content Classification APIs

REST API endpoints for browsing YouTube categories and video tags, completing the "classification trifecta" alongside Topics (Feature 011).

**6 New API Endpoints:**

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/categories` | GET | List categories sorted by video count |
| `/api/v1/categories/{category_id}` | GET | Get category details |
| `/api/v1/categories/{category_id}/videos` | GET | List videos in category |
| `/api/v1/tags` | GET | List tags sorted by video count |
| `/api/v1/tags/{tag}` | GET | Get tag details |
| `/api/v1/tags/{tag}/videos` | GET | List videos with tag |

**Key Features:**

- **Categories**: YouTube's 32 predefined content categories (Music, Gaming, Education, etc.)
- **Tags**: 139,763 unique creator-defined keywords
- **Sorting**: Categories and tags sorted by video_count descending
- **Pagination**: Standard limit (1-100) and offset parameters
- **URL Encoding**: Tags with special characters supported (spaces, hashtags)
- **Consistent Errors**: 404 for invalid IDs, 422 for validation errors

**Example Usage:**

```bash
# List top categories
curl http://localhost:8000/api/v1/categories

# Get videos in Music category
curl http://localhost:8000/api/v1/categories/10/videos

# List popular tags
curl http://localhost:8000/api/v1/tags

# Get videos with a specific tag (URL-encoded space)
curl "http://localhost:8000/api/v1/tags/hip%20hop/videos"
```

**Technical Details:**

- 33 new integration tests (13 category + 20 tag tests)
- Pydantic V2 response schemas with strict validation
- mypy strict compliance (0 errors)
- Video listings exclude deleted videos and sort by upload_date descending

## [0.14.0] - 2026-02-04

### Added
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
