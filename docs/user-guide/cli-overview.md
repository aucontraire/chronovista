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
