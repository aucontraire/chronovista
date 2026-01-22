# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

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

- Refactored CLI commands to use sync command framework with SyncResult and transformers
- Added ABC interfaces for service layer

### Fixed

- Removed unused imports in CLI commands (ChannelEnrichmentError, ErrorCategory, display_error_panel, etc.)
- Fixed import sorting with isort
