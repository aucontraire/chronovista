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
│   │   └── corrections/  # CorrectionBadge, SegmentEditForm, RevertConfirmation, CorrectionHistoryPanel
│   ├── search/         # SearchPage, SearchFilters, SearchResults
│   ├── video/          # VideoCard, VideoList, VideoDetailPage
│   ├── channel/        # ChannelCard, ChannelList
│   ├── batch/          # BatchCorrectionsPage components: PatternInput, MatchCard, EntityAutocomplete
│   ├── entity/         # EntityMentionsPanel (manual entity-video associations)
│   └── playlist/       # PlaylistCard, PlaylistNavigation
├── stores/             # Zustand state stores
│   └── recoveryStore.ts           # Recovery session state with localStorage persist
├── hooks/              # Custom React hooks
│   ├── useTranscriptSegments.ts   # Infinite scroll transcript loading
│   ├── useDeepLinkParams.ts       # URL parameter handling for deep links
│   ├── useDebounce.ts             # Input debouncing
│   ├── useEntitySearch.ts           # Debounced entity name/alias search
│   ├── useEntityDetail.ts           # Entity detail with aliases for mismatch check
│   └── useEntityMentions.ts         # Video entity associations, manual link/unlink with optimistic updates
├── pages/              # Page-level components (route targets)
│   ├── VideosPage.tsx
│   ├── VideoDetailPage.tsx
│   ├── ChannelsPage.tsx
│   ├── PlaylistsPage.tsx
│   ├── TranscriptSearchPage.tsx
│   ├── SearchPage.tsx
│   ├── BatchCorrectionsPage.tsx
│   └── EntityDetailPage.tsx
├── types/              # TypeScript type definitions
│   ├── video.ts
│   ├── channel.ts
│   ├── transcript.ts
│   ├── corrections.ts  # CorrectionType, CorrectionAuditRecord, SegmentEditState
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
| `/corrections/batch` | BatchCorrectionsPage | Batch find-and-replace corrections |
| `/entities/:entityId` | EntityDetailPage | Entity detail with aliases and videos |

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
- `useMutation` for write operations with optimistic updates (transcript corrections)
- Direct cache patching via `queryClient.setQueryData` for instant UI updates without refetch
- Query invalidation only on error (rollback scenario)

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

### Inline Transcript Corrections (v0.38.0)

The correction UI (Feature 035) enables inline editing of transcript segments directly in the transcript panel:

- **SegmentEditState discriminated union** — Each segment is in one of four mutually exclusive states: `read`, `editing`, `confirming-revert`, or `history`. This prevents impossible UI states (e.g., editing and viewing history simultaneously)
- **Single-edit-at-a-time** — Only one segment can be in a non-read state at a time. Entering edit mode on segment B automatically cancels segment A
- **Optimistic updates** — `useCorrectSegment` applies text changes to the TanStack Query cache immediately on mutate, rolls back on error, and overwrites with authoritative server values on success. Revert uses server-confirmed state only (no optimistic updates)
- **Cache patching** — Both mutation hooks patch the specific segment within the infinite query pages via `queryClient.setQueryData`, preserving scroll position. `invalidateQueries` is never called on success
- **Correction components** — Four components in `components/transcript/corrections/`: `CorrectionBadge` (visual indicator), `SegmentEditForm` (inline textarea + type select + validation), `RevertConfirmation` (confirm/cancel row), `CorrectionHistoryPanel` (audit record list with pagination)
- **Focus management** — Edit mode focuses textarea, revert focuses Confirm button, Escape restores focus to the originating button. `stopPropagation` prevents parent scroll handler from intercepting keystrokes
- **Screen reader support** — Dedicated `aria-live` region announces all state transitions (edit entered, saved, cancelled, revert shown/completed, history opened, errors)

### Batch Corrections & Entity Linking (v0.44.0)

The batch corrections page (Feature 041/043) provides a visual find-and-replace workflow with entity linking:

- **`EntityAutocomplete`** — ARIA combobox driven by the replacement text field. Searches entities and aliases via `GET /entities?search=...&search_aliases=true&exclude_alias_types=asr_error`. 300ms debounce, 2-char minimum, keyboard navigation (ArrowDown/Up, Enter, Escape)
- **Entity pill** — Selected entity displayed as a dismissible badge with canonical name, type label, external link to entity detail page (new tab), and dismiss button
- **Mismatch warning** — Amber non-blocking warning when replacement text doesn't match canonical name or any registered alias. Uses `useEntityDetail` hook to fetch alias data (backend filters out `asr_error` aliases)
- **`useEntitySearch`** — Debounced search hook returning `EntityListItem[]` from the entities list endpoint
- **`useEntityDetail`** — TanStack Query hook fetching entity detail including aliases for mismatch checking. 5-minute stale time, disabled when no entity selected
- **`AddAliasForm`** — Inline form on `EntityDetailPage` for creating new aliases via `POST /entities/{id}/aliases`. TanStack Query cache invalidation on success
- **State flow** — `selectedEntity` state in `BatchCorrectionsPage` drives: autocomplete display, pill rendering, entity_id inclusion in apply request, mismatch computation. The `entityAliasNames` from `useEntityDetail` are passed down to `PatternInput` for local mismatch checking

### Manual Entity-Video Associations (v0.51.0)

The `EntityMentionsPanel` (Feature 050) enables manual entity-video linking directly from the video detail page:

- **Entity search autocomplete** — `useEntitySearch` hook searches entities by name and aliases via `GET /entities/search?q=...&video_id=...`. Already manually-linked entities are disabled with "Already linked" label; transcript-linked entities remain selectable
- **Create association** — `useCreateManualAssociation` mutation calls `POST /videos/{videoId}/entities/{entityId}/manual`, then invalidates `video-entities`, `entitySearch`, and `entity-videos` caches
- **Delete with optimistic updates** — `useDeleteManualAssociation` implements full optimistic update lifecycle:
  - `onMutate`: cancels in-flight queries, snapshots cache, applies optimistic removal (manual-only entities removed from list; multi-source entities have `has_manual` cleared)
  - `onError`: rolls back to snapshot
  - `onSuccess`: invalidates with `refetchType: "none"` for video-entities (prevents race with optimistic update), immediate refetch for `entitySearch`, `entity-videos`, `entity-detail`
- **204 No Content handling** — `apiFetch` returns `undefined` for 204/205 responses without calling `response.json()`, preventing `SyntaxError` on empty body
- **Multi-source display** — `VideoEntitySummary` includes `has_manual` flag and `sources` array for source badge rendering (`[TRANSCRIPT ×N]`, `[MANUAL]`)

### React Router v7 Future Flags

The app opts in to `startTransition` via React Router's `v7_startTransition` future flag, wrapping route state updates in `React.startTransition` for concurrent rendering compatibility.

### Light Theme Only
The app uses a light-only theme (`bg-slate-50` main content). Dark mode variants are not used.

## See Also

- [Frontend Development](../development/frontend-development.md) - Development workflow and testing
- [System Design](system-design.md) - Backend architecture
- [Data Model](data-model.md) - Database schema
