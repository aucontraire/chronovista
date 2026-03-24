# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- MkDocs documentation setup with Material theme
- Comprehensive user guide and API reference

## [0.52.0] - 2026-03-23

### Added
- **Feature 051: Entity Creation Form (ADR-006 Increment E)**
  - **Tag-Backed Entity Creation (US1)**: "Create Entity" button on entities page opens modal form with ARIA `dialog` role and focus trap; name field with autocomplete searching canonical tags by prefix (debounced, 2-char minimum); autocomplete results show canonical form, video count, and alias count; selecting a tag pre-fills name and shows "Creating from tag" chip; entity type selector with all 8 entity-producing types (person, organization, place, event, work, technical_term, concept, other) with tooltips; optional description field; submit calls `POST /api/v1/entities/classify` using TagManagementService.classify(); on success modal closes and entity list refreshes
  - **Standalone Entity Creation (US2)**: When no matching tag exists, user proceeds with typed name as freeform entry; form indicates "Creating standalone entity (not linked to a tag)"; repeatable alias field (add/remove, max 20) with `aria-live="polite"` mode transition announcements; submit calls `POST /api/v1/entities` with auto-title-casing and normalization; on success modal closes and entity list refreshes
  - **Duplicate Detection (US3)**: Real-time debounced check via `GET /api/v1/entities/check-duplicate` with normalized name and entity type; warning block with `aria-live="assertive"` showing existing entity's name, type, and description; Link to existing entity detail page; submission blocked when duplicate exists; warning clears when name or type changes
  - **Entity Creation API**: `POST /api/v1/entities/classify` wraps TagManagementService.classify() with 404/409/400 error mapping; `GET /api/v1/entities/check-duplicate` with in-memory rate limiting (50 req/min); `POST /api/v1/entities` for standalone creation with alias deduplication
  - **EntityType Enum Expansion**: Added `concept` and `other` entity types across full stack (Pydantic enums, DB check constraints, frontend constants, entity type tabs)

### Fixed
- Tag normalization idempotency bug: `normalize('´#')` returned `'#'` but `normalize('#')` returned `None`; added second `lstrip('#')` pass after diacritic removal to ensure `normalize(normalize(x)) == normalize(x)` for all inputs
- `EntitiesPage.test.tsx` missing mock stubs for `useClassifyTag`, `useCreateEntity`, `useCheckDuplicate`, `useCreateManualAssociation`, `useDeleteManualAssociation` — caused 93 test failures when running full suite (CreateEntityModal hooks called outside QueryClientProvider)
- `EntitiesPage.test.tsx` entity type tab count assertion updated from 7 to 9 tabs (added Technical Term and Concept)

### Technical
- 3 new API endpoints (classify entity from tag, check duplicate, create standalone entity)
- 1 new frontend component (`CreateEntityModal`), 3 new TanStack Query hooks (`useClassifyTag`, `useCreateEntity`, `useCheckDuplicate`), 1 new constants module (`entityTypes.ts`)
- 158 new tests: 49 backend unit, 70 frontend component, 10 backend integration, 29 frontend hook tests
- 7,403 total backend tests, 3,519 total frontend tests
- Frontend version: 0.20.0 → 0.21.0
- TypeScript strict mode (0 errors), mypy strict compliance (0 errors)
- No new dependencies, no database migrations
- WCAG 2.1 AA: ARIA dialog, combobox, focus trap, keyboard navigation (Escape/Tab/Arrow), aria-live announcements

## [0.51.0] - 2026-03-22

### Added
- **Feature 050: Manual Video-Level Entity Mentions (ADR-006 Increment D)**
  - **Manual Entity-Video Association (US1)**: `EntityMentionsPanel` on video detail page with entity search autocomplete against existing `named_entities`; selecting an entity creates an `entity_mentions` row with `detection_method='manual'` and `segment_id=NULL`; duplicate prevention (409); already-linked entities shown as disabled with "Already linked" label; search driven by `useEntitySearch` hook with 300ms debounce and 2-char minimum
  - **Multi-Source Entity Video List (US2)**: Entity detail page shows videos from ALL sources (transcript, manual, user_correction) with source badges (`[TRANSCRIPT ×N]`, `[MANUAL]`); deduplication via `_SOURCE_CATEGORY_MAP` mapping detection methods to display categories; `has_manual` flag and `sources` array on `VideoEntitySummary` response; entity header stats reflect combined video count across all sources
  - **Remove Manual Association (US3)**: Unlink button with confirmation dialog on manually-linked entities; `DELETE /api/v1/videos/{video_id}/entities/{entity_id}/manual` returns 204 No Content; optimistic cache update with rollback on error; only manual associations can be removed (transcript-derived mentions cannot be deleted from UI)
  - **Entity Search API**: `GET /api/v1/entities/search?q=...&video_id=...` returns entity matches with `is_linked` and `link_sources` fields indicating existing associations for the given video
  - **Manual Association API**: `POST /api/v1/videos/{video_id}/entities/{entity_id}/manual` creates manual entity-video association; `DELETE /api/v1/videos/{video_id}/entities/{entity_id}/manual` removes it

### Fixed
- `apiFetch` calling `response.json()` on 204 No Content responses — added status check to return `undefined` for bodyless responses (204/205)
- `_TRANSCRIPT_METHODS` missing `"user_correction"` — entity mention counts excluded correction-derived mentions, showing 0 in entity detail view
- `_SOURCE_CATEGORY_MAP` mapping `user_correction` to its own category instead of `"transcript"` — frontend showed separate badge instead of combining with transcript count
- `union_all` in `visible_names` subquery causing JOIN fan-out when canonical name also existed as a `name_variant` alias — changed to `union` to deduplicate, fixing doubled mention counts
- Entity search autocomplete disabling all linked entities — changed to only disable manually-linked entities (`link_sources.includes("manual")`), allowing transcript-linked entities to receive manual associations
- `useDeleteManualAssociation` using `useEffect(isSuccess)` for cleanup — replaced with per-call `onSuccess` callback for reliable state reset

### Technical
- 3 new API endpoints (entity search, create manual association, delete manual association)
- 1 new frontend component (`EntityMentionsPanel`), 2 new hooks (`useEntityMentions`, `useDeleteManualAssociation`), 1 new API client module
- New Alembic migration 050 for `entity_mentions` schema updates (nullable `segment_id`, nullable `language_code` for manual mentions)
- 43 new frontend tests (apiFetch 204 handling, delete API client, optimistic update hook)
- 7,301+ total backend tests, 3,377+ total frontend tests
- Frontend version: 0.19.0 → 0.20.0
- TypeScript strict mode (0 errors), mypy strict compliance (0 errors)
- No new dependencies

## [0.50.0] - 2026-03-21

### Added
- **Feature 049: Settings & Preferences Page**
  - **Language Preferences UI (US1)**: Settings page at `/settings` with full language preference management; preferences grouped by type (Fluent, Learning, Curious, Exclude) with color-coded pills showing display name and code; add preference via searchable language combobox with preference type selector; remove individual preferences; reset all with confirmation `alertdialog`; learning goal input conditionally shown for "learning" type; empty state explaining each preference type's effect on transcript downloading; `DuplicateLanguageError` validation (FR-009); `aria-live` region for preference change announcements; `useLanguagePreferences` hook with PUT replace-all semantics and priority renumbering
  - **Preference-Aware Transcript Download (US2)**: Frontend transcript download now respects configured language preferences; backend `download_transcript()` consults `PreferenceAwareTranscriptFilter` to determine which languages to download (fluent → learning → curious, skipping excluded); `?language` query parameter continues to work as override; error message lists attempted languages when no transcripts available; `model_validate()` conversion from ORM to Pydantic domain models
  - **Cache Status & Management (US3)**: "Cache" section on Settings page showing cached image count and total disk space; "Clear Cache" button with confirmation `alertdialog`; Escape key dismisses dialog; loading skeleton, error state with retry, empty cache state ("No cached images"); `useCacheStatus` hook with purge mutation and query invalidation
  - **Application Info (US4)**: "About" section with backend version, frontend version, database statistics (videos, channels, playlists, transcripts, corrections, canonical tags) in `dl/dt/dd` markup; last sync timestamps for 5 data types with "Never synced" fallback; `useAppInfo` hook with 30s staleTime
  - **Settings API Endpoints**: `GET /api/v1/settings/supported-languages` (all BCP-47 codes with display names, no auth required); `GET /api/v1/settings/cache-status` (image count, disk size); `DELETE /api/v1/settings/cache` (purge all cached images); `GET /api/v1/settings/app-info` (version, DB stats, sync timestamps)
  - **Sidebar Navigation**: Settings entry added below separator alongside Setup; `NavSeparator` component with `kind: "separator"` entry type; content navigation (Videos, Transcripts, Channels, Playlists, Entities, Search) above separator, configuration items (Setup, Settings) below

### Changed
- Sidebar restructured: Setup moved below separator to group with Settings (content above, config below)
- Transcript language display on video cards changed from plain text to indigo pills (`bg-indigo-50 text-indigo-700`) with up to 5 visible and `+N` overflow; "N transcripts" count text removed

### Fixed
- `download_transcript()` type mismatch: SQLAlchemy ORM models passed where Pydantic domain models expected by `PreferenceAwareTranscriptFilter` — added `model_validate()` conversion
- Stale `# type: ignore[return-value]` on `ProblemJSONResponse` in settings router

### Technical
- 4 new backend endpoints, 3 new frontend hooks, 4 new frontend components, 1 new page
- 150 new tests (38 backend + 112 frontend across 7 test files)
- 3,277 total frontend tests, 6,000+ total backend tests
- Frontend version: 0.18.0 → 0.19.0
- TypeScript strict mode (0 errors), mypy strict compliance (0 errors)
- No new dependencies, no database migrations
- GitHub issue #102 created for sync timestamp persistence

## [0.49.0] - 2026-03-20

### Added
- **Feature 048: Video Embed with Transcript Download and Interactive Playback Sync**
  - **Transcript Download (US1)**: `POST /api/v1/videos/{video_id}/transcript/download` endpoint with 11-char video_id regex validation, in-flight download guard per video_id (429), call to TranscriptService, returns transcript metadata; `useTranscriptDownload` TanStack Query mutation hook with 30s AbortController timeout and 3-key cache invalidation on success; "Download Transcript" button on video detail page (visible when no transcript exists, disabled with tooltip when unauthenticated, loading/error/retry states per FR-004)
  - **Embedded YouTube Player (US2)**: `useYouTubePlayer` hook with dynamic IFrame API script injection, 10s script load timeout, rAF-based 250ms getCurrentTime() polling, binary search active segment matching, `youtube-nocookie.com` privacy-enhanced mode; `VideoEmbed` component with pre-render availability check, runtime error fallback to static thumbnail, watch history disclosure note; two-column grid layout on >=1024px (stacked below) with sticky player
  - **Click-to-Seek and Active Segment Highlighting (US3)**: Click transcript segment to seek video and auto-play; active segment highlighting with `border-l-4 border-blue-500 bg-blue-50` and 150ms transition; 4-tier highlight precedence (deep-link yellow > correction amber > active blue > default); auto-scroll with "Follow playback" toggle (default ON); 1000ms debounced aria-live announcements; keyboard-accessible segments (Enter/Space to seek)
  - YouTube IFrame API TypeScript type declarations (`youtube.d.ts`)

### Fixed
- Edit/revert/history buttons on transcript segments triggering unintended video seek — added `e.stopPropagation()` to prevent click bubbling to row-level seekTo handler
- Deep link test asserting non-highlighted segments should not have `tabindex` — updated to expect `tabindex="0"` (added for keyboard-accessible click-to-seek)

### Technical
- 1 new backend endpoint, 3 new frontend hooks, 2 new frontend components, 1 new type declaration file
- 303 new tests (86 backend: 58 unit + 28 integration; 217 frontend across 6 test files)
- 3,156 total frontend tests, 6,000+ total backend tests
- Frontend version: 0.17.0 → 0.18.0
- TypeScript strict mode (0 errors), mypy strict compliance (0 errors)
- No new dependencies, no database migrations
- `waitForContainer` rAF polling to handle delayed container ref attachment in lifted hook pattern

## [0.48.0] - 2026-03-19

### Added
- **Feature 047: Docker Containerization & Data Onboarding UI** (GitHub #97, #98)
  - **Containerized Stack (US1)**: Single `docker compose up` starts PostgreSQL 15 + FastAPI backend serving both API (`/api/v1/*`) and React static build (`/*`) on port 8765; multi-stage Dockerfile (Poetry export → pip install → slim runtime, ~505MB); Alembic migrations auto-run on startup via entrypoint script with `pg_isready` health check; OAuth token persists via `./data/` bind mount; NLP dependencies excluded by default (`--build-arg INCLUDE_NLP=true` to include)
  - **Data Onboarding Page (US2)**: New `/onboarding` route with step-based pipeline wizard; `GET /api/v1/onboarding/status` returns pipeline state (4 steps: Seed Reference Data → Load Data Export → Enrich Metadata → Normalize Tags), record counts, auth status, and export detection; `POST /api/v1/tasks` triggers background operations with in-memory TaskManager (mutual exclusion per operation type); `GET /api/v1/tasks/{task_id}` for polling; step cards show status, metrics, progress bar, and error/retry UI
  - **Returning User Detection (US3)**: `new_data_available` compares takeout directory mtime against most recent video `created_at`; completed steps show green checkmarks with result metrics; pipeline state derived from DB counts (survives container restart)
  - **Multi-Directory Takeout Processing**: Load Data processes all `YouTube and YouTube Music*` directories (dated + undated) in takeout path, capturing full watch history across Google Takeout behavior changes; includes `TakeoutRecoveryService` for deleted/private video metadata recovery
  - **Maximum Enrichment Pipeline**: Enrich Metadata runs 4 sub-steps: `enrich_videos(priority="all", include_deleted=True)`, `enrich_playlists()`, sync liked videos, `enrich_channels()`; non-fatal error handling per sub-step
  - **Migration guide**: `docs/guides/migrating-to-docker.md` for users transitioning from native setup
  - **`enriched_videos` count**: Separate metric tracking videos enriched via YouTube API (`WHERE view_count IS NOT NULL`), distinct from total video count

### Changed
- `OperationType` enum extended with `SEED_REFERENCE`, `LOAD_DATA`, `ENRICH_METADATA`, `NORMALIZE_TAGS`
- `PipelineStepStatus` enum added with `NOT_STARTED`, `AVAILABLE`, `RUNNING`, `COMPLETED`, `BLOCKED`
- `TaskStatus` enum added with `QUEUED`, `RUNNING`, `COMPLETED`, `FAILED`
- `OnboardingCounts` schema includes `enriched_videos` field
- Removed "Sync Transcripts" from pipeline (YouTube IP-blocks bulk transcript download; transcripts fetched per-video from detail page)

### Technical
- New files: `onboarding_service.py`, `task_manager.py`, `onboarding.py` (router + schemas), `tasks.py` (router + schemas), `entrypoint.sh`, `Dockerfile`, `docker-compose.yml`
- SPA routing: FastAPI serves `index.html` for all non-API, non-static routes
- Frontend: TanStack Query polling with 2-second `refetchInterval` during active tasks
- Docker image ~505MB without NLP dependencies
- mypy strict compliance (0 errors across src/ and tests/)

## [0.47.0] - 2026-03-18

### Added
- **Feature 046: Correction Intelligence Frontend**
  - **Batch History Page (US1)**: New `/corrections/batch/history` route with paginated list of past batch operations showing pattern, replacement, correction count, actor, and timestamp; "Revert" button with confirmation dialog calling `DELETE /api/v1/corrections/batch/{batch_id}`; pagination with offset/limit and `has_more` flag; TanStack Query cache invalidation on successful revert; user-friendly error messages for 404 (batch not found) and 409 (already reverted); empty state when no batches exist; `useBatchHistory` hook with infinite scroll (GitHub #92)
  - **Cross-Segment Discovery UI (US2)**: `GET /api/v1/corrections/cross-segment/candidates` endpoint wrapping existing `CrossSegmentDiscovery.discover()` service; "Suggested Cross-Segment Candidates" collapsible panel on `/corrections/batch` page with ranked candidate cards showing both segment texts, proposed correction, source pattern, confidence score, and partial-correction badge; clicking a candidate pre-fills the find-replace form and auto-collapses the panel; loading skeleton, error state, empty state; `useCrossSegmentCandidates` hook (GitHub #91)
  - **Word-Level Diff Analysis Dashboard (US3)**: `GET /api/v1/corrections/diff-analysis` endpoint wrapping existing `DiffAnalysisService`; ASR Error Patterns page at `/corrections/diff-analysis` with sortable table (frequency column), client-side error token filter, server-side entity name filter (debounced 300ms), "Show completed" toggle; entity column linked to entity detail page; "Find & Replace" action navigates to batch corrections page with `\b` word-boundary regex pattern pre-filled and regex mode enabled; completed rows show disabled "Completed" badge; `useDiffAnalysis` hook (GitHub #93)
  - **Phonetic ASR Variant Suggestions (US4)**: `GET /api/v1/entities/{entity_id}/phonetic-matches` endpoint wrapping existing `PhoneticMatcher` service; "Suspected ASR Variants" lazy-loaded collapsible section on entity detail page; results table showing original text, proposed correction, confidence score, evidence type, video title, and segment link; "Register as Alias" button (calls existing alias creation API) and "Find & Replace" button (navigates to batch corrections with regex pattern pre-filled); confidence threshold slider (default 0.5); `usePhoneticMatches` hook (GitHub #94)
  - **Sidebar Navigation Restructure**: Collapsible "Transcripts" nav group in sidebar containing Search, Find & Replace, Batch History, ASR Error Patterns, and Language Preferences; `NavGroup` component with expand/collapse animation and `aria-expanded` accessibility; sidebar icons for new routes (`ChartBarIcon`, `ClockIcon`, `TranscriptsIcon`)

### Fixed
- **Entity Mention Scan False Positives**: `_load_entity_patterns()` now excludes `asr_error` aliases from scan patterns — previously included ASR error alias text (e.g., "Bonazo") in regex patterns, creating 917 false `rule_match` mentions across 24 entities
- **Entity Video List Count Inconsistency**: `get_entity_video_list()` now applies visible-names filter (canonical name + non-ASR-error aliases) so video count and mention count are consistent in the entity detail page header — previously showed impossible stats like "2 mentions, 3 videos"
- **Cross-Segment Stopword False Positives**: Added stopword filtering to `CrossSegmentDiscovery` — common English function word splits like "be out" (from "Rick Beato") no longer generate spurious cross-segment candidates
- **ASR Alias Quality Gates**: `is_valid_asr_alias()` gate in `asr_alias_registry.py` rejects aliases shorter than 4 characters or consisting entirely of common English function words; applied to both full-string and sub-token alias registration; deleted "be out" alias and 51 associated false entity mentions for Rick Beato
- **DiffAnalysis Filter Alignment**: Fixed vertical misalignment between "Filter by error token" and "Filter by entity name" inputs on ASR Error Patterns page

### Technical
- 3 new API endpoints: cross-segment candidates, diff analysis, phonetic matches
- 6 new React pages/components: `BatchHistoryPage`, `DiffAnalysisPage`, `CrossSegmentPanel`, `NavGroup`, phonetic matches section on `EntityDetailPage`
- 5 new TanStack Query hooks: `useBatchHistory`, `useCrossSegmentCandidates`, `useDiffAnalysis`, `usePhoneticMatches`, `useBatchApply` (enhanced)
- 8 new backend tests for ASR alias exclusion and entity video list filtering
- 7 new tests for cross-segment stopword filtering
- 15 new tests for ASR alias quality gates
- Frontend version: 0.15.0 → 0.16.0
- mypy strict compliance (0 errors)
- TypeScript strict mode (0 errors)
- No new dependencies, no new database migrations

## [0.46.0] - 2026-03-15

### Added
- **Feature 045: Correction Intelligence Pipeline**
  - **Batch Correction Provenance (US1)**: Nullable `batch_id` (UUIDv7) column on `transcript_corrections` table with index; `BatchCorrectionService` assigns a single batch ID per find-replace invocation; `batch-revert` CLI subcommand reverts all corrections sharing a batch ID with effective text recalculation and entity mention counter updates; `GET /api/v1/corrections/batches` lists all batch metadata; `DELETE /api/v1/corrections/batch/{batch_id}` reverts a batch via API; corrections export (CSV/JSON) includes `batch_id` column (GitHub #81)
  - **Historical Batch Backfill (US2)**: `scripts/utilities/backfill_batch_ids.py` retroactively assigns `batch_id` values to existing corrections using sliding-window heuristic (same actor, original/corrected text, timestamps within configurable window); supports `--dry-run` and `--window` flags; idempotent — re-running makes no changes; Rich progress bar and summary table output (GitHub #81)
  - **Word-Level Diff Analysis (US3)**: `word_level_diff()` function compares original and corrected text token-by-token via `difflib.SequenceMatcher`; `corrections analyze-diffs` CLI command reports error tokens, canonical forms, frequency, and associated entities across all corrections; minimal-token ASR alias registration alongside full-string aliases when corrections match entities (GitHub #80)
  - **ASR Error Boundary Detection (US4)**: `PhoneticMatcher` service using Double Metaphone and Soundex algorithms to identify single-word corruptions, truncations, and multi-word corruptions with spaces; confidence scoring based on phonetic distance with configurable threshold; corroborating evidence requirements to distinguish ASR errors from legitimate similar-sounding names; `corrections detect-boundaries` CLI command (GitHub #77)
  - **Cross-Segment Candidate Discovery (US5)**: `CrossSegmentDiscovery` service mines recurring correction patterns to find ASR errors split across adjacent transcript segments; generates word-boundary split hypotheses and searches for prefix-at-end/suffix-at-start pairs; confidence-ranked output; `corrections suggest-cross-segment` CLI command with `--min-corrections` threshold (GitHub #78)
  - **Fuzzy Utils Refactor (FR-025)**: Replaced hand-rolled fuzzy matching in `fuzzy.py` with `python-Levenshtein` for performance; existing consumers (canonical tag autocomplete) unaffected

### Changed
- `corrections export` CSV/JSON output now includes `batch_id` column

### Technical
- New Alembic migration: `045_add_batch_id_to_corrections`
- New files: `phonetic_matcher.py`, `cross_segment_discovery.py`, `word_level_diff.py`, `backfill_batch_ids.py`, `batch_corrections_router.py`, `batch_correction_schemas.py`
- New dependencies: `fuzzywuzzy`, `python-Levenshtein`, `jellyfish`, `metaphone`
- 200+ new tests across unit and integration suites
- GitHub issue #91 created for wiring cross-segment discovery into the frontend

## [0.45.0] - 2026-03-14

### Added
- **Feature 044: Data Accuracy & Search Reliability**
  - `entities scan --audit` flag — reports user-correction mentions with unregistered text forms in a Rich table with registration suggestions
  - `_escape_like_pattern()` shared helper for ILIKE wildcard escaping in `transcript_segment_repository.py`
  - NULL byte (`\x00`) rejection in search endpoints with 400 Bad Request response
  - 79 new tests across unit and integration suites

### Fixed
- Special character search (GitHub #84): `_`, `%`, `\` in search queries now match literally instead of acting as SQL ILIKE wildcards
- Phrase matching (GitHub #84): multi-word queries like `[ __ ]` treated as contiguous phrases, not split into independent terms
- Batch find-replace literal mode: same ILIKE escaping applied via `find_by_text_pattern()`
- Entity mention count accuracy (GitHub #89): `mention_count` and `video_count` now exclude mentions matching ASR-error aliases, aligning with visible alias occurrence counts
- `has_mentions` filter now correctly excludes entities with only ASR-error-matched mentions

### Technical
- No new dependencies, no schema changes, no migrations
- Files modified: `search.py`, `transcript_segment_repository.py`, `entity_mention_repository.py`, `entity_mention_scan_service.py`, `entity_commands.py`
- `update_entity_counters()` rewritten with `union_all` JOIN against visible names (canonical + non-ASR-error aliases)

## [0.44.0] - 2026-03-13

### Added
- **Feature 043: Entity-Aware Corrections (ADR-006 Increment C)**
  - Entity autocomplete on batch corrections page (`/corrections/batch`): debounced search against entity names and aliases via `GET /api/v1/entities?search=...&search_aliases=true&exclude_alias_types=asr_error`
  - Selected entity pill/badge with canonical name, entity type badge, dismiss button, and external link to entity detail page (opens in new tab)
  - Mismatch warning (amber, non-blocking) when replacement text does not match the selected entity's canonical name or any registered alias — warns that future scans may not match the text form, suggests adding an alias via the entity detail page
  - Alias-aware mismatch check: `useEntityDetail` hook fetches entity detail (including aliases, `asr_error` filtered by backend) so registered aliases like "AMLO" for "Andrés Manuel López Obrador" correctly suppress the warning
  - Entity summary row in ApplyControls showing linked entity before apply, with compact mismatch indicator
  - Alias display on entity detail page: genuine aliases (not `asr_error`) shown in a dedicated section with color-coded type badges (name_variant, abbreviation, nickname, translated_name, former_name)
  - Alias creation form on entity detail page: text input + alias type dropdown + "Add" button with TanStack Query cache invalidation and 3-second auto-clearing success message
  - `POST /api/v1/entities/{entity_id}/aliases` endpoint: validates entity exists, normalizes alias name, rejects duplicates (409), creates alias with `EntityAliasRepository`; `CreateEntityAliasRequest` schema with `alias_name` (1-500 chars) and `alias_type` (Literal excluding `asr_error`)
  - `fetchEntityDetail()` and `createEntityAlias()` API client functions
  - `useEntityDetail` TanStack Query hook with 5-minute stale time for alias-aware mismatch checking
  - `EntityDetail` and `CreateEntityAliasRequest`/`CreateEntityAliasResponse` TypeScript interfaces
  - GitHub issue #87: `entities scan --audit` flag for detecting drift between `user_correction` mentions and registered aliases

### Fixed
- Transcript segment edit form transparency bug: virtual list items with `position: absolute` caused neighboring rows to paint on top of the edit form; fixed with `zIndex: 10` on active segment row
- False positive mismatch warning for registered aliases (e.g., "AMLO" incorrectly triggering warning despite being a registered abbreviation alias)
- `DuplicateTableError` for `ix_entity_mentions_correction_id`: removed duplicate `Index()` from `__table_args__` (column `index=True` already creates it)
- 3 mypy errors in `test_batch_correction_service.py`: replaced lambda `append() or value` tricks with proper async helpers; removed unused `type: ignore` comment
- 6 test failures after Feature 043 model changes: updated member count, expected keys, and mock attributes for `EntityMention` and entity detail response schema

### Technical
- 29 new backend tests for alias creation endpoint, 33 new frontend tests for AddAliasForm component
- Frontend version: 0.14.0 → 0.15.0
- 2,524 frontend tests passing (0 failures)
- TypeScript strict mode (0 errors)
- mypy strict compliance (0 errors)
- No new dependencies, no new database migrations

## [0.43.1] - 2026-03-12

### Fixed
- **Feature 042: Frontend Polish & Video Detail UX**
  - Channel search now eagerly loads all pages before filtering — previously only searched the first 25 channels, causing "No channels match" on fast typing
  - "Searching all channels..." banner with `aria-live="polite"` while pages load during search
  - Transcript virtualization threshold lowered from 500 to 50 segments — fixes scroll reset at ~25 minute mark when switching from standard to virtualized list mid-scroll
  - Transcript segment search now eagerly loads all pages — previously showed "0 of 0" because search only ran against loaded segments
  - Scroll-to-match moved from TranscriptPanel to TranscriptSegments using `containerRef.scrollTop` calculation — fixes scroll failing silently for off-screen virtualized segments where DOM refs are null
  - Added `prevActiveSegmentIndexRef` guard to prevent scroll yanking back to active match during eager-fetch page loads
  - Suppressed `PaginationStatus` during active channel search to avoid confusing "Showing 25 of 800" while filtering

### Technical
- Eager-fetch pattern: `useEffect` calling `fetchNextPage()` when search is active and `hasNextPage && !isFetchingNextPage` — TanStack Query cascades naturally until all pages load
- Applied to both `ChannelsPage` and `TranscriptSegments` for consistent search-over-paginated-data behavior
- Frontend version: 0.13.0 → 0.14.0
- 2,491 frontend tests passing (0 failures)
- TypeScript strict mode (0 errors)
- No new dependencies, no backend changes

## [0.43.0] - 2026-03-11

### Added
- **Feature 041: Batch Correction UI (ADR-005 Increment 7)**
  - Full-featured web UI for batch find-and-replace transcript corrections at `/corrections/batch`
  - Search & preview: pattern/replacement input with regex, case-insensitive, and cross-segment toggles; language, channel, and video ID filters; up to 100 match cards with before/after highlighting
  - Match cards: video title deep link to exact segment, channel name, timestamp, context segments (always visible), amber boundary connector for cross-segment pairs, "previously corrected" badge
  - Selection: all matches selected by default, individual checkboxes, select all/deselect all, pair-based selection (toggling a cross-segment match auto-toggles its partner)
  - Apply workflow: inline confirmation strip (not modal) with correction type dropdown, optional note, auto-rebuild toggle (default on); controls locked during apply with spinner
  - Result summary: applied/skipped/failed counts with color coding, deep links to failed segments, "Retry N failed" button, affected video count
  - 5 React components: `PatternInput`, `MatchList`, `MatchCard`, `ApplyControls`, `ResultSummary`
  - 3 TanStack Query mutation hooks: `useBatchPreview`, `useBatchApply`, `useBatchRebuild`
  - State machine via `useReducer`: idle → previewing → applying → complete
  - Focus management: first match card focused after preview, result summary focused after apply
  - WCAG 2.1 AA: `role="switch"` toggles, `aria-live` selection announcements, strikethrough+bold diff (not color-only), 44×44px touch targets
  - `BatchCorrectionsIcon` sidebar navigation icon
  - 3 REST API endpoints: `POST /api/v1/corrections/batch/{preview,apply,rebuild-text}` with Pydantic V2 request/response schemas
  - `ACTOR_USER_BATCH` ("user:batch") actor constant for web UI batch corrections audit trail (distinct from CLI's "cli:batch")
- **Correction Type Taxonomy Redesign (Migration 039)**
  - Replaced `asr_error` enum value with domain-specific types: `proper_noun`, `word_boundary`, `other`
  - Full enum: `spelling`, `proper_noun`, `context_correction`, `word_boundary`, `formatting`, `profanity_fix`, `other`, `revert`
  - Alembic migration 039 uses column-swap strategy (safe for PostgreSQL enum limitations)
  - Migration maps existing `asr_error` rows to `other` (safe neutral default for all users)
  - Post-migration reclassification script: `scripts/utilities/reclassify_asr_corrections.py` with `--audit` (preview), `--apply` (auto-classify), and `--batch-id` (manual batch review) modes; uses capitalization heuristic to detect proper noun corrections
  - Updated frontend `CORRECTION_TYPE_DESCRIPTIONS` and `SegmentEditForm` dropdown

### Changed
- `BatchCorrectionService.apply_to_segments()` accepts `corrected_by_user_id` parameter instead of hardcoding actor (enables web vs CLI actor distinction)
- `find_and_replace()` CLI path continues to use `ACTOR_CLI_BATCH` constant

### Fixed
- Web frontend batch corrections incorrectly attributed to "cli:batch" — now correctly uses "user:batch"
- `correction_note` field added to `BatchApplyRequest` schema for user-provided correction notes

### Technical
- 5 new frontend components, 3 hooks, 1 types file, 1 page component
- 7 Pydantic V2 API schemas for batch correction endpoints
- Frontend version: 0.12.0 → 0.13.0
- mypy strict compliance (0 errors)
- TypeScript strict mode (0 errors)
- No new dependencies
- Alembic migration 039 for CorrectionType enum redesign

## [0.42.0] - 2026-03-10

### Added
- **Feature 040: Correction Pattern Matching Robustness (#76, #71)**
  - `--cross-segment` flag on `corrections find-replace` — matches patterns spanning two adjacent transcript segments (e.g., ASR splitting "Claudia Sheinbaum" across segment boundaries as "Claudia Shane" + "Bound")
  - Cross-segment dry-run preview with box-drawing pair markers (`╶─┐`/`╶─┘`) and pair count in summary
  - Cross-segment correction application: replacement placed in segment A, consumed fragment removed from segment B, leading whitespace normalized on segment B
  - Cross-segment partner cascade revert: reverting one segment of a cross-segment pair automatically reverts its partner via `[cross-segment:partner=N]` audit marker
  - Single-segment precedence: patterns matching entirely within one segment are corrected first, excluding those segments from cross-segment pairing
  - Conflict detection: overlapping cross-segment pairs resolved by lower sequence number, later pair skipped with warning
  - Python-to-PostgreSQL regex translation: `\b`→`\y`, `\B`→`\Y` state machine in `translate_python_regex_to_posix()` so users write Python regex syntax and it works consistently in both DB queries and Python-side replacement
  - Unscoped `--cross-segment` warning when no `--video-id`/`--language`/`--channel` filter is provided and segment count exceeds 5,000
  - Empty segment warning after cross-segment corrections that may leave segment B with empty text
  - `--cross-segment` composes with `--regex`, `--case-insensitive`, `--language`, `--video-id`, `--channel` filters
  - `find_segments_in_scope()` repository method for fetching segments with scope filters
  - `SegmentPair` and `CrossSegmentMatch` Pydantic V2 models
  - User guide documentation: `docs/user-guide/corrections.md` covering all correction workflows

### Fixed
- ASR alias hook `UniqueViolationError` crashing batch corrections — duplicate check now uses `alias_name_normalized` (matching the unique constraint) instead of `alias_name`, and INSERT wrapped in savepoint to prevent session poisoning
- `batch_revert` return type annotation updated for 5-element tuples (added `bool` partner cascade flag)

### Changed
- **Refactored** ASR alias registration into shared `asr_alias_registry.py` module — `register_asr_alias()` and `resolve_entity_id_from_text()` replace duplicated logic in `TranscriptCorrectionService` and `BatchCorrectionService` (DRY)

### Technical
- 27 new tests for `asr_alias_registry` shared utility (8 resolve + 19 register)
- Integration tests for cross-segment matching, revert, partner cascade, conflict detection
- CLI unit tests for dry-run display formatting (pair markers, summary counts)
- mypy strict compliance (0 errors)
- No new dependencies, no database migrations

## [0.41.1] - 2026-03-08

### Added
- `entities add-alias` CLI command — add one or more aliases to an existing named entity without recreating it (Feature 039)

## [0.41.0] - 2026-03-08

### Added

#### Feature 038: Entity Mention Detection (ADR-006 Increment B)

Scans transcript segments for mentions of known entities using PostgreSQL word-boundary regex matching. Creates an `entity_mentions` junction table linking entities to the specific segments and videos where they appear. Includes an ASR alias auto-registration hook on `find-replace` that captures actual misspelling forms from regex patterns for expanded mention coverage.

**3 New CLI Commands (`chronovista entities`):**

| Command | Description |
|---------|-------------|
| `entities scan` | Scan transcript segments for entity name/alias mentions with dry-run, batch processing, and progress feedback |
| `entities stats` | Display aggregate entity mention statistics with type breakdown and top entities |
| `entities list` (enhanced) | New `--has-mentions`, `--no-mentions` filters and `--sort mentions` option with "Mentions" column |

**Entity Mention Scanning (`entities scan`):**
- Loads all active entities + aliases, builds escaped regex patterns with `\b` word boundaries
- Scans transcript segments in configurable batches (100–5000, default 500)
- Uses effective text (corrected_text if has_correction=True, otherwise text)
- `--dry-run` previews matches in a Rich table (video_id, segment_id, start_time, entity_name, matched_text, context)
- `--full` deletes existing `rule_match` mentions before rescanning (respects filter scope)
- `--new-entities-only` scans only entities with zero existing mentions
- `--entity-type`, `--video-id` (repeatable), `--language` filters
- ON CONFLICT (entity_id, segment_id, mention_text) DO NOTHING for deduplication
- Updates `named_entities.mention_count` and `video_count` via aggregate queries after scan
- Progress bar with spinner in live mode; summary panel with segments scanned, mentions found, unique entities, unique videos, duration

**Entity Stats (`entities stats`):**
- Overview panel: total mentions, unique entities with mentions, unique videos, coverage %
- Type breakdown table: mentions per entity type
- Top entities table: top N entities by video count (default: 10)
- `--entity-type` and `--top` filters

**ASR Alias Auto-Registration Hook (in `corrections find-replace`):**
- When a `find-replace` correction matches an entity name, the original misspelling form is auto-registered as an `asr_error` alias
- Regex mode extracts each distinct matched form via `re.findall()` and registers separately with per-form occurrence counts
- Captures effective text BEFORE `apply_correction()` mutates the ORM object (prevents timing bug where corrected text no longer matches the pattern)
- Enables the closed-loop pipeline: corrections → rebuild-text → entity scan → expanded mention coverage

**New Source Files (5):**

| File | Description |
|------|-------------|
| `models/entity_mention.py` | `EntityMentionBase`, `EntityMentionCreate`, `EntityMention` Pydantic V2 models |
| `repositories/entity_mention_repository.py` | Repository with bulk insert (ON CONFLICT DO NOTHING), scoped delete, counter updates, video/entity summary queries |
| `services/entity_mention_scan_service.py` | Scanning orchestration with batch processing, pattern construction, incremental/full rescan modes |
| `api/schemas/entity_mentions.py` | API response schemas: `VideoEntitySummary`, `MentionPreview`, `EntityVideoResult`, `EntityVideoResponse` |
| `db/migrations/versions/038_add_entity_mentions_table.py` | Alembic migration: `entity_mentions` table with UUIDv7 PK, FKs, unique + CHECK constraints, 5 indexes |

**New Enum:**

| Enum | Values | Purpose |
|------|--------|---------|
| `DetectionMethod` | `rule_match`, `spacy_ner`, `llm_extraction`, `manual` | Discriminator for how a mention was detected (extensible for future NLP/LLM methods) |

### Known Limitations

#### Bulk Correction Edge Cases

When using `chronovista corrections find-replace`, be aware of the following limitations:

- **Cross-segment matches**: If a misspelling spans two adjacent transcript segments (e.g., "Claudia" at the end of segment #152 and "Shembun" at the start of segment #153), `find-replace` will not match it because each segment is searched independently. You must correct such cases manually via the inline web UI on each segment, or wait for cross-segment pattern matching support (GitHub issue #71).
- **Regex greediness**: Broad regex patterns (e.g., `Sham\w*`) may match unintended text in other contexts. Always use `--dry-run` first to review all matches before applying.
- **Partial word matches in substring mode**: Without `--regex`, the default substring mode uses SQL `LIKE '%pattern%'`, which can match inside larger words. For example, `--pattern "art"` would match "art", "start", "party", etc. Use `--regex` with word boundaries (`\bart\b`) for precise matching.
- **Order of operations matters**: After running `find-replace`, always run `rebuild-text` before `entities scan` to ensure the full transcript text reflects corrections. The scan reads segment-level effective text (not `transcript_text`), but `rebuild-text` keeps the full-text search index and API responses in sync.
- **Idempotency after revert**: If you `batch-revert` a correction and then re-run the same `find-replace`, it will re-apply. This is by design (idempotency applies to consecutive runs, not revert-then-reapply cycles).

### Technical
- 200 new tests (81 model + 54 repository + 46 service + 19 integration)
- mypy strict compliance (0 errors)
- No new dependencies (uses existing SQLAlchemy, Pydantic V2, uuid_utils)
- New Alembic migration for `entity_mentions` table (fully reversible)
- Frontend version: 0.11.0 → 0.12.0

## [0.40.0] - 2026-03-06

### Added

#### Feature 037: Entity Classify Improvements (#69)

Standalone named entity management CLI and improvements to the `classify` command. Adds 3 new `chronovista entities` commands for creating, listing, and backfilling entity descriptions independently of canonical tags. Enhances `classify` with `--description` flag and auto-title-case for entity-producing types. CLI only — no frontend changes, no new API endpoints, no database migrations.

**3 New CLI Commands (`chronovista entities`):**

| Command | Description |
|---------|-------------|
| `entities create <name> --type <type>` | Create a standalone named entity with aliases, description, auto-title-case, and duplicate detection |
| `entities list` | Browse named entities in a Rich table with type, search, and limit filters |
| `entities backfill-descriptions` | Copy classify `--reason` text into entity descriptions for entities with NULL descriptions |

**Entity Create (Issue #69):**
- Takes a canonical name and `--type` (person, organization, place, event, work, technical_term)
- Normalizes the name via `TagNormalizationService.normalize()` for duplicate detection
- Auto-title-cases the canonical name for entity-producing types
- `--description` option for a human-readable entity description
- `--alias` option (repeatable) to add additional name variants as `entity_aliases` rows
- Creates canonical name as an alias (same pattern as `classify`)
- Validates against `_ENTITY_PRODUCING_TYPES` — rejects topic/descriptor (tag-only types)
- Duplicate detection: same normalized name + entity type → error

**Entity List:**
- Rich table with columns: ID (truncated), Name, Type, Description (truncated), Aliases count, Created date
- `--type` filter restricts to a specific entity type
- `--search` / `-q` case-insensitive canonical name search
- `--limit` / `-l` caps results (default: 50)
- Footer shows "Showing N of M total entities"

**Backfill Descriptions:**
- Queries `tag_operation_logs` for classify operations (operation_type='create') with a reason
- Joins against `named_entities` where description IS NULL
- `--dry-run` shows a preview table (Entity ID, Name, Reason) without writing
- Normal mode updates entities and commits

**Classify Improvements (Issues #60, #62):**
- `--description` flag populates `named_entities.description` directly during classification (falls back to `--reason` when `--description` is not provided)
- Auto-title-case: `canonical_form` is automatically title-cased for entity-producing types (person, organization, place, event, work, technical_term); `--no-auto-case` flag opts out
- Auto-title-case prevents future lowercase person entity names caused by YouTube creators never capitalizing a tag

**New Source File (1):**

| File | Description |
|------|-------------|
| `cli/entity_commands.py` | 3 Typer commands registered as `entities` sub-app: create, list, backfill-descriptions |

**Modified Files (3):**
- `cli/main.py` — Registered `entity_app` as `entities` sub-app
- `cli/tag_commands.py` — Added `--description` and `--no-auto-case` flags to `classify` command
- `services/tag_management.py` — Added `description` and `auto_case` parameters to `classify()` method

### Fixed
- 4 lowercase person entity names (Camila Escalante, Dena Takruri, Lara Sheehi, Margaret Kimberley) corrected via one-time `INITCAP()` update across `canonical_tags`, `named_entities`, and `entity_aliases` tables — root cause: no YouTube creator ever title-cased those tags, so canonical form election selected lowercase

### Technical
- 42 new tests: 29 integration (entity CLI), 6 integration (tag management CLI), 7 unit (tag management service)
- mypy strict compliance (0 errors)
- No new dependencies, no database migrations (uses Feature 028a tables)

## [0.39.0] - 2026-03-05

### Added

#### Feature 036: Batch Correction Tools (ADR-005 Increment 6)

CLI batch tools for finding, replacing, reverting, exporting, and analyzing transcript corrections at scale. Enables pattern-based bulk correction of recurring ASR errors across the entire transcript library with transaction safety, dry-run preview, and full audit trail. CLI only — no frontend changes, no new API endpoints, no database migrations.

**6 New CLI Commands (`chronovista corrections`):**

| Command | Description |
|---------|-------------|
| `corrections find-replace --pattern X --replacement Y` | Batch find-and-replace across all transcript segments with dry-run, confirmation prompt, regex/case-insensitive modes, and filter options |
| `corrections rebuild-text` | Regenerate `video_transcripts.transcript_text` from corrected segments (space-separated, matching original assembly) |
| `corrections export --format csv\|json` | Export correction audit records to CSV or JSON with date/video/type filters and stdout support |
| `corrections stats` | Aggregate correction statistics with type breakdown and top corrected videos |
| `corrections patterns` | Discover recurring correction patterns with copy-paste suggested commands |
| `corrections batch-revert --pattern X` | Batch revert corrections matching a pattern with dry-run and confirmation |

**Batch Find-Replace (US-1, US-2, US-8):**
- Database-side pattern matching using SQL `LIKE`/`ILIKE`/`~`/`~*` on effective text (`CASE WHEN has_correction THEN corrected_text ELSE text END`) — no full table load into Python (NFR-2)
- `--regex` flag for Python regular expression patterns; `--case-insensitive` / `-i` for case-insensitive matching
- `--language`, `--channel`, `--video-id` (repeatable) filter options
- `--correction-type` (default: `asr_error`) and `--correction-note` for audit trail metadata
- `--dry-run` preview with Rich table: video_id, segment_id, start_time, current text (context-window truncated to 80 chars with match bold-highlighted), proposed text (end-truncated to 80 chars)
- `--limit` option caps dry-run preview rows (default: 50)
- Confirmation prompt showing pattern, replacement, correction type, active filters, and scope ("This will correct N segments across M videos. Proceed? [y/N]")
- `--yes` / `-y` flag skips confirmation for scripting
- Rich summary table: segments scanned, matches found, corrections applied, skipped (no-op), failed, unique videos
- Rich progress bar updating per transaction batch (NFR-3)

**Transaction Safety (NFR-1):**
- Configurable transaction batches via `--batch-size` (default: 100 segments per commit)
- Per-batch commit/rollback: failed batches are rolled back independently; previously committed batches remain applied
- Summary reports both successful and failed batch counts

**Rebuild Corrected Full Text (US-3):**
- Scans `video_transcripts` where `has_corrections = True`, concatenates segment effective texts ordered by `start_time`, separated by spaces (matching original transcript assembly format)
- `--video-id` and `--language` filter options
- `--dry-run` preview showing video_id, language_code, current text length, and new text length
- Rich progress bar (one tick per transcript rebuilt)
- Skips transcripts with no corrected segments (no unnecessary writes)

**Export Corrections (US-4, US-5):**
- `--format csv` writes CSV with columns: id, video_id, language_code, segment_id, correction_type, original_text, corrected_text, correction_note, corrected_by_user_id, corrected_at, version_number
- `--format json` writes JSON array with 2-space indentation (or `--compact` for no indentation)
- `--output` writes to file; omitted writes to stdout (pipe-friendly)
- `--video-id`, `--correction-type`, `--since`, `--until` (ISO 8601) date filters
- `--since` inclusive (`>=`), `--until` inclusive (`<=`, date-only interpreted as end-of-day)
- Summary line to stderr: "Exported N correction records"

**Correction Statistics (US-6):**
- Rich panel with: total corrections (excluding reverts), total reverts, unique segments, unique videos
- Breakdown by `correction_type` table (type and count columns) with separate "Reverts" row
- Top N most-corrected videos table (video_id, title, correction count) via `--top` option (default: 10)
- `--language` filter option
- Aggregate SQL queries (max 3 round-trips) — no full record load into memory

**Correction Patterns Discovery (US-7):**
- Groups `transcript_corrections` by (original_text, corrected_text) pairs, excluding reverts
- Rich table: original_text, corrected_text, occurrences, remaining_matches (segments still containing the error)
- Sorted by `remaining_matches` descending (highest-impact patterns first)
- Each row includes suggested command: `corrections find-replace --pattern "<original>" --replacement "<corrected>"`
- `--min-occurrences` (default: 2), `--limit` (default: 25), `--show-completed` flag
- Patterns with `remaining_matches = 0` hidden by default

**Batch Revert (US-9):**
- Finds segments whose `corrected_text` matches pattern, reverts each via `TranscriptCorrectionService.revert_correction`
- Same filter and safety options as find-replace: `--video-id`, `--language`, `--regex`, `--case-insensitive`, `--dry-run`, `--yes`, `--batch-size`
- Each revert creates proper audit record with `correction_type = 'revert'`
- Summary: total reverted, total skipped, total errors

**Actor String Convention (FR-030, FR-031):**
- `correction_actors.py` module with constants: `ACTOR_USER_LOCAL` ("user:local"), `ACTOR_CLI_BATCH` ("cli:batch"), `ACTOR_CLI_INTERACTIVE` ("cli:interactive")
- `auto_actor(engine)` helper for engine-based actor selection
- API endpoint defaults `corrected_by_user_id` to `ACTOR_USER_LOCAL` when client omits the field (previously NULL)
- CLI batch commands use `ACTOR_CLI_BATCH` for all audit records

**New Source Files (4):**

| File | Description |
|------|-------------|
| `models/correction_actors.py` | Actor string constants and `auto_actor()` helper |
| `models/batch_correction_models.py` | 6 Pydantic V2 frozen models: BatchCorrectionResult, CorrectionExportRecord, CorrectionPattern, CorrectionStats, TypeCount, VideoCount |
| `services/batch_correction_service.py` | BatchCorrectionService with find_and_replace, rebuild_text, export_corrections, get_statistics, get_patterns, batch_revert, and shared _process_in_batches helper |
| `cli/correction_commands.py` | 6 Typer commands registered as `corrections` sub-app |

**Modified Files (4):**
- `cli/main.py` — Registered `correction_app` as `corrections` sub-app
- `repositories/transcript_segment_repository.py` — Added `find_by_text_pattern()` and `count_filtered()` with database-side pattern matching
- `repositories/transcript_correction_repository.py` — Added `get_all_filtered()`, `get_stats()`, and `get_correction_patterns()` aggregate query methods
- `api/routers/transcript_corrections.py` — Default `corrected_by_user_id` to `ACTOR_USER_LOCAL` when omitted

### Fixed
- `corrected_by_user_id` defaulting to NULL in correction submission API when client omits the field — now defaults to `"user:local"` via `ACTOR_USER_LOCAL` constant
- Pre-existing channel video test failures (`StopAsyncIteration`) caused by Feature 035's corrections batch query adding a 4th `db.execute()` call that existing mock sessions didn't account for — added missing mock result to `_create_channel_videos_mock_session`

### Technical
- 277 new tests: 7 unit (actors), 46 unit (models), 33 unit (segment repo), 47 unit (correction repo), 84 unit (service), 60 unit (CLI), 13 integration (batch workflow + cross-feature contracts), 2 API (actor default)
- 6,026 total tests passing with 0 regressions
- Coverage: 90%+ on all new source files
- mypy strict compliance (0 errors on all new and modified files)
- No new dependencies, no database migrations (uses existing tables from Features 033-035)
- All commands registered on `corrections` Typer sub-app following existing CLI conventions (NFR-6)
- Structured INFO logging at start/completion of every batch operation with duration (NFR-4)
- Idempotency verified: running find-replace twice with same pattern reports "0 corrections applied" on second run (NFR-5)
- Database-side filtering via SQL LIKE/ILIKE/~ operators — no full table load into Python memory (NFR-2)
- Rich progress bars on all batch operations updating per transaction batch (NFR-3)

## [0.38.0] - 2026-03-03

### Added

#### Feature 035: Frontend Inline Correction UI (ADR-005 Increment 5)

Full inline correction workflow in the transcript panel — edit segment text, choose correction type, submit, revert, and view correction history — all without leaving the page. Consumes the REST API from Feature 034. Frontend and backend query changes only — no new API endpoints, no database migrations.

**Segment-Level Correction Badge (US-1):**
- "Corrected" badge (`bg-amber-100 text-amber-800 border-amber-200`) on segments where `has_correction === true`
- Tooltip shows "Corrected {count} times" and formatted `corrected_at` timestamp when `correction_count > 1`
- `aria-label="Corrected segment"` — text label always present (WCAG 1.4.1)
- Badge renders in both StandardSegmentList and VirtualizedSegmentList paths

**Video-Level Correction Indicator (US-2):**
- `has_corrections` field on `TranscriptSummary` interface (backend: EXISTS subquery on `transcript_segments.has_correction`)
- "Corrections" badge on `VideoCard` in transcript info row alongside "Manual CC" / "Auto CC"
- "This transcript has corrections" indicator in `TranscriptPanel` header on `VideoDetailPage`
- Absent `has_corrections` treated as `false` via nullish coalescing

**Inline Edit Mode (US-3, US-4):**
- Edit button visible on hover/focus-within with `aria-label="Edit segment {id}"`
- `<textarea>` pre-filled with effective text; auto-focused on mount (WCAG 2.4.3)
- `<select>` for correction type: spelling, asr_error, context_correction, profanity_fix, formatting (default: asr_error)
- Save and Cancel buttons with 44×44px touch targets (WCAG 2.5.8)
- Client-side validation: empty text ("Correction text cannot be empty.") and no-change ("Correction is identical to the current text.") with `role="alert"` and `aria-invalid="true"`
- Validation on Save click only; errors clear on next keystroke
- Single-edit-at-a-time: entering edit on a second segment cancels the first
- API errors displayed inline with `aria-describedby` linking to textarea

**Revert Workflow (US-5):**
- Revert button appears when `has_correction === true` with `aria-label="Revert correction for segment {id}"`
- Inline confirmation row: "Revert to previous version?" with Confirm/Cancel buttons
- Confirm button auto-focused on mount (WCAG 2.4.3, 3.3.4)
- `aria-busy="true"` on Confirm button during pending mutation; Cancel always enabled
- On 422 `NO_ACTIVE_CORRECTION`, inline `role="alert"` error shown for 4 seconds
- Focus returns to Edit button after successful revert (Revert button may no longer exist)

**Correction History Panel (US-6):**
- History button appears when `correction_count > 0` with `aria-label="View correction history for segment {id}"`
- Inline bordered card below segment row with `role="region"` and `aria-label="Correction history"`
- Each `CorrectionAuditRecord` displays: correction type (title-cased), formatted date, original text, corrected text, version number, and correction note
- "Load more" pagination when `has_more === true`
- Empty state: "No corrections recorded for this segment."
- Loading skeleton with 3 pulsing placeholder rows
- Escape key dismisses panel; focus returns to History button

**Keyboard Accessibility (US-7):**
- Edit, Revert, History buttons reachable via Tab
- Edit mode tab order: textarea → correction type → Save → Cancel
- Escape cancels edit/revert/history with correct focus restoration
- All interactive elements have `focus-visible:ring-2 focus-visible:ring-blue-500`
- `event.stopPropagation()` on edit form keydown prevents parent scroll handler interception

**Screen Reader Announcements (US-8):**
- Dedicated `aria-live="polite" aria-atomic="true" className="sr-only"` region
- Announcements for: edit mode entered, correction saved, edit cancelled, revert confirmation shown, revert completed, history panel opened, API errors
- Error announcements use `aria-live="assertive"`
- All SVG icons carry `aria-hidden="true"`

**TanStack Query Cache Patching (US-9, US-10):**
- `useCorrectSegment` hook: optimistic patch on mutate (text, has_correction, corrected_at, correction_count), rollback on error, authoritative overwrite on success
- `useRevertSegment` hook: server-confirmed state only (no optimistic updates)
- `useSegmentCorrectionHistory` hook: `staleTime: 0`, `enabled: isHistoryOpen`
- Cache patched via `queryClient.setQueryData` on infinite query pages — no `invalidateQueries` on success
- `aria-busy="true"` on segment row during pending mutation

**UI Polish:**
- Segment row `hover:bg-slate-50` for visual identification on wide screens
- Tooltips on action buttons: "Edit segment", "Revert to previous version", "View correction history"

**New Frontend Files (14):**

| File | Description |
|------|-------------|
| `types/corrections.ts` | CorrectionType, CorrectionAuditRecord, CorrectionSubmitResponse, CorrectionRevertResponse, SegmentEditState discriminated union |
| `hooks/useCorrectSegment.ts` | Submit mutation with optimistic updates and rollback |
| `hooks/useRevertSegment.ts` | Revert mutation with server-confirmed state |
| `hooks/useSegmentCorrectionHistory.ts` | Correction history query hook |
| `components/transcript/corrections/CorrectionBadge.tsx` | "Corrected" badge with tooltip |
| `components/transcript/corrections/SegmentEditForm.tsx` | Inline edit form with validation |
| `components/transcript/corrections/RevertConfirmation.tsx` | Inline revert confirmation row |
| `components/transcript/corrections/CorrectionHistoryPanel.tsx` | Correction history panel with pagination |
| `components/transcript/corrections/index.ts` | Barrel export |
| `components/transcript/corrections/__tests__/CorrectionBadge.test.tsx` | Badge tests |
| `components/transcript/corrections/__tests__/SegmentEditForm.test.tsx` | Edit form tests |
| `components/transcript/corrections/__tests__/RevertConfirmation.test.tsx` | Revert confirmation tests |
| `components/transcript/corrections/__tests__/CorrectionHistoryPanel.test.tsx` | History panel tests |
| `components/transcript/__tests__/TranscriptSegments.corrections.test.tsx` | Integration tests |

**Modified Files (8):**
- `types/transcript.ts` — Added `has_correction`, `corrected_at`, `correction_count` to `TranscriptSegment`
- `types/video.ts` — Added `has_corrections` to `TranscriptSummary`
- `hooks/useTranscriptSegments.ts` — Exported `segmentsQueryKey` for cache patching
- `components/transcript/TranscriptSegments.tsx` — EditModeProps, SegmentEditState, aria-live region, single-edit-at-a-time, hover highlight, button tooltips
- `components/transcript/TranscriptPanel.tsx` — "This transcript has corrections" indicator
- `components/video/VideoCard.tsx` — "Corrections" badge in transcript info row
- `src/chronovista/api/schemas/videos.py` — `has_corrections` computed field on `TranscriptSummary`
- `src/chronovista/api/routers/videos.py` — EXISTS subquery for `has_corrections` aggregation

### Technical
- 263 new tests: 252 frontend (CorrectionBadge 23, SegmentEditForm 52, RevertConfirmation 16, CorrectionHistoryPanel 29, TranscriptSegments integration 40, hook tests 92) + 11 backend (TranscriptSummary corrections)
- 2,320 total frontend tests passing (98 files), 5,700+ total backend tests passing
- Coverage: 90%+ on all new components and hooks
- mypy strict compliance (0 errors on all modified backend files)
- TypeScript strict mode (0 errors)
- WCAG 2.1 Level AA compliance: keyboard operability (2.1.1), focus order (2.4.3), focus visible (2.4.7), touch targets (2.5.8), color independence (1.4.1), status messages (4.1.3), error prevention (3.3.4)
- Frontend version: 0.10.0 → 0.11.0
- No new npm dependencies, no new Python dependencies
- No database migrations (uses existing tables from Features 033/034)
- SegmentEditState discriminated union prevents impossible UI states (read | editing | confirming-revert | history)
- Optimistic updates with rollback on submit; server-confirmed state on revert

## [0.37.0] - 2026-03-03

### Added

#### Feature 034: Correction Submission API (ADR-005 Increment 4)

REST API endpoints for submitting, reverting, and viewing transcript corrections with full audit trail. Enriches existing segment responses with correction metadata. Backend only — no frontend changes, no CLI commands, no database migrations.

**3 New API Endpoints (`/api/v1/videos/{video_id}/transcript/segments/{segment_id}/corrections`):**

| Endpoint | Method | Status | Description |
|----------|--------|--------|-------------|
| `.../corrections` | POST | 201 | Submit a correction to a transcript segment |
| `.../corrections/revert` | POST | 200 | Revert the latest correction on a segment |
| `.../corrections` | GET | 200 | Paginated correction history for a segment |

**Submit Correction (US-1):**
- Accepts `corrected_text` (required, min 1 char after whitespace stripping), `correction_type` (required, one of 5 non-revert `CorrectionType` values), `correction_note` (optional), `corrected_by_user_id` (optional)
- `language_code` as required query parameter (matches existing transcript endpoint pattern)
- Field validator rejects `correction_type=revert` (use dedicated revert endpoint instead)
- Delegates to `TranscriptCorrectionService.apply_correction()` from Feature 033
- Returns 201 with audit record (id, version_number, original_text, corrected_text, corrected_at) and segment state (has_correction, effective_text)
- Error codes: `SEGMENT_NOT_FOUND` (422), `NO_CHANGE_DETECTED` (422), `INVALID_CORRECTION_TYPE` (422), `NOT_FOUND` (404 for video)

**Revert Correction (US-2):**
- No request body — always reverts the latest correction
- Delegates to `TranscriptCorrectionService.revert_correction()` from Feature 033
- Returns 200 with revert audit record and restored segment state
- Error codes: `SEGMENT_NOT_FOUND` (422), `NO_ACTIVE_CORRECTION` (422), `NOT_FOUND` (404 for video)

**Correction History (US-3):**
- Paginated via `limit` (default 50, max 100) and `offset` query parameters
- Results ordered by `version_number DESC` (newest first)
- Returns empty list for segments with no corrections (not 404)
- Returns `ApiResponse[list[CorrectionAuditRecord]]` with `PaginationMeta`

**Segment Response Enrichment (US-4):**
- 3 new fields on existing `GET .../transcript/segments` response: `has_correction` (bool), `corrected_at` (datetime | null), `correction_count` (int)
- Derived via single aggregation query on `transcript_corrections` table (no N+1)
- `text` field continues to return effective text (corrected if available, original otherwise)

**Pydantic V2 Schemas (5 models):**
- `CorrectionSubmitRequest` — request body with `str_strip_whitespace=True`, `min_length=1`, revert rejection validator
- `CorrectionAuditRecord` — audit record with `from_attributes=True` for ORM mapping
- `SegmentCorrectionState` — post-mutation segment state (has_correction, effective_text)
- `CorrectionSubmitResponse` — wraps audit record + segment state
- `CorrectionRevertResponse` — type alias for `CorrectionSubmitResponse`

### Technical
- 57 new tests: 33 unit (schemas), 24 integration (API endpoints — 9 submit, 6 revert, 6 history, 3 segment enrichment)
- 5,689 total tests passing with 0 regressions
- Coverage: 100% on correction router, 100% on correction schemas
- mypy strict compliance (0 errors on all new and modified files)
- No new dependencies, no database migrations (uses tables from Feature 033)
- All error responses use RFC 7807 problem details format (Feature 013)
- `pytestmark = pytest.mark.asyncio` in all async test files
- `ASGITransport` + `AsyncClient` for API integration tests (no server required)

## [0.36.0] - 2026-03-02

### Added

#### Feature 033: Transcript Corrections Audit Table (ADR-005 Increment 3)

Append-only audit table and service layer for recording, applying, reverting, and protecting transcript corrections. All mutations use the flush-only transaction pattern — the caller owns the transaction lifecycle. Backend only — no new API endpoints, no frontend changes, no CLI commands.

**Database Migration:**
- New `transcript_corrections` table with columns: id (UUIDv7 PK), video_id, language_code, segment_id (nullable FK), correction_type, original_text, corrected_text, correction_note (nullable), corrected_by_user_id (nullable), corrected_at (server_default now()), version_number
- Composite FK to `video_transcripts(video_id, language_code)` with RESTRICT on delete
- Optional FK to `transcript_segments(id)` with RESTRICT on delete
- CHECK constraint: `version_number >= 1`
- Indexes: `idx_transcript_corrections_lookup (video_id, language_code, corrected_at)` and `idx_transcript_corrections_segment (segment_id, corrected_at)`
- 3 new columns on `video_transcripts`: `has_corrections` (BOOLEAN, default false), `last_corrected_at` (TIMESTAMP), `correction_count` (INTEGER, default 0)
- Fully reversible: downgrade drops table and removes columns

**CorrectionType Enum (6 values):**
- `spelling`, `profanity_fix`, `context_correction`, `formatting`, `asr_error`, `revert`

**TranscriptCorrectionRepository (append-only, FR-018):**
- `update()` and `delete()` raise `NotImplementedError` — immutable audit trail
- `get_by_segment()` — corrections for a segment ordered by `version_number DESC`
- `get_by_video()` — paginated corrections for a transcript with total count
- `count_by_video()` — total corrections for a (video_id, language_code) pair
- `get_latest_version()` — highest version_number with `FOR UPDATE` row lock (NFR-005)
- `get()` and `exists()` by UUID primary key

**TranscriptCorrectionService:**
- `apply_correction()` — atomically creates audit record, updates segment `corrected_text` and `has_correction`, updates transcript metadata (`has_corrections`, `correction_count`, `last_corrected_at`); version chain: `original_text` is the current effective text, not the original raw text (FR-008a); raises `ValueError` for non-existent segment or identical text (no-op prevention)
- `revert_correction()` — reverts to previous state: revert-to-original (V_N==1: clears `corrected_text`, `has_correction=False`, decrements `correction_count`, recomputes `has_corrections` via EXISTS scan) or revert-to-prior (V_N>1: restores to `V_N.original_text`, keeps `has_correction=True`); records revert as new audit entry with `correction_type='revert'`
- All mutations use `session.flush()` only — never calls `session.commit()` or `session.rollback()` (FR-007a)
- Structured INFO logging for all operations (NFR-006)

**Re-Download Protection (US5):**
- Transcript sync checks `has_correction` before overwriting segment text
- Corrected segments: raw `text` column updated, `corrected_text` preserved, warning logged about divergence
- `--force-overwrite` flag bypasses protection and recomputes transcript metadata
- Uncorrected segments update normally

**Pydantic V2 Domain Models:**
- `TranscriptCorrectionBase`, `TranscriptCorrectionCreate`, `TranscriptCorrectionRead`
- `ConfigDict(strict=True, from_attributes=True)` pattern

**Cross-Feature Contract Verification:**
- `display_text` property returns `corrected_text` after `apply_correction` and original `text` after revert-to-original
- Search router ILIKE queries cover `corrected_text` column for corrected segments
- SRT export uses `display_text` for corrected segment output
- Transcripts API inline ternary returns correct effective text
- Transcript metadata columns (`has_corrections`, `correction_count`, `last_corrected_at`) verified in API responses

### Technical
- 139 new tests: 34 unit (models), 44 unit (repository), 31 unit (service), 9 unit (transcript service US5), 21 integration (full DB flows + cross-feature contracts)
- Hypothesis property-based tests for CorrectionType exhaustiveness, text field edge cases, version chain integrity
- 5,632 total tests passing with 0 regressions
- Coverage: 97-100% on all new source files (transcript_correction.py, transcript_correction_repository.py, transcript_correction_service.py, migration)
- mypy strict compliance (0 errors on all new and modified files)
- No new dependencies (uses existing SQLAlchemy, Alembic, Pydantic V2, uuid_utils)
- Test factory: `TranscriptCorrectionFactory` with UUIDv7 PK generation via `uuid.UUID(bytes=uuid7().bytes)`

## [0.35.0] - 2026-02-27

### Added

#### Feature 032: Canonical Tag Frontend Integration (ADR-003 Phase 3 Frontend)

Integrates the canonical tag API (Feature 030) into the React frontend. Replaces raw tag autocomplete, filter pills, and video detail tag display with canonical-tag-aware components showing aggregated video counts, variation counts, and top aliases. Frontend only — no backend changes, no new API endpoints, no database migrations.

**Canonical Tag Autocomplete (`TagAutocomplete`):**
- Two-line dropdown options: canonical_form with video_count right-aligned, "N variations" in smaller text below
- Calls `GET /api/v1/canonical-tags?q={search}&limit=10` via new `useCanonicalTags` hook (replaces `useTags`)
- "Did you mean:" fuzzy suggestions when prefix search returns zero results and query >= 2 characters
- Rate limit 429 handling: "Too many requests. Please wait." with input disabled for `Retry-After` duration
- Selection uses `normalized_form` as filter value, generating `?canonical_tag=<normalized_form>` URL parameters
- Full ARIA combobox pattern preserved with enhanced screen reader announcements ("Mexico, 910 videos, 8 variations")

**Consolidated Filter Pills (`FilterPills`, `VideoFilters`):**
- Single pill per canonical tag with variation count badge (e.g., "Mexico · 8 vars")
- New `canonical_tag` filter type with teal color scheme (`filterColors.canonical_tag`)
- `?canonical_tag=<normalized_form>` URL parameters replace `?tag=<raw_tag>` for all new filter selections
- Canonical tag display names resolved via `useCanonicalTags` hook with TanStack Query caching
- "Active Filters (N)" count reflects canonical tags, not raw aliases
- `handleClearAll` clears `canonical_tag` parameters alongside existing filter types

**Video List Filtering (`useVideos`, `HomePage`):**
- `useVideos` hook sends `canonical_tag=<normalized_form>` parameters to backend (Feature 030 endpoint)
- `canonicalTags` option added to `UseVideosOptions` interface
- TanStack Query cache key includes `canonicalTags` for proper invalidation
- `HomePage` reads `searchParams.getAll('canonical_tag')` and passes to `useVideos`

**Video Detail Tag Grouping (`ClassificationSection`):**
- Raw tags grouped by canonical form using batch `useQueries` resolution against `GET /api/v1/canonical-tags?q={tag}&limit=1`
- Each canonical group shows `canonical_form` badge with teal color scheme
- Top aliases displayed below each badge ("Also: MEXICO, mexico, méxico, #mexico") via `useCanonicalTagDetail` hook
- Alias line hidden when `alias_count=1` or when only alias is the canonical form itself (R7 rule)
- Unresolved/orphaned tags displayed in separate "Unresolved Tags" subsection with slate italic styling
- Skeleton loading placeholders during resolution (up to 10)
- Clicking any canonical tag badge navigates to `/videos?canonical_tag=<normalized_form>`

**New Hooks:**
- `useCanonicalTags(search, options)` — debounced canonical tag search with suggestions support
- `useCanonicalTagDetail(normalizedForm)` — fetch canonical tag detail with top aliases

**New Types (`types/canonical-tags.ts`):**
- `CanonicalTagListItem`, `CanonicalTagSuggestion`, `CanonicalTagListResponse`
- `TagAliasItem`, `CanonicalTagDetailResponse`
- `SelectedCanonicalTag` — display/value pair for selected tags

**Design Tokens (`styles/tokens.ts`):**
- `filterColors.canonical_tag` — teal color scheme (`#F0FDFA` bg, `#134E4A` text, `#99F6E4` border)

### Migration Notes

**URL Parameter Change — Backward Compatible:**
- The frontend now generates `?canonical_tag=<normalized_form>` URLs instead of `?tag=<raw_tag>` for all tag-related navigation and filtering
- **Old bookmarks still work**: URLs with `?tag=Mexico` continue to function — the backend `GET /api/v1/videos?tag=Mexico` endpoint is unchanged, and the frontend reads both `tag` and `canonical_tag` URL parameters
- Legacy `?tag=` pills display without variation count badges, visually distinguishable from canonical tag pills
- The frontend no longer generates `?tag=` URLs; all new tag links use `?canonical_tag=`

**Prerequisites:**
- Feature 028a (Tag Normalization Schema), Feature 029 (Tag Normalization Backfill), and Feature 030 (Canonical Tag API) must be deployed before canonical tag features function
- Without the backfill pipeline (`chronovista tags normalize`), the canonical tag endpoints return empty results and the autocomplete will show no suggestions
- Raw tag filtering via `?tag=` continues to work regardless of whether the backfill has been run

### Technical
- 212 new frontend tests across 6 test files (2,177 total frontend tests, 88 test files)
- Coverage: useCanonicalTags 100%, useCanonicalTagDetail 95%, ClassificationSection 98%, FilterPills 98%, TagAutocomplete 84%, HomePage 100%
- Frontend version: 0.9.0 → 0.10.0
- No new npm dependencies
- No backend changes, no database migrations
- TanStack Query cache config preserved: staleTime 5min, gcTime 10min, retry 3 with exponential backoff
- WCAG 2.1 Level AA compliance maintained (44px touch targets, ARIA combobox, screen reader announcements)

## [0.34.0] - 2026-02-27

### Added

#### Feature 031: Tag Management CLI (ADR-003 Phase 4)

CLI commands for manual curation of the canonical tag system. Enables merging spelling variants the normalization pipeline missed, splitting incorrectly merged tags, renaming display forms, classifying tags as named entities, reviewing diacritic collisions, deprecating junk tags, and undoing any operation. All mutations are logged to `tag_operation_logs` with full `rollback_data` JSONB for undo capability. Backend/CLI only — no frontend changes, no new API endpoints, no database migrations.

**7 New CLI Commands (`chronovista tags`):**

| Command | Description |
|---------|-------------|
| `tags merge <sources...> --into <target>` | Merge one or more canonical tags into a target, reassigning all aliases |
| `tags split <normalized_form> --aliases "raw1,raw2,..."` | Split specific aliases into a new canonical tag |
| `tags rename <normalized_form> --to "New Form"` | Change canonical display form without affecting normalized form |
| `tags classify <normalized_form> --type <entity_type>` | Assign entity type (person, organization, place, event, work, technical_term, topic, descriptor) |
| `tags classify --top N` | Display top N unclassified canonical tags by video count |
| `tags deprecate <normalized_form>` | Soft-delete a canonical tag (excluded from search/browse, data preserved) |
| `tags collisions` | Interactive review of Tier 1 diacritic collision candidates with split/keep/next actions |
| `tags undo <operation_id>` | Reverse any tag management operation using self-contained rollback data |

**Tag Management Service (`TagManagementService`):**
- Orchestrates all 7 operations with atomic transactions (all-or-nothing semantics per NFR-004)
- Self-contained rollback data: each operation stores complete previous state in `tag_operation_logs.rollback_data` JSONB — undo requires no additional table reads
- Type-specific undo handlers: `_undo_merge()`, `_undo_split()`, `_undo_rename()`, `_undo_classify()`, `_undo_deprecate()`
- Lazy count recalculation via `SELECT COUNT` with JOIN after every mutation
- Multi-source merge: `tags merge mejico mexiko --into mexico` in a single atomic operation with one log entry
- Entity classification with upsert semantics (FR-019): handles multiple tag aliases normalizing to the same form (e.g., "Aaron Mate" and "Aaron Maté" → "aaron mate") by accumulating `occurrence_count` instead of failing on unique constraint
- Entity-producing types (person, organization, place, event, work, technical_term) create `named_entities` + `entity_aliases` records; tag-only types (topic, descriptor) set `entity_type` only
- Collision detection compares casefolded forms within canonical tag groups to find false diacritic merges
- All commands support `--reason "text"` flag stored in `tag_operation_logs.reason`

**Result Dataclasses:**
- `MergeResult`, `SplitResult`, `RenameResult`, `ClassifyResult`, `DeprecateResult`, `UndoResult`, `CollisionGroup`
- Rich console output with formatted panels and tables for all operations

**Repository (`TagOperationLogRepository`):**
- `get()`, `exists()`, `get_recent(limit=20)`, `get_by_operation_id()` for audit trail access
- Inherits CRUD from `BaseSQLAlchemyRepository` with UUIDv7 primary keys

**Pydantic V2 Models (`TagOperationLog` family):**
- `TagOperationLogBase`, `TagOperationLogCreate`, `TagOperationLogUpdate`, `TagOperationLog`
- JSONB-stored UUID lists use `list[str]` to prevent Pydantic V2 coercion issues with `json.dumps()`
- Validated `operation_type` constrained to {merge, split, rename, delete, create}

### Fixed
- UUID JSON serialization error in `tag_operation_logs` JSONB columns: changed `source_canonical_ids` and `affected_alias_ids` from `list[uuid.UUID]` to `list[str]` in `TagOperationLogCreate` to prevent Pydantic V2 from coercing strings back to UUID objects that `json.dumps()` cannot serialize
- Entity alias unique constraint violation during `tags classify` when multiple tag aliases normalize to the same form (e.g., "Aaron Mate" and "Aaron Maté"): implemented upsert semantics with `occurrence_count` accumulation for both in-batch duplicates and pre-existing DB records

### Technical
- 181 new tests: 73 unit (service), 35 unit (repository), 73 integration (CLI commands)
- All commands registered on existing `tag_app` Typer group — no new CLI entry points
- Uses existing repositories: `CanonicalTagRepository`, `TagAliasRepository`, `NamedEntityRepository`, `EntityAliasRepository`
- `performed_by` field set to `'cli'` for all CLI-initiated operations
- `video_tags` table never modified (Safety Guarantee #1 from ADR-003)
- 5,493 total tests passing with 0 regressions
- mypy strict compliance (0 errors across 415 source files)
- No new dependencies, no database migrations

## [0.33.0] - 2026-02-23

### Added

#### Feature 030: Canonical Tag API (ADR-003 Phase 3)

Read-only REST API exposing 124,686 canonical tags from the tag normalization system. Provides browse, detail, and video-by-tag endpoints with prefix search, fuzzy suggestions, per-client rate limiting, and integration into the unified video filter system. Backend only — no frontend or CLI changes.

**API Endpoints (`/api/v1/canonical-tags`):**
- `GET /canonical-tags` — Browse all canonical tags sorted by `video_count DESC` with pagination (`limit`, `offset`)
- `GET /canonical-tags?q={prefix}` — Prefix search on `canonical_form` and `normalized_form` via `ILIKE '{q}%'`
- `GET /canonical-tags/{normalized_form}` — Full detail: display form, alias/video counts, top aliases (configurable via `alias_limit`, default 5), timestamps
- `GET /canonical-tags/{normalized_form}/videos` — Paginated videos via 3-table JOIN: `canonical_tags → tag_aliases (canonical_tag_id) → video_tags (raw_form = tag) → videos (video_id)`, ordered by `upload_date DESC`
- `GET /videos?canonical_tag={normalized_form}` — Filter existing video list by canonical tag with AND semantics across multiple values (e.g., `?canonical_tag=python&canonical_tag=tutorial`)

**Fuzzy Suggestions (Levenshtein distance ≤ 2):**
- When `q` parameter is provided and prefix search yields zero results, computes fuzzy suggestions from top 5,000 active canonical tags (by `video_count`)
- Uses `chronovista.utils.fuzzy.find_similar()` with `max_distance=2`, `limit=10`
- Returns structured `CanonicalTagSuggestion` objects with `canonical_form` and `normalized_form`
- Fallback is best-effort: catches all exceptions and returns `null` suggestions on failure

**Rate Limiting (per-client IP, autocomplete only):**
- 50 requests per minute sliding window, applied only when `q` parameter is present
- Client identification via `X-Forwarded-For` header (proxied) or `request.client.host` (direct)
- In-memory `defaultdict(list)` storage with timestamp cleanup per request
- 429 response with `Retry-After` header and `retry_after` body field

**Repository (`CanonicalTagRepository`):**
- `search()` — Prefix ILIKE on `canonical_form`/`normalized_form` with `status` filter, `video_count DESC` sort, pagination, total count
- `get_by_normalized_form()` — Single lookup by unique normalized form with status filter
- `get_top_aliases()` — Top aliases for a canonical tag ordered by `occurrence_count DESC`
- `get_videos_by_normalized_form()` — 3-table JOIN path with `selectinload(channel)`, `selectinload(transcripts)`, `selectinload(category)`, `include_unavailable` toggle, pagination, distinct count
- `build_canonical_tag_video_subqueries()` — Builds per-tag subqueries for AND-intersection filtering; returns `None` on unrecognized tag (short-circuit for FR-012 empty result)

**Pydantic V2 Schemas (6 models):**
- `CanonicalTagListItem` — Summary with `canonical_form`, `normalized_form`, `alias_count`, `video_count`
- `CanonicalTagDetail` — Full detail extending list item with `top_aliases`, `created_at`, `updated_at`
- `TagAliasItem` — Individual alias with `raw_form`, `occurrence_count`
- `CanonicalTagSuggestion` — Fuzzy match result with `canonical_form`, `normalized_form`
- `CanonicalTagListResponse` — Wraps `data`, `pagination`, optional `suggestions`
- `CanonicalTagDetailResponse` — Wraps single `data` item
- All models use `ConfigDict(strict=True, from_attributes=True)`

**Unified Filter Integration:**
- `CANONICAL_TAG` added to `FilterType` enum in `api/schemas/filters.py`
- Max 10 canonical tag values per request, counting toward `MAX_TOTAL_FILTERS=15`
- `build_canonical_tag_video_subqueries()` generates SQL-level AND intersection subqueries
- Unrecognized canonical tags return empty result (FR-012 short-circuit) with WARNING log

**NFR Compliance:**
- NFR-001: List endpoint 0.174s (requirement: < 2s)
- NFR-002: Videos-by-tag endpoint 0.091s (requirement: < 3s)
- NFR-005: WARNING for unrecognized filters, INFO for query timing, DEBUG for fuzzy pool details
- NFR-006: 10-second `asyncio.wait_for()` timeout on video queries with 504 Gateway Timeout response and `Retry-After: 5` header

**Route Registration:**
- Router mounted at `/api/v1/` in `api/main.py` with `tags=["Canonical Tags"]`
- Videos endpoint defined before detail endpoint to prevent `{normalized_form}` capturing `"videos"` path segment

### Fixed
- Missing `selectinload(VideoDB.category)` in `CanonicalTagRepository.get_videos_by_normalized_form()` — caused `MissingGreenlet` error when router accessed `video.category.name` outside async context

### Technical
- 96 new tests: 21 unit (repository), 25 integration (router), 8 integration (filter), 4 regression (backward compatibility SC-005), 7 fuzzy/rate-limit, 24 tag endpoint, 7 additional
- All test IDs generated via `YouTubeIdFactory.create_channel_id()` / `create_video_id()` — zero hand-crafted YouTube IDs
- Quickstart validation passed all 12 checks against live production data (124,686 canonical tags, 141,163 aliases)
- mypy strict compliance (0 errors on all new and modified files)
- No new dependencies (uses existing FastAPI, SQLAlchemy, Pydantic V2, uuid_utils)
- No database migrations (reads existing tables from Feature 028a/029)
- 5,351 total tests passing with 0 regressions

## [0.32.0] - 2026-02-23

### Added

#### Feature 029: Tag Normalization Backfill Pipeline (ADR-003 Phase 2)

Bulk backfill pipeline that processes all 141,163 distinct tags from the `video_tags` table through the 9-step Unicode normalization pipeline (from Phase 1) to populate `canonical_tags` (124,686 rows) and `tag_aliases` (141,163 rows). Includes pre-backfill analysis with collision detection, post-backfill count recalculation, and three new CLI commands.

**Backfill Pipeline (`TagBackfillService`):**
- `_normalize_and_group()` processes all distinct tags through `TagNormalizationService.normalize()`, groups by normalized form, selects canonical forms via `select_canonical_form()`
- SQLAlchemy Core `INSERT ... ON CONFLICT DO NOTHING` for bulk inserts (first use in codebase — justified by 140K+ rows)
- Pre-generated UUIDv7 primary keys via `uuid_utils.uuid7()` for batch efficiency
- Two-pass `video_count` computation: insert `canonical_tags` with `video_count=0`, then single SQL `UPDATE ... FROM (subquery JOIN tag_aliases JOIN video_tags)`
- Per-batch transaction commits (1,000 records/batch) — interruption loses at most one batch
- Idempotent re-run: `ON CONFLICT DO NOTHING` on UNIQUE constraints; safe to re-execute after partial completion

**Analysis & Collision Detection:**
- `run_analysis()` provides read-only pre-backfill preview with top canonical tags, collision candidates, and skip list
- Collision detection compares casefolded-only forms within normalized groups; flags merges where forms differ by Tier 1 diacritics (e.g., México/Mexico → mexico)
- `KNOWN_FALSE_MERGE_PATTERNS` (`frozenset[str]`, 5 entries: café, résumé, cliché, naïve, rapé) — display-only labels in analysis output, not stored in DB, does not prevent merges
- Table and JSON output formats (`--format table|json`)

**Count Recalculation:**
- `run_recount()` recalculates `alias_count` and `video_count` on all canonical tags from source-of-truth tables
- `--dry-run` mode previews count deltas without writing

**CLI Commands (`chronovista tags`):**
- `tags normalize` — Run backfill with `--batch-size` option (default 1,000) and Rich progress bar
- `tags analyze` — Pre-backfill analysis with `--format` (table/json) and `--dry-run` (no-op, always read-only)
- `tags recount` — Recalculate counts with `--dry-run` for preview

**Repository Enhancement:**
- `get_distinct_tags_with_counts()` on `VideoTagRepository` — `SELECT tag, COUNT(*) FROM video_tags GROUP BY tag`

### Fixed
- Tag normalization idempotency bug: `normalize("##")` produced `"#"` but `normalize("#")` produced `None`; changed single leading `#` strip (`text[1:]`) to `text.lstrip("#")` to strip all leading hash characters

### Technical
- 145 new tests: 37 unit (service), 12 integration (full pipeline against DB), 17 CLI (command interface), 79 existing tests updated
- Hypothesis property-based tests for normalization idempotency (500 examples)
- 5,255 total tests passing with 0 regressions
- mypy strict compliance (0 errors on all new and modified files)
- No new dependencies (uses existing SQLAlchemy Core, uuid_utils, Rich, Typer)

## [0.31.0] - 2026-02-22

### Added

#### Feature 028a: Tag Normalization Schema & Core Service (ADR-003 Phase 1)

Foundational storage layer and normalization algorithm for tag grouping. Creates the schema, enums, normalization service, and all supporting infrastructure. Tables are empty after this phase — no data moves until Phase 2 (028b backfill).

**Database Migration:**
- 5 new tables created in FK dependency order: `named_entities`, `entity_aliases`, `canonical_tags`, `tag_aliases`, `tag_operation_logs`
- 15 indexes including partial indexes for soft-delete optimization
- All CHECK constraints, UNIQUE constraints, and cascade rules per ADR-003
- UUIDv7 primary keys generated application-side via `uuid_utils.uuid7` (PG 15 lacks native support)

**Normalization Pipeline (`TagNormalizationService`):**
- 9-step `normalize()` pipeline: strip whitespace, strip single leading `#`, replace NBSP/tabs, collapse spaces, strip zero-width chars, NFKD decompose, strip Tier 1 marks, NFC recompose, casefold
- `selective_strip_diacritics()` standalone utility — strips only 8 universally safe combining marks (Tier 1) while preserving structurally distinct marks (tilde, cedilla, ogonek, horn, etc.)
- `select_canonical_form()` — title case preference via `str.istitle()`, frequency tiebreaker, alphabetical `min()` deterministic tiebreaker

**Enums (6 new `str, Enum` types):**
- `EntityType` (8 values), `EntityAliasType` (6), `TagStatus` (3), `CreationMethod` (4), `DiscoveryMethod` (5), `TagOperationType` (5)

**Pydantic Models:**
- Base/Create/Update/Full hierarchy for `CanonicalTag`, `TagAlias`, `NamedEntity`, `EntityAlias`
- State invariant validators: merged status requires `merged_into_id` (FR-027), no self-merge (FR-028)

**Repositories:**
- `CanonicalTagRepository`, `TagAliasRepository`, `NamedEntityRepository`, `EntityAliasRepository`
- Inherit from `BaseSQLAlchemyRepository` with ORM model aliasing to avoid Pydantic naming conflicts

### Technical
- 189 new tests (186 passed, 3 skipped for index verification): 71 normalization service tests, 28 schema integration tests, 66 Pydantic model validation tests, 24 repository unit tests
- Hypothesis property-based tests (500 examples each) for idempotency and Tier 1 absence invariants
- 98% test coverage across all new modules
- 5,183 total tests passing with 0 regressions
- mypy strict compliance (0 errors on all 9 new source files)
- New dependency: `uuid_utils` v0.14.1

## [0.30.0] - 2026-02-19

### Added

#### Feature 027: Unified Filter & Sort System

Consistent sorting and filtering controls across all 5 list pages with shared reusable components, replacing ad-hoc implementations.

**Backend:**
- Shared `SortOrder` enum extracted to `api/schemas/sorting.py` for reuse across all routers
- `sort_by`, `sort_order`, `liked_only` params on `GET /videos`
- `sort_by`, `sort_order`, `liked_only`, `has_transcript`, `unavailable_only` params on `GET /playlists/{id}/videos`
- `sort_by`, `sort_order`, `is_subscribed` params on `GET /channels`; `is_subscribed` added to `ChannelListItem` schema
- `sort_by`, `sort_order`, `liked_only` params on `GET /channels/{id}/videos`
- Deterministic secondary sort by primary key on all 5 sorted endpoints for pagination consistency

**Frontend:**
- `SortDropdown<TField>` generic typed component (native `<select>`, WCAG 2.5.8 compliant)
- `FilterToggle` component (native checkbox with URL param sync, 44×44px hit area)
- `useUrlParam` and `useUrlParamBoolean` hooks for URL state management with snake_case param keys
- `FilterPills` extended with boolean pill support (Liked, Has transcripts)
- Channels page subscription filter tabs (All/Subscribed/Not Subscribed)
- ARIA live region announcements (`role="status"`, `aria-live="polite"`) on all 5 pages
- Scroll-to-top and pagination reset on filter/sort changes
- Focus management — triggering control retains focus after state changes

### Removed
- `PlaylistSortDropdown.tsx` replaced by generic `SortDropdown`

## [0.29.0] - 2026-02-19

### Added

#### Feature 026: Local Image Cache Proxy

Backend image proxy that locally caches YouTube channel avatars and video thumbnails to eliminate 429 rate-limit errors from YouTube CDN. Includes CLI commands for cache management and frontend integration replacing all direct YouTube CDN image URLs.

**Image Cache Service:**
- `ImageCacheService` with async fetch, cache, and serve logic
- Filesystem-based storage under `cache/images/channels/` and `cache/images/videos/{prefix}/`
- Two-character prefix sharding for video thumbnails (e.g., `dQ/dQw4w9WgXcQ_mqdefault.jpg`)
- Atomic writes via temp file + rename to prevent serving partial downloads
- Zero-byte `.missing` marker files for 404/410 caching (transient errors serve placeholder without marker)
- Magic-byte content type detection (JPEG, PNG, WebP) decoupled from `.jpg` file extension
- `asyncio.Semaphore(5)` for concurrent YouTube fetch limiting
- Dual timeouts: 2.0s (on-demand proxy), 10.0s (CLI warming)
- Lightweight validation: reject < 1 KB or non-image Content-Type; 5 MB max download size
- SVG placeholder fallbacks (240x240 silhouette for channels, 320x180 play icon for videos)
- `ImageQuality` enum: `default` (120x90), `mqdefault` (320x180), `hqdefault` (480x360), `sddefault` (640x480), `maxresdefault` (1280x720)

**Image Proxy API Endpoints:**
- `GET /api/v1/images/channels/{channel_id}` — Serve cached channel avatar
- `GET /api/v1/images/videos/{video_id}?quality=mqdefault` — Serve cached video thumbnail
- `X-Cache` response header: `HIT`, `MISS`, or `PLACEHOLDER`
- Cache-Control: `public, max-age=604800, immutable` (7d) for cached images; `public, max-age=3600` (1h) for placeholders
- Public endpoints (no auth) — `<img>` tags cannot send auth headers
- Input validation via existing `ChannelId`/`VideoId` types

**CLI Commands (`chronovista cache`):**
- `cache warm` — Pre-warm cache with Rich Progress, `--type`, `--quality`, `--limit`, `--delay`, `--dry-run`
- `cache status` — Rich table with cache counts, sizes, and dates
- `cache purge` — Selective purge with `--type`, `--force`, unavailable content warning
- Exit codes: 0 (success), 1 (partial/errors), 2 (invalid args), 130 (interrupted)

**Enrichment Invalidation Hook:**
- Lazy singleton `ImageCacheService` in enrichment service
- Automatic cache invalidation when channel `thumbnail_url` changes during enrichment
- NULL-safe: only invalidates on non-NULL → different non-NULL URL change

**Frontend:**
- All YouTube CDN image URLs replaced with backend proxy URLs via `API_BASE_URL`
- `ChannelCard.tsx`: Channel avatar via `/images/channels/{channel_id}`
- `ChannelDetailPage.tsx`: Channel avatar via proxy
- `VideoCard.tsx`: Video thumbnail via `/images/videos/{video_id}?quality=mqdefault` (16:9, lazy-loaded)
- `VideoDetailPage.tsx`: Video thumbnail via `/images/videos/{video_id}?quality=sddefault` (640x480, eager-loaded)
- `PlaylistVideoCard.tsx`: Video thumbnail via `/images/videos/{video_id}?quality=mqdefault`
- Client-side SVG placeholder fallback on `onError` (defense in depth)

### Fixed
- Wayback page parser failing to extract `channel_id` from pre-2020 YouTube archive pages that use `data-channel-external-id` attributes or `<a>` anchor tags instead of structured data meta tags. Added two fallback extraction strategies:
  1. `data-channel-external-id` attribute on subscribe buttons
  2. `/channel/UCxxx` URLs in `<a>` anchor tags (including Wayback-prefixed URLs)

### Technical
- 108 new backend tests (45 service + 22 router + 31 CLI + 10 integration)
- 94 new frontend tests across 4 component test files
- 96 page parser tests (4 new for channel_id fallback extraction)
- Zero new third-party dependencies
- mypy strict compliance (0 errors)
- TypeScript strict mode (0 errors)

## [0.28.0] - 2026-02-18

### Added

#### Feature 025: Recovery API & Channel Archive Recovery

Expose video and channel recovery via REST API endpoints, add channel metadata recovery from the Wayback Machine, and provide a full frontend recovery UX with progress tracking, cancellation, and navigation guards.

**Recovery API Endpoints:**
- `POST /api/v1/videos/{video_id}/recover` with `start_year`/`end_year` query params and structured `VideoRecoveryResponse`
- `POST /api/v1/channels/{channel_id}/recover` with `ChannelRecoveryResponse`
- `recovered_at` and `recovery_source` fields added to video and channel detail responses
- Idempotency guard: skips Wayback Machine if entity was recovered within last 5 minutes
- Recovery dependency injection via `get_recovery_deps()` with shared rate limiter (40 req/s)

**Channel Recovery:**
- `extract_channel_metadata()` page parser method with JSON extraction from `ytInitialData` and HTML meta tag fallback
- `recover_channel()` orchestrator with two-tier overwrite policy (all fields mutable, NULL protection)
- CDX client `fetch_channel_snapshots()` with separate cache namespace
- Auto-channel recovery during video recovery when recovered `channel_id` references an unavailable channel

**Page Parser Enhancements:**
- Truncated description replacement: `#eow-description` HTML now overrides short JSON `shortDescription` ending in "..."
- Like count extraction restructured with 5-pattern system ordered by specificity:
  1. Button content span (`yt-uix-button-content`)
  2. Locale-agnostic number from like button `aria-label`
  3. Modern `yt-formatted-string` with "N likes"
  4. "along with N other people" English pattern
  5. Broad `aria-label` scan (last resort)
- International locale support for like counts (German `2.510` → 2510, etc.)

**Frontend:**
- "Recover from Web Archive" button on video and channel detail pages
- "Re-recover from Web Archive" label when previously recovered
- Year filter UI with collapsible "Advanced Options" section and validation
- Zustand v5 recovery store with `persist` middleware for session-level state
- Elapsed time counter during recovery ("Recovering... 1m 23s elapsed")
- Cancel button with `AbortController` integration
- `beforeunload` warning during active recovery
- AppShell recovery indicator banner with entity link and elapsed time
- Toast notifications for recovery completion (green) and failure (red) with 8s auto-dismiss
- localStorage hydration with backend polling for orphaned sessions
- SPA navigation guard (`useBlocker` modal) on video and channel detail pages
- Transcript panel conditionally rendered based on transcript availability
- React Router v7 `startTransition` future flag opt-in

**CLI:**
- Channel recovery statistics in batch summary for `chronovista recover`

### Fixed
- Recovery timeout mismatch: frontend `apiFetch` now accepts per-call timeout override (660s for recovery vs 10s default)
- `sessions.get is not a function` error on localStorage hydration (added `merge` callback for Map deserialization)
- 404 errors for `/transcript/languages` on deleted videos (gated on `transcript_summary.count > 0`)
- Transcript languages endpoint now passes `include_unavailable=true` for deleted video support
- Truncated descriptions from Wayback JSON no longer prevent full `#eow-description` recovery
- Like count extraction failing on non-English locale pages (German, etc.)

### Technical
- 1,739 passing frontend tests across 71 files
- 4,500+ passing backend tests
- 246 recovery-specific backend tests
- Zustand v5 (~3KB gzipped) for app-level recovery state
- mypy strict compliance (0 errors)
- TypeScript strict mode (0 errors)

## [0.27.0] - 2026-02-15

### Added

#### Feature 024: Wayback Video Recovery

Recover metadata for deleted/unavailable YouTube videos using the Internet Archive's Wayback Machine. Coordinates CDX API queries, archived page parsing, and database updates to restore titles, descriptions, tags, channels, and other metadata from archived snapshots.

**CDX API Client:**
- Async CDX API client with file-based caching (24h TTL) and retry logic
- Exponential backoff for HTTP 503 and connection errors (ConnectTimeout, ReadTimeout, ConnectError)
- Fixed 60s pause for HTTP 429 rate limit responses
- `--start-year` / `--end-year` flags for temporal anchor filtering
- Positive CDX limit (oldest-first) when `--start-year` is specified for efficient anchor-based search
- Separate cache keys per year filter configuration

**Page Parser:**
- Extract metadata from archived YouTube pages via `ytInitialPlayerResponse` and `ytInitialData` JSON
- Brace-counting JSON extraction for nested objects (replaces fragile regex)
- HTML meta tag fallback via BeautifulSoup for pages without embedded JSON
- Retry with exponential backoff (2s, 5s, 10s) for transient Wayback Machine connection failures
- Removal notice detection to skip unavailable-content archive pages

**Recovery Orchestrator:**
- Three-tier overwrite policy: immutable fields (channel_id, category_id) fill-if-NULL only; mutable fields overwrite when snapshot is newer; NULL protection never blanks existing values
- Stub channel creation for recovered channel_ids not present in the database (FK constraint protection)
- Channel recovery candidate identification for unavailable channels
- Snapshot iteration with configurable limit (max 20) and 600s timeout
- Dry-run mode for preview without database changes

**CLI Command (`chronovista recover video`):**
- `--video-id` for single-video recovery with progress spinner
- `--all` for batch recovery with configurable `--limit` and `--delay`
- `--dry-run` for preview mode
- `--start-year` / `--end-year` for temporal anchor filtering
- Rich table output for single results and batch summary reports
- Dependency checks for beautifulsoup4 (required) and selenium (optional)

**Frontend:**
- Recovered video titles displayed instead of generic "Unavailable Video" text
- Dimming and strikethrough only applied when no recovered data exists
- Unavailable videos visible by default in video list, channel, and playlist views
- `include_unavailable` parameter added to channel and playlist video hooks

### Fixed
- Foreign key violation when recovered `channel_id` references a channel not in the database
- Page parser regex now matches bare `ytInitialPlayerResponse = {...}` without `var` prefix
- CDX client retries on connection-level errors (ConnectTimeout, ReadTimeout, ConnectError)

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
