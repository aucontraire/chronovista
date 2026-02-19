# CLI Overview

Complete reference for chronovista command-line interface.

## Command Structure

```
chronovista [OPTIONS] COMMAND [ARGS]...
```

## Global Options

| Option | Description |
|--------|-------------|
| `--version` | Show version and exit |
| `--help` | Show help and exit |
| `--verbose` | Enable verbose output |

## Command Groups

### Authentication Commands

```bash
chronovista auth [COMMAND]
```

| Command | Description |
|---------|-------------|
| `login` | Authenticate with YouTube |
| `logout` | Clear authentication |
| `status` | Check authentication status |

### Sync Commands

```bash
chronovista sync [COMMAND]
```

| Command | Description |
|---------|-------------|
| `all` | Full synchronization |
| `topics` | Sync topic categories |
| `playlists` | Sync playlists |
| `transcripts` | Sync video transcripts |
| `history` | Sync watch history |

### Topic Commands

```bash
chronovista topics [COMMAND]
```

| Command | Description |
|---------|-------------|
| `list` | List all topics |
| `show <id>` | Show topic details |
| `videos <id>` | Videos in topic |
| `channels <id>` | Channels in topic |
| `popular` | Popular topics |
| `related <id>` | Related topics |
| `similar <id>` | Similar topics |
| `chart` | Visual chart |
| `tree <id>` | Relationship tree |
| `explore` | Interactive exploration |
| `trends` | Trend analysis |
| `insights` | Personalized insights |
| `graph` | Export graph data |
| `heatmap` | Activity heatmap |
| `engagement` | Engagement analytics |
| `channel-engagement <id>` | Channel engagement |

### Category Commands

```bash
chronovista categories [COMMAND]
```

| Command | Description |
|---------|-------------|
| `list` | List all video categories |
| `show <category>` | Show category details (by ID or name) |
| `videos <category>` | Videos in category |

**Note:** Categories are YouTube's creator-assigned video categories (e.g., "Music", "Gaming", "Comedy").

### Tag Commands

```bash
chronovista tags [COMMAND]
```

| Command | Description |
|---------|-------------|
| `list` | List popular tags by video count |
| `show --tag <tag>` | Show tag details and related tags |
| `videos --tag <tag>` | Videos with a specific tag |
| `search --pattern <pattern>` | Search tags by pattern |
| `stats` | Comprehensive tag statistics |
| `by-video --id <video_id>` | Show all tags for a video |

**Note:** Tags use `--tag`, `--pattern`, and `--id` options (not positional arguments) to support tags and video IDs that start with `-`.

### Playlist Commands

```bash
chronovista playlist [COMMAND]
```

| Command | Description |
|---------|-------------|
| `list` | List playlists with link status |
| `show <id>` | Show playlist details |

**Note:** Link status is derived from the playlist ID prefix:
- `PL` prefix or `LL`/`WL`/`HL` = Linked (YouTube playlist)
- `int_` prefix = Unlinked (internal/local playlist)

### Enrich Commands

```bash
chronovista enrich [COMMAND]
```

| Command | Description |
|---------|-------------|
| `run` | Enrich video metadata from YouTube API |
| `status` | Show enrichment status |
| `channels` | Enrich channel metadata |

### Takeout Commands

```bash
chronovista takeout [COMMAND]
```

| Command | Description |
|---------|-------------|
| `seed <path>` | Seed database from Takeout |
| `peek <path>` | Preview Takeout data |
| `analyze <path>` | Analyze Takeout data |
| `inspect <path>` | Deep inspection |
| `integrate <path>` | Integrate with API data |

### Language Commands

```bash
chronovista languages [COMMAND]
```

| Command | Description |
|---------|-------------|
| `set` | Set language preferences |
| `show` | View preferences |
| `config` | Configure auto-download |

### Export Commands

```bash
chronovista export [COMMAND]
```

| Command | Description |
|---------|-------------|
| `videos` | Export video data |
| `channels` | Export channel data |
| `watch-history` | Export watch history |

### Recover Commands

```bash
chronovista recover [COMMAND]
```

| Command | Description |
|---------|-------------|
| `video` | Recover metadata for deleted videos via Wayback Machine |

**Note:** Requires `beautifulsoup4` (included in default install). Optional `selenium` enables pre-2017 page fallback.

Video recovery also attempts to recover the associated channel's metadata when the channel is unavailable. In batch mode (`--all`), the summary report includes channel recovery statistics showing how many channels were attempted, recovered, and which fields were restored.

### API Commands

```bash
chronovista api [COMMAND]
```

| Command | Description |
|---------|-------------|
| `start` | Start the REST API server |

## Detailed Command Reference

### Authentication

#### Login

```bash
chronovista auth login
```

Opens browser for OAuth authentication with YouTube.

**Options:**

- `--force` - Force re-authentication even if already logged in

#### Status

```bash
chronovista auth status
```

Shows current authentication status and token expiration.

### API Server

#### Start Server

```bash
chronovista api start [OPTIONS]
```

Starts the FastAPI REST API server for programmatic access to your data.

**Options:**

- `--host <host>` - Host to bind to (default: 127.0.0.1)
- `--port <port>` - Port to listen on (default: 8000)
- `--reload` - Enable auto-reload for development

**Examples:**

```bash
# Start with defaults
chronovista api start

# Start on specific port
chronovista api start --port 8765

# Development mode with auto-reload
chronovista api start --reload
```

**Notes:**

- Requires prior authentication via `chronovista auth login`
- Interactive API documentation available at `http://localhost:<port>/docs`
- OpenAPI specification at `http://localhost:<port>/openapi.json`

### Synchronization

#### Sync All

```bash
chronovista sync all
```

Performs full synchronization of all data types.

**Options:**

- `--topic <id>` - Filter by topic ID
- `--incremental` - Only sync new data
- `--dry-run` - Preview without changes

#### Sync Topics

```bash
chronovista sync topics
```

Populates the database with YouTube's 32 standard topic categories.

#### Sync Transcripts

```bash
chronovista sync transcripts [OPTIONS]
```

Downloads transcripts for videos in your database with full timestamp preservation.

**Options:**

- `--video-id <id>` - Sync specific video(s) (can be repeated)
- `--language <code>` - Preferred language code (default: en, can be repeated)
- `--limit <n>` - Maximum videos to process (default: 100)
- `--force` - Re-download existing transcripts
- `--dry-run` - Preview without downloading

**Examples:**

```bash
# Preview what would be synced
chronovista sync transcripts --dry-run

# Sync transcripts for all videos without transcripts
chronovista sync transcripts

# Sync specific videos
chronovista sync transcripts --video-id VIDEO_ID

# Sync with language preference
chronovista sync transcripts --language es --language en --limit 50
```

### Topic Analytics

#### List Topics

```bash
chronovista topics list
```

Lists all topic categories with content counts.

#### Popular Topics

```bash
chronovista topics popular [OPTIONS]
```

**Options:**

- `--metric [videos|channels|combined]` - Ranking metric (default: videos)
- `--limit <n>` - Number of results (default: 10)

#### Similar Topics

```bash
chronovista topics similar <TOPIC_ID> [OPTIONS]
```

Finds topics with similar content patterns using cosine similarity.

**Options:**

- `--min-similarity <float>` - Minimum similarity threshold (default: 0.1)
- `--limit <n>` - Number of results (default: 10)

#### Topic Chart

```bash
chronovista topics chart [OPTIONS]
```

Displays ASCII bar chart of topic popularity.

**Options:**

- `--metric [videos|channels|combined]` - Chart metric
- `--limit <n>` - Number of topics to show
- `--width <n>` - Chart width in characters

#### Topic Tree

```bash
chronovista topics tree <TOPIC_ID> [OPTIONS]
```

Visualizes topic relationships as a hierarchical tree.

**Options:**

- `--max-depth <n>` - Maximum tree depth (default: 2)
- `--min-confidence <float>` - Minimum confidence for relationships
- `--no-stats` - Hide statistics

#### Interactive Exploration

```bash
chronovista topics explore [OPTIONS]
```

Interactive topic exploration with guided workflow.

**Options:**

- `--auto-advance` - Auto-advance through topics
- `--no-analytics` - Skip analytics for faster browsing

#### Trends Analysis

```bash
chronovista topics trends [OPTIONS]
```

Analyzes topic popularity trends over time.

**Options:**

- `--period [monthly|weekly|daily]` - Time period (default: monthly)
- `--months-back <n>` - Number of months to analyze
- `--direction [growing|declining|stable]` - Filter by trend direction
- `--limit <n>` - Number of results

#### Graph Export

```bash
chronovista topics graph [OPTIONS]
```

Exports topic relationship data for visualization.

**Options:**

- `--format [dot|json]` - Output format (default: dot)
- `--output <file>` - Output file path
- `--min-confidence <float>` - Minimum relationship confidence
- `--limit <n>` - Maximum number of topics

### Category Analytics

#### List Categories

```bash
chronovista categories list [OPTIONS]
```

Lists all YouTube video categories with video counts.

**Options:**

- `--assignable-only, -a` - Only show categories that creators can assign

#### Show Category

```bash
chronovista categories show <CATEGORY>
```

Shows details for a specific category. Accepts category ID (e.g., "23") or name (e.g., "Comedy").

#### Videos by Category

```bash
chronovista categories videos <CATEGORY> [OPTIONS]
```

Shows videos in a specific category.

**Options:**

- `--limit, -l <n>` - Number of results (default: 20)
- `--include-deleted` - Include deleted videos

### Tag Analytics

#### List Tags

```bash
chronovista tags list [OPTIONS]
```

Lists the most popular tags ordered by video count.

**Options:**

- `--limit, -l <n>` - Number of results (default: 50)

#### Show Tag

```bash
chronovista tags show --tag <TAG> [OPTIONS]
```

Shows details for a specific tag, including related tags that frequently appear together.

**Options:**

- `--tag, -t <tag>` - Tag to show (required)
- `--related, -r <n>` - Number of related tags (default: 10)

**Example:**
```bash
# Tag starting with hyphen requires --tag option
chronovista tags show --tag "-ALFIE"
chronovista tags show -t "music"
```

#### Videos by Tag

```bash
chronovista tags videos --tag <TAG> [OPTIONS]
```

Shows videos with a specific tag.

**Options:**

- `--tag, -t <tag>` - Tag to search for (required)
- `--limit, -l <n>` - Number of results (default: 20)

#### Search Tags

```bash
chronovista tags search --pattern <PATTERN> [OPTIONS]
```

Search for tags matching a pattern (case-insensitive partial match).

**Options:**

- `--pattern, -p <pattern>` - Pattern to search for (required)
- `--limit, -l <n>` - Number of results (default: 30)

#### Tag Statistics

```bash
chronovista tags stats
```

Shows comprehensive tag statistics including total tags, unique tags, average tags per video, and most common tags.

#### Tags by Video

```bash
chronovista tags by-video --id <VIDEO_ID>
```

Shows all tags for a specific video.

**Options:**

- `--id, -i <video_id>` - Video ID (required)

**Example:**
```bash
# Video ID starting with hyphen requires --id option
chronovista tags by-video --id "-2kc5xfeQEs"
chronovista tags by-video -i "dQw4w9WgXcQ"
```

### Playlist Management

#### List Playlists

```bash
chronovista playlist list [OPTIONS]
```

Lists playlists with their link status (derived from playlist ID prefix).

**Options:**

- `--linked` - Show only linked playlists (YouTube IDs)
- `--unlinked` - Show only unlinked playlists (internal IDs)
- `--limit, -n <n>` - Maximum playlists to show (default: 50)
- `--format [table|json|csv]` - Output format (default: table)
- `--sort [title|videos|status]` - Sort order (default: title)

**Examples:**

```bash
# List all playlists
chronovista playlist list

# List only YouTube-linked playlists
chronovista playlist list --linked

# Export as JSON
chronovista playlist list --format json --limit 100
```

#### Show Playlist

```bash
chronovista playlist show <PLAYLIST_ID>
```

Shows detailed information about a specific playlist.

Accepts both internal IDs (`int_` prefix) and YouTube IDs (`PL` prefix).

**Examples:**

```bash
chronovista playlist show PLdU2XMVb99xMxwMeeLWDqmyW8GFqpvgVC
chronovista playlist show int_7f37ed8c5d41402abc4b2a76b9719d91
```

### Enrichment

#### Run Enrichment

```bash
chronovista enrich run [OPTIONS]
```

Enriches video metadata from the YouTube Data API.

**Options:**

- `--limit <n>` - Maximum videos to enrich
- `--priority [high|medium|low|all]` - Priority level filter
- `--dry-run` - Preview without making changes
- `--include-playlists` - Also enrich playlist metadata
- `--report <path>` - Generate JSON report
- `--log-file <path>` - Log to file

**Examples:**

```bash
# Enrich up to 1000 videos
chronovista enrich run --limit 1000

# Preview what would be enriched
chronovista enrich run --dry-run --limit 100

# Enrich with report generation
chronovista enrich run --report ./enrichment-report.json
```

#### Enrichment Status

```bash
chronovista enrich status
```

Shows current enrichment status including counts of enriched vs. pending videos.

#### Enrich Channels

```bash
chronovista enrich channels [OPTIONS]
```

Enriches channel metadata from the YouTube Data API.

**Options:**

- `--limit <n>` - Maximum channels to enrich
- `--dry-run` - Preview without making changes

### Video Recovery

#### Recover Video

```bash
chronovista recover video [OPTIONS]
```

Recovers metadata for deleted YouTube videos from the Internet Archive's Wayback Machine. Supports single-video and batch recovery modes.

**Options:**

- `--video-id, -v <id>` - Recover a single video by ID
- `--all, -a` - Recover all unavailable videos (batch mode)
- `--limit, -l <n>` - Maximum videos to recover (batch mode only)
- `--dry-run` - Preview recovery without making changes
- `--delay, -d <seconds>` - Delay between videos in batch mode (default: 1.0)
- `--start-year <year>` - Only search Wayback snapshots from this year onward (2005-2026)
- `--end-year <year>` - Only search Wayback snapshots up to this year (2005-2026)

**Note:** `--video-id` and `--all` are mutually exclusive. One must be specified.

**Examples:**

```bash
# Recover a specific video
chronovista recover video --video-id dQw4w9WgXcQ

# Recover all unavailable videos
chronovista recover video --all --limit 50

# Preview what would be recovered
chronovista recover video --all --dry-run --limit 10

# Focus on archives from a specific era
chronovista recover video --video-id VIDEO_ID --start-year 2018 --end-year 2020

# Batch recovery with slower rate limiting
chronovista recover video --all --delay 2.0
```

**Recovery Details:**

- Queries the Wayback Machine CDX API for archived YouTube video pages
- Extracts metadata from JSON (`ytInitialPlayerResponse`) or HTML meta tags
- Recovers: title, description, channel, tags, upload date, view/like counts, category, thumbnail
- Three-tier overwrite policy: immutable fields fill-if-NULL only, mutable fields overwrite-if-newer, NULL protection
- Results are cached locally for 24 hours to avoid redundant API calls
- Creates stub channel records when recovered `channel_id` has no existing DB entry
- Automatically attempts channel recovery when the associated channel is unavailable
- Batch summary includes channel recovery statistics (channels attempted, recovered, and fields restored)

### Google Takeout

#### Seed Database

```bash
chronovista takeout seed <PATH> [OPTIONS]
```

Imports Google Takeout data into the database.

**Options:**

- `--incremental` - Safe to re-run, only adds new data
- `--dry-run` - Preview without database changes
- `--only <types>` - Seed specific data types (channels,videos,playlists)
- `--skip <types>` - Skip certain data types
- `--progress` - Show detailed progress bars

#### Peek

```bash
chronovista takeout peek <PATH> [OPTIONS]
```

Preview Takeout data without importing.

**Options:**

- `--summary` - Show summary only
- `--by-topic` - Group by topics

#### Analyze

```bash
chronovista takeout analyze <PATH> [OPTIONS]
```

Analyze patterns in Takeout data.

**Options:**

- `--type [viewing-patterns|channel-relationships|temporal-patterns]`
- `--topic <id>` - Filter by topic
- `--export [csv|json]` - Export results

### Export

#### Export Videos

```bash
chronovista export videos [OPTIONS]
```

Export video data.

**Options:**

- `--format [csv|json]` - Output format
- `--channel <id>` - Filter by channel
- `--with-transcripts` - Include transcript data
- `--language-filter <code>` - Filter by language

#### Export Watch History

```bash
chronovista export watch-history [OPTIONS]
```

Export viewing history.

**Options:**

- `--language-breakdown` - Group by language
- `--date-range <start,end>` - Date range filter
- `--channel <id>` - Filter by channel

## Examples

### Basic Workflow

```bash
# 1. Authenticate
chronovista auth login

# 2. Sync topics first
chronovista sync topics

# 3. Full sync
chronovista sync all

# 4. Explore your data
chronovista topics popular
chronovista topics chart --metric combined
```

### Takeout Analysis

```bash
# Preview Takeout data
chronovista takeout peek /path/to/takeout --summary

# Seed database
chronovista takeout seed /path/to/takeout --progress

# Analyze patterns
chronovista takeout analyze /path/to/takeout --type viewing-patterns
```

### Topic Deep Dive

```bash
# Find popular topics
chronovista topics popular --limit 5

# Explore relationships
chronovista topics similar 10 --min-similarity 0.3
chronovista topics tree 10 --max-depth 3

# Export for visualization
chronovista topics graph --format json --output topics.json
```

### Category Exploration

```bash
# List all categories with video counts
chronovista categories list

# Show only assignable categories
chronovista categories list --assignable-only

# View category details (by name or ID)
chronovista categories show Comedy
chronovista categories show 23

# Browse videos in a category
chronovista categories videos Music --limit 50
```

### Tag Exploration

```bash
# List most popular tags
chronovista tags list --limit 20

# View tag details (note: use --tag for tags starting with -)
chronovista tags show --tag "music"
chronovista tags show --tag "-ALFIE"

# Find videos with specific tag
chronovista tags videos --tag "gaming" --limit 30

# Search for tags matching a pattern
chronovista tags search --pattern "python"

# View tag statistics
chronovista tags stats

# View all tags for a specific video
chronovista tags by-video --id "dQw4w9WgXcQ"
chronovista tags by-video --id "-2kc5xfeQEs"  # Video ID starting with -
```

### Deleted Video Recovery

```bash
# Recover a specific deleted video
chronovista recover video --video-id dQw4w9WgXcQ

# Recover all unavailable videos (batch mode)
chronovista recover video --all --limit 50

# Preview recovery without making changes
chronovista recover video --all --dry-run

# Focus search on a specific era (faster for older videos)
chronovista recover video --video-id VIDEO_ID --start-year 2018

# Batch recovery with custom rate limiting
chronovista recover video --all --limit 20 --delay 2.0
```

### REST API Workflow

```bash
# 1. Authenticate (same as CLI)
chronovista auth login

# 2. Start API server
chronovista api start --port 8765

# 3. Access via HTTP
curl http://localhost:8765/api/v1/health
curl http://localhost:8765/api/v1/videos?limit=10

# 4. View interactive docs
open http://localhost:8765/docs
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Invalid arguments |
| 3 | Authentication required |
| 4 | API error |
| 5 | Database error |

## See Also

- [Authentication](authentication.md)
- [Data Synchronization](data-sync.md)
- [Topic Analytics](topic-analytics.md)
- [Google Takeout](google-takeout.md)
- [Data Population](data-population.md) - Recommended data population order (including recovery)
- [REST API](rest-api.md)
