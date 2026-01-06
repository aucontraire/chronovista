# Data Synchronization

Guide to synchronizing your YouTube data with chronovista.

## Overview

chronovista syncs data from two sources:

1. **YouTube Data API** - Real-time data from your account
2. **Google Takeout** - Historical data export (see [Google Takeout Guide](google-takeout.md))

## Quick Start

```bash
# Authenticate first
chronovista auth login

# Sync everything
chronovista sync all

# Or sync specific data types
chronovista sync topics
chronovista sync playlists
chronovista sync transcripts
```

## Sync Commands

### Full Sync

```bash
chronovista sync all
```

Synchronizes all data types in the correct dependency order:

1. Topic categories
2. Channels
3. Videos
4. Playlists
5. Transcripts
6. User interactions

**Options:**

| Option | Description |
|--------|-------------|
| `--topic <id>` | Filter by topic category |
| `--incremental` | Only sync new data |
| `--dry-run` | Preview without changes |

### Topic Categories

```bash
chronovista sync topics
```

Syncs YouTube's 32 standard topic categories. This should be run first as other data references these topics.

**Output:**
```
Syncing topic categories...
Created: 32, Updated: 0
```

### Channels

```bash
chronovista sync channels
```

Syncs channel metadata for:

- Your subscribed channels
- Channels from watched videos
- Channels from playlists

### Videos

```bash
chronovista sync videos
```

Syncs video metadata including:

- Title, description, duration
- View count, like count
- Tags and topic associations
- Language information
- Content restrictions

### Playlists

```bash
chronovista sync playlists
```

Syncs your YouTube playlists:

- User-created playlists
- Saved playlists
- Playlist items and positions

### Transcripts

```bash
chronovista sync transcripts
```

Downloads video transcripts based on language preferences.

**Options:**

| Option | Description |
|--------|-------------|
| `--language <code>` | Specific language (BCP-47) |
| `--limit <n>` | Maximum videos to process |
| `--priority-cc` | Prioritize closed captions |

## Sync Strategies

### Incremental Sync

For regular updates, use incremental sync:

```bash
chronovista sync all --incremental
```

This:

- Only fetches new data since last sync
- Updates changed records
- Skips unchanged data
- Minimizes API quota usage

### Topic-Filtered Sync

Focus on specific content categories:

```bash
# Only sync News & Politics content
chronovista sync all --topic 25

# Only sync Music content
chronovista sync all --topic 10
```

### Dry Run

Preview what would be synced:

```bash
chronovista sync all --dry-run
```

Shows:

- Number of records to create
- Records to update
- Estimated API calls
- Quota usage estimate

## Data Flow

```
YouTube Data API
       │
       ▼
┌─────────────────┐
│  Sync Service   │
│                 │
│ - Rate limiting │
│ - Batch calls   │
│ - Error retry   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Repositories   │
│                 │
│ - Validation    │
│ - Deduplication │
│ - FK integrity  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Database     │
│                 │
│ - PostgreSQL    │
│ - Full history  │
└─────────────────┘
```

## Rate Limiting

chronovista implements intelligent rate limiting to respect API quotas:

### YouTube Data API

| Resource | Quota Cost | Daily Limit |
|----------|------------|-------------|
| videos.list | 1 unit | 10,000 |
| channels.list | 1 unit | 10,000 |
| playlists.list | 1 unit | 10,000 |
| captions.list | 50 units | 200 calls |
| captions.download | 200 units | 50 calls |

### Transcript Downloads

The `youtube-transcript-api` has IP-based limits:

```
Max requests/hour: 50-100
Delay between requests: 5 seconds
Daily limit: 300-500 requests
```

## Error Handling

### Automatic Retry

Transient errors are automatically retried:

```python
# Default retry configuration
max_retries = 3
retry_delay = 5  # seconds
backoff_factor = 2
```

### Error Types

| Error | Handling |
|-------|----------|
| Rate limit | Wait and retry |
| Quota exceeded | Stop and report |
| Network error | Retry with backoff |
| API error | Log and continue |

### Viewing Errors

```bash
# Check sync status
chronovista status

# View detailed logs
cat ~/.chronovista/logs/sync.log
```

## Monitoring Progress

### Progress Bars

Enable detailed progress tracking:

```bash
chronovista sync all --progress
```

Shows:

- Current operation
- Items processed
- Estimated time remaining
- Error count

### Status Check

```bash
chronovista status
```

Output:
```
Database Status
---------------
Channels: 1,234
Videos: 45,678
Transcripts: 12,345
Topics: 32

Last Sync: 2024-01-15 10:30:00
Next Scheduled: None
```

## Best Practices

### Initial Sync

For first-time setup:

```bash
# 1. Sync topics first
chronovista sync topics

# 2. Full sync
chronovista sync all --progress

# 3. Import Takeout for complete history
chronovista takeout seed /path/to/takeout --progress
```

### Regular Updates

For ongoing use:

```bash
# Daily incremental sync
chronovista sync all --incremental
```

### Large Libraries

For accounts with extensive history:

```bash
# Sync in batches by topic
chronovista sync all --topic 10  # Music
chronovista sync all --topic 20  # Gaming
chronovista sync all --topic 27  # Education
```

## Troubleshooting

### Sync Hangs

If sync appears stuck:

1. Check network connection
2. Verify authentication: `chronovista auth status`
3. Check logs: `cat ~/.chronovista/logs/sync.log`
4. Try with verbose: `chronovista sync all --verbose`

### Missing Data

If data seems incomplete:

1. Ensure topics are synced first
2. Check topic filter isn't too restrictive
3. Verify API quotas aren't exhausted
4. Try full sync without incremental flag

### Database Errors

If you encounter database errors:

```bash
# Check database status
make dev-db-status

# Reset and re-sync if needed
make dev-db-reset
chronovista sync all
```

## See Also

- [Google Takeout](google-takeout.md) - Import historical data
- [Topic Analytics](topic-analytics.md) - Analyze synced data
- [Transcripts](transcripts.md) - Transcript management
- [Configuration](../getting-started/configuration.md) - Rate limit settings
