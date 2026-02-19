# Frontend Architecture

Overview of the chronovista web frontend architecture.

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Framework | React 19 | UI components and rendering |
| Language | TypeScript 5 (strict) | Type safety |
| Build | Vite 6 | Fast bundling with HMR |
| Styling | Tailwind CSS 4 | Utility-first CSS |
| Server State | TanStack Query 5 | Data fetching, caching, synchronization |
| Routing | React Router 6 | Client-side navigation |
| Virtualization | TanStack Virtual 3 | Efficient rendering of large lists |
| Client State | Zustand 5 | Recovery session state with persist middleware |
| API Generation | Orval 7 | TypeScript client from OpenAPI spec |

## Project Structure

```
frontend/src/
├── api/                # API configuration and generated clients
│   └── config.ts       # apiFetch utility, base URL, error handling
├── components/         # Reusable UI components
│   ├── layout/         # AppShell, Sidebar, TopNav
│   ├── transcript/     # TranscriptPanel, TranscriptSegments, LanguageSelector
│   ├── search/         # SearchPage, SearchFilters, SearchResults
│   ├── video/          # VideoCard, VideoList, VideoDetailPage
│   ├── channel/        # ChannelCard, ChannelList
│   └── playlist/       # PlaylistCard, PlaylistNavigation
├── stores/             # Zustand state stores
│   └── recoveryStore.ts           # Recovery session state with localStorage persist
├── hooks/              # Custom React hooks
│   ├── useTranscriptSegments.ts   # Infinite scroll transcript loading
│   ├── useDeepLinkParams.ts       # URL parameter handling for deep links
│   └── useDebounce.ts             # Input debouncing
├── pages/              # Page-level components (route targets)
│   ├── VideosPage.tsx
│   ├── VideoDetailPage.tsx
│   ├── ChannelsPage.tsx
│   ├── PlaylistsPage.tsx
│   ├── TranscriptSearchPage.tsx
│   └── SearchPage.tsx
├── types/              # TypeScript type definitions
│   ├── video.ts
│   ├── channel.ts
│   ├── transcript.ts
│   └── playlist.ts
├── styles/             # Design tokens and shared styles
│   └── tokens.ts       # Spacing, colors, animation config
├── App.tsx             # Root component with routing
└── main.tsx            # Application entry point
```

## Routing

Routes are defined in `App.tsx` using React Router v6:

| Path | Page | Description |
|------|------|-------------|
| `/` | VideosPage | Video library with filtering |
| `/videos/:videoId` | VideoDetailPage | Video details with transcript panel |
| `/channels` | ChannelsPage | Channel listing and discovery |
| `/channels/:channelId` | ChannelDetailPage | Channel details |
| `/playlists` | PlaylistsPage | Playlist navigation |
| `/playlists/:playlistId` | PlaylistDetailPage | Playlist videos |
| `/search` | SearchPage | Multi-section search |
| `/transcripts` | TranscriptSearchPage | Transcript-specific search |

## State Management

### Server State (TanStack Query)

All API data is managed through TanStack Query. Each data type has its own query key factory:

```typescript
// Example: transcript segments
const segmentsQueryKey = (videoId: string, languageCode: string) =>
  ["transcriptSegments", videoId, languageCode] as const;
```

Patterns used:
- `useQuery` for single-resource fetching
- `useInfiniteQuery` for paginated lists (video lists, transcript segments)
- `useMutation` for write operations
- Query invalidation for cache updates after mutations

### URL State

URL parameters drive filtering and deep linking via `useSearchParams`:

```
/videos?tags=music&category=10
/videos/abc123?t=90&lang=en
/search?q=keyword&section=segments
```

### Recovery State (Zustand)

Recovery session state is managed by a Zustand v5 store with `persist` middleware (`frontend/src/stores/recoveryStore.ts`). This store tracks active recovery operations across page navigations and browser refreshes:

```typescript
// Recovery store shape
interface RecoveryState {
  activeRecovery: {
    entityType: "video" | "channel";
    entityId: string;
    startedAt: number;
    startYear?: number;
    endYear?: number;
  } | null;
  abortController: AbortController | null;
  // actions
  startRecovery: (params: StartRecoveryParams) => void;
  cancelRecovery: () => void;
  clearRecovery: () => void;
}
```

Key behaviors:
- **localStorage persistence** via Zustand `persist` middleware for crash recovery
- **Hydration with backend polling** — on app load, if an orphaned session exists in localStorage, the store polls the backend to check if recovery completed while the tab was closed
- **AbortController integration** — `cancelRecovery()` aborts the in-flight HTTP request

### Local State

Minimal local state for UI concerns only (open/closed panels, form inputs before submission).

## Data Flow

```
Backend API (port 8765)
    ↓ HTTP/JSON
apiFetch (frontend/src/api/config.ts)
    ↓ typed response
TanStack Query cache
    ↓ reactive updates
React components
    ↓ user interactions
URL state (React Router) → triggers new queries
```

## Key Architectural Decisions

### Virtualized Lists
Long lists (transcript segments, video libraries) use `@tanstack/react-virtual` to render only visible items. A 500-segment transcript renders ~15 DOM elements at a time.

### Infinite Scroll
Transcript segments load in batches (50 initial, then 25 per page) using `useInfiniteQuery`. The `IntersectionObserver` API triggers the next page fetch.

### Deep Link Navigation
Search results link to specific transcript timestamps via URL parameters (`?t=90&lang=en`). The `seekToTimestamp` function uses the backend's `start_time` filter for precise segment loading without offset estimation.

### API Client Strategy
The project uses a hybrid approach:
- **Orval** generates typed hooks from the OpenAPI spec for stable endpoints
- **`apiFetch`** utility for direct API calls where generated hooks aren't available

### Deleted Content Visibility
Videos with `availability_status` other than `available` display status badges (e.g., "Deleted", "Private", "Unavailable") throughout the UI. Recovered videos show a "Recovered" indicator with the recovery source timestamp. Filters on the video list page allow toggling deleted content visibility via the `?include_deleted=true` query parameter.

### Recovery UX

The recovery flow (v0.28.0) provides real-time feedback for long-running Wayback Machine operations:

- **Recover button** — Appears on deleted/unavailable video and channel pages. Triggers `POST /api/v1/videos/{video_id}/recover` or `POST /api/v1/channels/{channel_id}/recover` with optional year filters
- **Progress timer** — Elapsed time display while recovery is in progress
- **AppShell recovery indicator** — A global banner in the AppShell layout shows active recovery status with entity link and elapsed time, visible from any page
- **Toast notifications** — Recovery events (started, completed, failed, cancelled) display as toast messages with 8-second auto-dismiss
- **SPA navigation guard** — `useBlocker` modal warns the user before navigating away during an active recovery, preventing accidental cancellation
- **Cancel with AbortController** — The recovery store's `cancelRecovery()` action aborts the in-flight fetch request via `AbortController`

### React Router v7 Future Flags

The app opts in to `startTransition` via React Router's `v7_startTransition` future flag, wrapping route state updates in `React.startTransition` for concurrent rendering compatibility.

### Light Theme Only
The app uses a light-only theme (`bg-slate-50` main content). Dark mode variants are not used.

## See Also

- [Frontend Development](../development/frontend-development.md) - Development workflow and testing
- [System Design](system-design.md) - Backend architecture
- [Data Model](data-model.md) - Database schema
