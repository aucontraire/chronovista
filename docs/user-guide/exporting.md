# Exporting Data

Guide to exporting your YouTube data from chronovista.

## Overview

chronovista supports comprehensive data export in multiple formats with language-aware filtering and customizable options.

## Supported Formats

| Format | Description | Use Case |
|--------|-------------|----------|
| CSV | Comma-separated values | Spreadsheets, Excel |
| JSON | JavaScript Object Notation | APIs, programmatic use |

## Export Commands

### Videos

```bash
# Basic CSV export
chronovista export videos --format csv --output videos.csv

# JSON export
chronovista export videos --format json --output videos.json

# With transcripts
chronovista export videos --with-transcripts

# Filter by channel
chronovista export videos --channel CHANNEL_ID

# Filter by language
chronovista export videos --language-filter en-US
```

### Channels

```bash
# Export channels
chronovista export channels --format csv --output channels.csv

# With analytics
chronovista export channels --with-analytics

# Date range filter
chronovista export channels --date-range 2024-01-01,2024-12-31
```

### Watch History

```bash
# Export watch history
chronovista export watch-history --format csv

# Group by language
chronovista export watch-history --language-breakdown

# Filter by channel
chronovista export watch-history --channel CHANNEL_ID

# Date range
chronovista export watch-history --date-range 2024-01-01,2024-06-30
```

### Transcripts

```bash
# Export transcripts
chronovista export transcripts --format json

# Specific language
chronovista export transcripts --language en-US

# Include video metadata
chronovista export transcripts --include-video-metadata
```

### Topics

```bash
# Export topic data
chronovista export topics --format csv

# With associations
chronovista export topics --with-associations

# As graph data
chronovista topics graph --format json --output topics.json
```

## Export Options

### Common Options

| Option | Description |
|--------|-------------|
| `--format [csv\|json]` | Output format |
| `--output <file>` | Output file path |
| `--limit <n>` | Maximum records |
| `--offset <n>` | Skip first n records |

### Filtering Options

| Option | Description |
|--------|-------------|
| `--channel <id>` | Filter by channel |
| `--topic <id>` | Filter by topic |
| `--language-filter <code>` | Filter by language |
| `--date-range <start,end>` | Date range filter |

### Content Options

| Option | Description |
|--------|-------------|
| `--with-transcripts` | Include transcript data |
| `--with-analytics` | Include analytics data |
| `--with-associations` | Include related entities |
| `--include-video-metadata` | Include full video info |

## CSV Export Format

### Videos CSV

```csv
video_id,title,channel_id,channel_name,duration,upload_date,view_count,like_count
dQw4w9WgXcQ,"Never Gonna Give You Up",UCuAXFkgsw1L7xaCfnd5JJOw,"Rick Astley",213,2009-10-25,1234567890,12345678
```

### Channels CSV

```csv
channel_id,title,subscriber_count,video_count,default_language,country
UCuAXFkgsw1L7xaCfnd5JJOw,"Rick Astley",12000000,150,en,GB
```

### Watch History CSV

```csv
video_id,title,watched_at,watch_duration,watch_percentage
dQw4w9WgXcQ,"Never Gonna Give You Up",2024-01-15T10:30:00,180,85.0
```

## JSON Export Format

### Videos JSON

```json
{
  "exported_at": "2024-01-15T12:00:00Z",
  "total_records": 1000,
  "videos": [
    {
      "video_id": "dQw4w9WgXcQ",
      "title": "Never Gonna Give You Up",
      "channel": {
        "id": "UCuAXFkgsw1L7xaCfnd5JJOw",
        "name": "Rick Astley"
      },
      "duration": 213,
      "upload_date": "2009-10-25",
      "statistics": {
        "view_count": 1234567890,
        "like_count": 12345678
      }
    }
  ]
}
```

### Topics JSON

```json
{
  "exported_at": "2024-01-15T12:00:00Z",
  "topics": [
    {
      "topic_id": 10,
      "name": "Music",
      "video_count": 847,
      "channel_count": 156,
      "related_topics": [
        {"id": 24, "name": "Entertainment", "similarity": 0.65}
      ]
    }
  ]
}
```

## Advanced Export

### Scheduled Exports

Create a script for regular exports:

```bash
#!/bin/bash
DATE=$(date +%Y-%m-%d)

chronovista export videos --format csv --output "exports/videos_$DATE.csv"
chronovista export watch-history --format csv --output "exports/history_$DATE.csv"
```

### Filtered Exports

```bash
# Educational content only
chronovista export videos --topic 27 --format csv

# Music with transcripts
chronovista export videos --topic 10 --with-transcripts --format json

# Recent watch history
chronovista export watch-history --date-range 2024-01-01,today
```

### Large Exports

For very large datasets:

```bash
# Export in chunks
chronovista export videos --limit 10000 --offset 0 --output chunk1.csv
chronovista export videos --limit 10000 --offset 10000 --output chunk2.csv
```

## Data Analysis

### Using with Pandas

```python
import pandas as pd

# Load exported data
videos = pd.read_csv('videos.csv')
history = pd.read_csv('watch_history.csv')

# Analysis
print(f"Total videos: {len(videos)}")
print(f"Watch history entries: {len(history)}")
print(f"Top channels: {videos['channel_name'].value_counts().head()}")
```

### Using with SQL

Export as JSON and load into a database:

```bash
chronovista export videos --format json --output videos.json
```

```sql
-- Load into PostgreSQL
COPY videos FROM 'videos.json' WITH (FORMAT json);
```

## Best Practices

### Regular Backups

```bash
# Weekly backup script
#!/bin/bash
BACKUP_DIR="$HOME/chronovista_backups/$(date +%Y-%m-%d)"
mkdir -p "$BACKUP_DIR"

chronovista export videos --format json --output "$BACKUP_DIR/videos.json"
chronovista export channels --format json --output "$BACKUP_DIR/channels.json"
chronovista export transcripts --format json --output "$BACKUP_DIR/transcripts.json"
chronovista export watch-history --format json --output "$BACKUP_DIR/history.json"
```

### Incremental Exports

```bash
# Export only recent data
chronovista export watch-history \
    --date-range $(date -d '7 days ago' +%Y-%m-%d),$(date +%Y-%m-%d) \
    --output weekly_history.csv
```

### Data Validation

After export, validate:

```python
import pandas as pd

df = pd.read_csv('videos.csv')

# Check for issues
print(f"Null values: {df.isnull().sum()}")
print(f"Duplicate IDs: {df.duplicated('video_id').sum()}")
```

## Troubleshooting

### Empty Export

If export returns no data:

1. Check database has data: `chronovista status`
2. Verify filters aren't too restrictive
3. Check date range format

### Memory Issues

For very large exports:

```bash
# Use streaming export
chronovista export videos --stream --output videos.json

# Or export in chunks
chronovista export videos --limit 5000 --output videos.csv
```

### Encoding Issues

For special characters:

```bash
# Force UTF-8 encoding
chronovista export videos --encoding utf-8 --output videos.csv
```

## See Also

- [CLI Overview](cli-overview.md) - All export commands
- [Data Synchronization](data-sync.md) - Getting data to export
- [Topic Analytics](topic-analytics.md) - Topic export options
