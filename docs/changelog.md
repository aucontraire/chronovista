# Changelog

All notable changes to chronovista will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- MkDocs documentation setup with Material theme
- Comprehensive user guide and API reference
- Architecture documentation

## [0.12.0] - 2026-02-03

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
