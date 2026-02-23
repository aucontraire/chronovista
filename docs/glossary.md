# Glossary

Project-specific terminology used throughout chronovista documentation and code.

## Data Concepts

**Enrichment**
:   The process of fetching additional metadata for existing database records using the YouTube Data API. For example, a video seeded from Google Takeout only has basic info; enrichment adds statistics, tags, topic categories, and other metadata.

**Seeding**
:   Importing initial data from a Google Takeout export into the database. Seeded records contain historical information but lack the real-time metadata that API enrichment provides.

**Sync / Synchronization**
:   Fetching current data from the YouTube Data API and updating the local database. Syncs are incremental by default, only fetching new or updated records.

**Takeout**
:   A Google service ([takeout.google.com](https://takeout.google.com/)) that lets you export your data from Google products. chronovista imports YouTube and YouTube Music data from Takeout exports.

## YouTube Concepts

**Topic Category**
:   YouTube's hierarchical content classification system (e.g., Music, Gaming, Education). Videos can be associated with one or more topic categories. chronovista syncs the full topic taxonomy via `chronovista sync topics`.

**Video Category**
:   A simpler YouTube classification (e.g., "Film & Animation", "Music", "Pets & Animals") assigned by the uploader. Different from topic categories, which are assigned by YouTube's algorithms.

**Linked Playlist / Unlinked Playlist**
:   A **linked playlist** is one that exists in your YouTube account and can be synced via the API. An **unlinked playlist** was imported from Takeout but may no longer exist on YouTube (deleted or made private).

## Transcript Concepts

**Transcript Segment**
:   A single timed text entry in a video transcript, with a start time, duration, and text content. Segments are typically 2-10 seconds long.

**Language Preference**
:   A user-configured preference for transcript languages, with four tiers:
    - **Fluent**: Languages you speak natively (highest priority for transcript download)
    - **Learning**: Languages you're studying (second priority)
    - **Curious**: Languages you're interested in (downloaded when available)
    - **Exclude**: Languages you never want downloaded

**CC (Closed Captions)**
:   Manually created or professionally transcribed captions. Higher quality than auto-generated transcripts.

**Auto-generated Transcript**
:   Transcripts created by YouTube's speech recognition. Available for most videos but may contain errors.

## Recovery Concepts

**Wayback Machine**
:   The Internet Archive's web archive ([web.archive.org](https://web.archive.org/)). chronovista queries archived YouTube video pages to recover metadata for deleted or unavailable videos.

**CDX API**
:   The Wayback Machine's index API (`web.archive.org/cdx/search/cdx`). Returns a list of archived snapshots for a given URL, filtered by status code, MIME type, and date range. chronovista uses this to discover which YouTube video pages have been archived.

**Snapshot**
:   A single archived copy of a web page stored by the Wayback Machine, identified by a 14-digit timestamp (e.g., `20220106075526`). Each snapshot may contain different metadata depending on when it was captured.

**Availability Status**
:   A video or channel's current accessibility state. Values: `available` (normal), `deleted`, `private`, `unavailable` (generic), `region_restricted`. Replaces the legacy `deleted_flag` boolean with richer status tracking.

**Recovery**
:   The process of extracting metadata from a Wayback Machine snapshot of a deleted YouTube page and updating the local database. **Video recovery** pulls title, description, tags, thumbnail, channel info, like/view counts, and upload date using a three-tier overwrite policy. **Channel recovery** pulls title, description, subscriber count, video count, thumbnail, and country using a two-tier overwrite policy. Recovery is available via CLI (`chronovista recover video`), REST API (`POST /api/v1/recovery/videos/{id}` and `POST /api/v1/recovery/channels/{id}`), and the frontend's "Recover from Web Archive" button.

**Recovery Source**
:   The origin of recovered metadata, recorded in the `recovery_source` field. Typically `wayback_machine` for data extracted from Internet Archive snapshots.

**Overwrite Policy (Three-Tier, Videos)**
:   The strategy for merging recovered video metadata with existing database records. **Immutable fields** (e.g., `channel_id`, `category_id`) are only written if the current value is NULL. **Mutable fields** (e.g., `title`, `description`, `view_count`) overwrite existing values if the recovered data is newer. **NULL protection** ensures existing non-NULL values are never blanked by NULL recovered values.

**Overwrite Policy (Two-Tier, Channels)**
:   The strategy for merging recovered channel metadata. All fields are **mutable** (overwrite-if-newer), with **NULL protection** to prevent blanking existing values. There are no immutable fields for channel recovery.

**Idempotency Guard**
:   A mechanism that caches recovery results for 5 minutes. If the same video or channel is recovered again within this window, the cached result is returned immediately without re-querying the Wayback Machine. Prevents redundant network calls and duplicate processing.

**Stub Channel**
:   A minimal channel record created automatically during video recovery when the recovered `channel_id` doesn't exist in the database. Satisfies foreign key constraints and is marked with `availability_status = unavailable`. Stub channels are eligible for subsequent channel recovery to fill in their metadata.

## Tag Normalization Concepts

**Tag Normalization**
:   The process of grouping raw video tags into canonical forms using Unicode normalization, diacritic stripping, and case folding. For example, "México", "mexico", and "MEXICO" all normalize to the same canonical tag. Implemented as a 9-step pipeline in `TagNormalizationService`.

**Canonical Tag**
:   The preferred display form for a group of normalized tags. Selected by preference: title case (`str.istitle()`), then highest frequency, then alphabetical tiebreaker. Stored in the `canonical_tags` table with UUIDv7 primary keys.

**Tag Alias**
:   A raw tag form from `video_tags` linked to its canonical tag. Every distinct raw tag becomes exactly one alias. Stored in the `tag_aliases` table. The `video_tags` table itself is never modified — aliases provide the mapping.

**Collision Candidate**
:   A group of tags that were merged by diacritic stripping where the casefolded forms differ (e.g., "México" casefolds to "méxico" while "Mexico" casefolds to "mexico"). Flagged in `tags analyze` output for manual review. Not an error — most collisions are correct merges.

**Tier 1 Diacritics**
:   Eight combining marks that are universally safe to strip during normalization: acute, grave, circumflex, diaeresis, macron, breve, dot above, and ring above. Stripping these merges common accent variants (e.g., café/cafe) without changing letter identity.

## Technical Concepts

**Development Mode**
:   When `DEVELOPMENT_MODE=true` in `.env`, chronovista uses the development database (`DATABASE_DEV_URL`, typically port 5434) instead of the production database (`DATABASE_URL`, typically port 5432).

**API Key vs OAuth Credentials**
:   An **API key** authenticates the application for public data access. **OAuth credentials** (Client ID + Client Secret) authenticate a specific user for access to their personal data (watch history, playlists, subscriptions).

**Orval**
:   A code generation tool that reads an OpenAPI specification (JSON) and generates TypeScript types and React Query hooks. Used to keep the frontend's API client in sync with the backend.

**Deep Link**
:   A URL that navigates directly to a specific location within the app, such as a particular timestamp in a video transcript (e.g., `/videos/abc123?t=90&lang=en`).

## Architecture Concepts

**Repository Pattern**
:   A data access abstraction that provides CRUD operations for domain entities. Each entity type (Video, Channel, Transcript) has its own repository class.

**Composite Key**
:   A primary key made up of multiple columns. Used for join tables like `video_tags` (video_id + tag) and `transcript_segments` (video_id + language_code + start_time).

**Integration Test Tiers**
:   chronovista's integration tests are organized in dependency tiers:
    - **Tier 1**: Independent entities (Channel, TopicCategory)
    - **Tier 2**: Channel-dependent (ChannelKeyword, Playlist)
    - **Tier 3**: Video core (Video, VideoStatistics)
    - **Tier 4**: Video-dependent (VideoTranscript, VideoTag)
