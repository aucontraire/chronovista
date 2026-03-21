# Changelog

All notable changes to chronovista will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- MkDocs documentation setup with Material theme
- Comprehensive user guide and API reference

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
  - New `--audit` flag on `entities scan` command: reports user-correction mentions with unregistered text forms (text not matching any alias or canonical name); Rich table output showing Entity, Mention Text, Segment Count, and suggested CLI command to register the alias; read-only operation, mutually exclusive with `--full`, compatible with `--dry-run` (GitHub #87)

### Fixed
- **Special Character Search Fix (GitHub #84)**
  - ILIKE wildcard escaping: `_`, `%`, and `\` in search queries now match literally instead of acting as SQL wildcards
  - Phrase matching: multi-word queries like `[ __ ]` are treated as contiguous phrases, not split into independent terms
  - Same escaping fix applied to batch find-replace literal mode (`find_by_text_pattern()`)
  - NULL byte (`\x00`) rejection in search queries to prevent PostgreSQL silent truncation
  - Shared `_escape_like_pattern()` helper in `transcript_segment_repository.py`
- **Entity Mention Count Accuracy (GitHub #89)**
  - `update_entity_counters()` now filters by visible names only (canonical name + non-ASR-error aliases via `union_all` JOIN)
  - `mention_count` and `video_count` on `named_entities` exclude mentions matching ASR-error aliases
  - Entities with only ASR-error-matched mentions correctly show `mention_count=0`
  - `has_mentions` filter aligned with visible alias data (intentional behavior change)
  - Consistent counting across all paths: scan, batch apply, batch revert

### Technical
- Files modified: `search.py`, `transcript_segment_repository.py`, `entity_mention_repository.py`, `entity_mention_scan_service.py`, `entity_commands.py`
- No new dependencies, no schema changes, no migrations
- 79 new tests added

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
- `entities add-alias` CLI command — add one or more aliases to an existing named entity without recreating it

## [0.41.0] - 2026-03-08

### Added
- **Feature 038: Entity Mention Detection (ADR-006 Increment B)**
  - `chronovista entities scan` — scan transcript segments for entity name/alias mentions using word-boundary regex matching, with `--dry-run` preview, `--full` rescan, `--new-entities-only`, `--entity-type`/`--video-id`/`--language` filters, configurable `--batch-size` (100–5000), Rich progress bar and summary panel
  - `chronovista entities stats` — aggregate entity mention statistics with overview panel, type breakdown table, and top entities by video count (`--entity-type`, `--top` filters)
  - Enhanced `chronovista entities list` with `--has-mentions`, `--no-mentions` filter flags, `--sort mentions` option, and "Mentions" column
  - New `entity_mentions` table (Alembic migration 038) with UUIDv7 PKs, FKs to `named_entities` and `transcript_segments`, unique constraint on (entity_id, segment_id, mention_text), 5 performance indexes
  - `DetectionMethod` enum (rule_match, spacy_ner, llm_extraction, manual) for extensible mention detection
  - `EntityMentionRepository` with bulk insert (ON CONFLICT DO NOTHING), scoped delete, counter updates, video/entity summary queries
  - `EntityMentionScanService` with batch processing, pattern construction, incremental/full rescan modes, progress callbacks
  - ASR alias auto-registration hook in `corrections find-replace`: captures actual matched misspelling forms from regex patterns and registers each as a separate `asr_error` entity alias with occurrence counts
  - Correction-to-alias-to-mention closed-loop pipeline: `find-replace` → `rebuild-text` → `entities scan` → expanded mention coverage
  - API response schemas: `VideoEntitySummary`, `MentionPreview`, `EntityVideoResult`, `EntityVideoResponse`, `VideoEntitiesResponse`

### Known Limitations
- **Cross-segment matches**: `find-replace` cannot match patterns that span two adjacent transcript segments (e.g., a name split across segment boundaries). Correct these manually via the web UI or await cross-segment support (issue #71)
- **Regex greediness**: Broad regex patterns may match unintended text — always use `--dry-run` first
- **Substring mode partial matches**: Default substring mode (`LIKE '%pattern%'`) matches inside larger words; use `--regex` with `\b` word boundaries for precision
- **Order of operations**: After `find-replace`, run `rebuild-text` before `entities scan` to keep full-text search and API responses in sync

### Technical
- 200 new tests (81 model + 54 repository + 46 service + 19 integration)
- mypy strict compliance (0 errors)
- No new dependencies, new Alembic migration for `entity_mentions` table
- Frontend version: 0.11.0 → 0.12.0

## [0.40.0] - 2026-03-06

### Added
- **Feature 037: Entity Classify Improvements (#69)**
  - New `chronovista entities` sub-app with 3 CLI commands for standalone named entity management
  - `entities create <name> --type <type>` — create a standalone named entity (not linked to a canonical tag) with auto-title-case, name normalization, duplicate detection, `--description`, and `--alias` (repeatable) for additional name variants
  - `entities list` — browse named entities in a Rich table with `--type`, `--search`, `--limit` filters showing ID, name, type, description, alias count, and created date
  - `entities backfill-descriptions` — copy `classify --reason` text from `tag_operation_logs` into `named_entities.description` for entities with NULL descriptions, with `--dry-run` preview
  - `classify --description` flag to directly populate `named_entities.description` during entity classification (falls back to `--reason` when not provided)
  - Auto-title-case for `canonical_form` on entity-producing types during `classify` (person, organization, place, event, work, technical_term); `--no-auto-case` flag to opt out

### Fixed
- 4 lowercase person entity names (Camila Escalante, Dena Takruri, Lara Sheehi, Margaret Kimberley) corrected via one-time INITCAP update across `canonical_tags`, `named_entities`, and `entity_aliases` tables

### Technical
- 42 new tests (29 entity CLI + 6 tag management CLI + 7 tag management service)
- mypy strict compliance (0 errors)
- No new dependencies, no database migrations (uses Feature 028a tables)

## [0.39.0] - 2026-03-05

### Added
- **Feature 036: Batch Correction Tools (ADR-005 Increment 6)**
  - 6 new CLI commands under `chronovista corrections` sub-app for batch transcript correction operations
  - `corrections find-replace --pattern X --replacement Y` — batch find-and-replace across all transcript segments with database-side pattern matching (SQL LIKE/ILIKE/~ operators), `--regex`, `--case-insensitive`, `--language`/`--channel`/`--video-id` filters, `--dry-run` preview with Rich table (context-window truncated, match bold-highlighted), confirmation prompt showing scope, `--yes` for scripting, Rich progress bar and summary table
  - `corrections rebuild-text` — regenerate `video_transcripts.transcript_text` from corrected segments (space-separated, matching original assembly), `--dry-run` preview showing current vs new text length, Rich progress bar
  - `corrections export --format csv|json` — export correction audit records with `--video-id`, `--correction-type`, `--since`/`--until` (ISO 8601) filters, `--output` file or stdout (pipe-friendly), `--compact` for JSON, summary to stderr
  - `corrections stats` — aggregate correction statistics: totals (excluding reverts), type breakdown table, top N most-corrected videos with titles, `--language` filter, `--top` option (default: 10), max 3 SQL round-trips
  - `corrections patterns` — discover recurring correction patterns grouped by (original, corrected) pairs with remaining match counts, copy-paste suggested commands, `--min-occurrences`, `--limit`, `--show-completed`
  - `corrections batch-revert --pattern X` — batch revert corrections matching a pattern via `TranscriptCorrectionService.revert_correction`, `--dry-run`, `--yes`, same filter options as find-replace
  - Configurable transaction batching (default: 100 segments per commit) with per-batch rollback — failed batches don't affect previously committed batches (NFR-1)
  - Actor string constants module: `ACTOR_USER_LOCAL` ("user:local"), `ACTOR_CLI_BATCH` ("cli:batch"), `ACTOR_CLI_INTERACTIVE` ("cli:interactive") with `auto_actor()` helper
  - 6 Pydantic V2 frozen models: `BatchCorrectionResult`, `CorrectionExportRecord`, `CorrectionPattern`, `CorrectionStats`, `TypeCount`, `VideoCount`
  - 3 new repository query methods on `TranscriptSegmentRepository`: `find_by_text_pattern()`, `count_filtered()`
  - 3 new repository query methods on `TranscriptCorrectionRepository`: `get_all_filtered()`, `get_stats()`, `get_correction_patterns()`
  - API endpoint now defaults `corrected_by_user_id` to `"user:local"` when client omits the field

### Fixed
- `corrected_by_user_id` defaulting to NULL in correction submission API — now defaults to `ACTOR_USER_LOCAL`
- Pre-existing channel video test failures from Feature 035's corrections batch query missing mock result

### Technical
- 277 new tests (7 actor + 46 model + 33 segment repo + 47 correction repo + 84 service + 60 CLI + 13 integration + 2 API)
- 6,026 total tests passing with 0 regressions
- mypy strict compliance (0 errors)
- No new dependencies, no database migrations (uses Features 033-035 tables)
- Structured INFO logging on all batch operations with duration (NFR-4)
- Idempotency verified: second find-replace run reports "0 corrections applied" (NFR-5)
- Database-side filtering — no full table load into Python (NFR-2)
- Rich progress bars on all batch operations (NFR-3)
- Architecture documentation

## [0.38.0] - 2026-03-03

### Added
- **Feature 035: Frontend Inline Correction UI (ADR-005 Increment 5)**
  - Full inline correction workflow in the transcript panel: edit, submit, revert, and view correction history without leaving the page
  - "Corrected" badge (`bg-amber-100 text-amber-800`) on segments with active corrections; tooltip shows correction count and timestamp
  - Video-level "Corrections" badge on `VideoCard` and "This transcript has corrections" indicator on `VideoDetailPage`
  - `has_corrections` computed field on backend `TranscriptSummary` via EXISTS subquery
  - Inline edit mode: `<textarea>` with correction type `<select>` (spelling, asr_error, context_correction, profanity_fix, formatting), Save/Cancel with 44×44px touch targets
  - Client-side validation: empty text and no-change detection with `role="alert"` and `aria-invalid="true"`; errors clear on next keystroke
  - Single-edit-at-a-time enforcement: entering edit on a second segment cancels the first
  - Revert workflow: inline "Revert to previous version?" confirmation with auto-focused Confirm button, `aria-busy` during pending mutation
  - Correction history panel: inline bordered card with audit records (type, date, original text, corrected text, version, note), "Load more" pagination, loading skeleton, Escape to dismiss
  - `useCorrectSegment` hook with optimistic updates (immediate text patch, rollback on error, authoritative overwrite on success)
  - `useRevertSegment` hook with server-confirmed state only (no optimistic updates)
  - `useSegmentCorrectionHistory` hook with `staleTime: 0` and conditional `enabled`
  - TanStack Query cache patched via `queryClient.setQueryData` on infinite query pages — no `invalidateQueries` on success
  - SegmentEditState discriminated union (read | editing | confirming-revert | history) preventing impossible UI states
  - Dedicated `aria-live` region for screen reader announcements (edit entered, saved, cancelled, revert shown/completed, history opened, errors)
  - Full keyboard accessibility: Tab navigation to all buttons, Escape cancel with correct focus restoration, `stopPropagation` to prevent parent scroll interception
  - Segment row `hover:bg-slate-50` highlight and button tooltips (Edit, Revert, History)
  - 14 new frontend files: 4 correction components, 3 hooks, 1 type file, 1 barrel export, 5 test files
  - 8 modified files: TranscriptSegments.tsx, TranscriptPanel.tsx, VideoCard.tsx, transcript types, video types, useTranscriptSegments, backend video schemas + router

### Technical
- 263 new tests (252 frontend + 11 backend); 2,320 total frontend tests, 5,700+ total backend tests
- WCAG 2.1 Level AA compliance (keyboard 2.1.1, focus 2.4.3/2.4.7, touch targets 2.5.8, color 1.4.1, status messages 4.1.3, error prevention 3.3.4)
- Frontend version: 0.10.0 → 0.11.0
- No new dependencies, no database migrations (uses Features 033/034 tables)
- mypy strict + TypeScript strict compliance (0 errors)

## [0.37.0] - 2026-03-03

### Added
- **Feature 034: Correction Submission API (ADR-005 Increment 4)**
  - `POST .../segments/{segment_id}/corrections` — Submit a correction with `corrected_text`, `correction_type`, optional `correction_note` and `corrected_by_user_id`; returns 201 with audit record and segment state
  - `POST .../segments/{segment_id}/corrections/revert` — Revert latest correction (no body); returns 200 with revert audit record and restored segment state
  - `GET .../segments/{segment_id}/corrections` — Paginated correction history ordered by version_number DESC; returns empty list for uncorrected segments
  - `language_code` required query parameter on all 3 endpoints (matches existing transcript endpoint pattern)
  - Field validator rejects `correction_type=revert` on submit (must use dedicated revert endpoint)
  - RFC 7807 error codes: `SEGMENT_NOT_FOUND`, `NO_CHANGE_DETECTED`, `INVALID_CORRECTION_TYPE`, `NO_ACTIVE_CORRECTION`, `NOT_FOUND`
  - 3 new fields on existing segment list response: `has_correction` (bool), `corrected_at` (datetime | null), `correction_count` (int) — derived via single aggregation query
  - 5 Pydantic V2 schemas: `CorrectionSubmitRequest`, `CorrectionAuditRecord`, `SegmentCorrectionState`, `CorrectionSubmitResponse`, `CorrectionRevertResponse`
  - Authentication required on all endpoints (existing `require_auth` dependency)

### Technical
- 57 new tests (33 unit schemas + 24 integration API)
- 5,689 total tests passing with 0 regressions
- 100% coverage on correction router and schemas
- mypy strict compliance (0 errors)
- No new dependencies, no database migrations (uses Feature 033 tables)

## [0.36.0] - 2026-03-02

### Added
- **Feature 033: Transcript Corrections Audit Table (ADR-005 Increment 3)**
  - Append-only `transcript_corrections` audit table with UUIDv7 PKs, composite FK to `video_transcripts`, version chains, and `CorrectionType` enum (spelling, profanity_fix, context_correction, formatting, asr_error, revert)
  - `TranscriptCorrectionRepository` with immutability enforcement (`update()`/`delete()` raise `NotImplementedError`), segment/video queries, pagination, and `FOR UPDATE` row locking for version safety
  - `TranscriptCorrectionService.apply_correction()` — atomically creates audit record + updates segment `corrected_text`/`has_correction` + updates transcript metadata (`has_corrections`, `correction_count`, `last_corrected_at`); version chain preserves previous effective text as `original_text`
  - `TranscriptCorrectionService.revert_correction()` — reverts to previous state (revert-to-original clears correction, revert-to-prior restores previous version); records revert as new audit entry
  - Re-download protection: corrected segments preserve `corrected_text` during transcript sync; `--force-overwrite` flag bypasses protection
  - 3 new columns on `video_transcripts`: `has_corrections`, `last_corrected_at`, `correction_count`
  - Flush-only transaction pattern throughout (caller owns transaction lifecycle)
  - Cross-feature contract tests: `display_text` property, search ILIKE on `corrected_text`, SRT export, API responses
  - Pydantic V2 domain models: `TranscriptCorrectionBase`, `TranscriptCorrectionCreate`, `TranscriptCorrectionRead`
  - Alembic migration fully reversible (downgrade drops table and removes columns)

### Technical
- 139 new tests (34 unit models + 44 unit repository + 31 unit service + 9 unit transcript service + 21 integration)
- Hypothesis property-based tests for enum exhaustiveness, text edge cases, version chain integrity
- 5,632 total tests passing with 0 regressions
- 97-100% coverage on all new source files
- mypy strict compliance (0 errors)
- No new dependencies, no new API endpoints, no frontend changes

## [0.35.0] - 2026-02-27

### Added
- **Feature 032: Canonical Tag Frontend Integration (ADR-003 Phase 3 Frontend)**
  - Canonical tag autocomplete with aggregated video counts and variation counts (replaces raw tag autocomplete)
  - Two-line dropdown options: canonical form + video count on line 1, "N variations" on line 2
  - "Did you mean:" fuzzy suggestions when prefix search returns zero results
  - Rate limit 429 handling with `Retry-After` header support
  - Consolidated filter pills: single pill per canonical tag with "· N vars" badge and teal color scheme
  - `?canonical_tag=<normalized_form>` URL parameters replace `?tag=<raw_tag>` for all new tag navigation
  - Video detail tags grouped by canonical form with top aliases displayed ("Also: MEXICO, mexico, méxico")
  - Unresolved/orphaned tags shown in separate "Unresolved Tags" subsection with slate italic styling
  - Skeleton loading placeholders during canonical tag resolution
  - New hooks: `useCanonicalTags` (search), `useCanonicalTagDetail` (detail with aliases)
  - New types: `CanonicalTagListItem`, `SelectedCanonicalTag`, `CanonicalTagDetailResponse`, etc.
  - Design token: `filterColors.canonical_tag` (teal: `#F0FDFA`/`#134E4A`/`#99F6E4`)

### Migration Notes
- **Old `?tag=` bookmarks still work** — backend endpoint unchanged, frontend reads both `tag` and `canonical_tag` URL params
- Frontend no longer generates `?tag=` URLs; all new tag links use `?canonical_tag=<normalized_form>`
- Requires Features 028a/029/030 deployed; without backfill, canonical endpoints return empty results

### Technical
- 212 new frontend tests (2,177 total, 88 test files)
- Frontend version: 0.9.0 → 0.10.0
- No backend changes, no new dependencies, no migrations
- WCAG 2.1 Level AA compliance maintained

## [0.34.0] - 2026-02-27

### Added
- **Feature 031: Tag Management CLI (ADR-003 Phase 4)**
  - 7 new CLI commands for manual curation of 124,686 canonical tags with full undo capability
  - `tags merge <sources...> --into <target>` — merge spelling variants with multi-source support (single atomic operation)
  - `tags split <normalized_form> --aliases "raw1,raw2,..."` — split incorrectly merged aliases into a new canonical tag
  - `tags rename <normalized_form> --to "New Form"` — change display form without affecting normalized form
  - `tags classify <normalized_form> --type <entity_type>` — assign entity type (person, organization, place, event, work, technical_term, topic, descriptor)
  - `tags classify --top N` — display top N unclassified canonical tags by video count for triage
  - `tags deprecate <normalized_form>` — soft-delete junk tags (excluded from search/browse, data preserved)
  - `tags collisions` — interactive review of Tier 1 diacritic collision candidates with [s]plit/[k]eep/[n]ext actions
  - `tags undo <operation_id>` — reverse any operation using self-contained `rollback_data` JSONB
  - `tags undo --list` — show 20 most recent operations with IDs, types, timestamps, rolled_back status
  - `TagManagementService` orchestrating all operations with atomic transactions and type-specific undo handlers
  - Entity classification creates `named_entities` + `entity_aliases` records for entity-producing types; topic/descriptor set `entity_type` only
  - Upsert semantics for entity alias creation handling duplicate normalized forms (e.g., "Aaron Mate" / "Aaron Maté")
  - `TagOperationLogRepository` for audit trail access (get, exists, get_recent, get_by_operation_id)
  - 4 Pydantic V2 models: `TagOperationLogBase`, `TagOperationLogCreate`, `TagOperationLogUpdate`, `TagOperationLog`
  - 7 result dataclasses: `MergeResult`, `SplitResult`, `RenameResult`, `ClassifyResult`, `DeprecateResult`, `UndoResult`, `CollisionGroup`
  - All commands support `--reason "text"` flag stored in operation logs
  - Rich console output with formatted panels and tables for all operations

### Fixed
- UUID JSON serialization in `tag_operation_logs` JSONB columns (Pydantic V2 coercion workaround)
- Entity alias unique constraint violation during classify when multiple aliases normalize to same form

### Technical
- 181 new tests (73 unit service + 35 unit repository + 73 integration CLI)
- 5,493 total tests passing with 0 regressions
- mypy strict compliance (0 errors across 415 source files)
- No new dependencies, no database migrations
- `video_tags` table never modified (Safety Guarantee #1 from ADR-003)

## [0.33.0] - 2026-02-23

### Added
- **Feature 030: Canonical Tag API (ADR-003 Phase 3)**
  - `GET /api/v1/canonical-tags` — browse all 124,686 canonical tags with prefix search, sorted by video_count DESC
  - `GET /api/v1/canonical-tags/{normalized_form}` — tag detail with top raw-form aliases and occurrence counts
  - `GET /api/v1/canonical-tags/{normalized_form}/videos` — paginated videos spanning all raw tag variations via 3-table JOIN
  - `GET /api/v1/videos?canonical_tag=...` — filter videos by canonical tag with AND semantics across multiple values
  - Fuzzy suggestion fallback (Levenshtein distance ≤ 2) when prefix search yields no results, returning structured `CanonicalTagSuggestion` objects
  - Per-client IP rate limiting (50 req/min) on canonical tag autocomplete endpoint
  - `build_canonical_tag_video_subqueries()` repository method for SQL-level AND intersection filtering
  - 6 Pydantic V2 response schemas: `CanonicalTagListItem`, `CanonicalTagDetail`, `TagAliasItem`, `CanonicalTagSuggestion`, `CanonicalTagListResponse`, `CanonicalTagDetailResponse`
  - `CANONICAL_TAG` filter type added to unified filter system with max 10 values, counting toward MAX_TOTAL_FILTERS=15
  - 10-second query timeout on videos-by-tag endpoint with 504 Gateway Timeout response

### Fixed
- Missing `selectinload(VideoDB.category)` in canonical tag videos repository query causing `MissingGreenlet` error

### Technical
- 96 new tests (21 unit + 25 integration router + 8 integration filter + 4 regression + 7 fuzzy/rate-limit + 24 tag endpoint)
- All test IDs generated via `YouTubeIdFactory` (factory-based, no hand-crafted IDs)
- NFR-005 logging compliance: WARNING for unrecognized filters, INFO for query timing, DEBUG for fuzzy pool details
- Quickstart validation passed all 12 checks against live data (124,686 canonical tags)
- Performance: list endpoint 0.174s (NFR-001: <2s), videos-by-tag 0.091s (NFR-002: <3s)
- No new dependencies, no migrations

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
