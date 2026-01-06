# Google Takeout Integration

Comprehensive guide to using Google Takeout with chronovista.

## Overview

Google Takeout provides complete access to your YouTube data, including watch history that is no longer available through the YouTube Data API. chronovista can import this data to give you a complete picture of your YouTube activity.

## What is Google Takeout?

Google Takeout is Google's data export service that lets you download a complete archive of your YouTube data, including:

- **Complete watch history** (including deleted videos with titles preserved)
- **All playlists** (including private ones) with full video relationships
- **Search history** with timestamps
- **Comments and live chat messages**
- **Channel subscriptions** with dates
- **Liked videos** and other interactions

## Getting Your Takeout Data

### Step 1: Request Export

1. Go to [Google Takeout](https://takeout.google.com/)
2. Click "Deselect all"
3. Scroll down and select **YouTube and YouTube Music**
4. Click "All YouTube data included" to customize:
   - History (required)
   - Playlists (required)
   - Subscriptions (required)
   - Comments (optional)
   - Liked videos (optional)

### Step 2: Configure Export

Choose export settings:

| Setting | Recommended |
|---------|-------------|
| Format | JSON (preferred) or HTML |
| Frequency | One-time |
| File size | Largest available (50GB) |

### Step 3: Download

1. Click "Create export"
2. Wait for email notification (can take hours for large accounts)
3. Download the archive
4. Extract to a local folder

## Import Commands

### Database Seeding

```bash
# Basic import
chronovista takeout seed /path/to/your/takeout

# With progress tracking
chronovista takeout seed /path/to/takeout --progress

# Incremental (safe to re-run)
chronovista takeout seed /path/to/takeout --incremental

# Preview without changes
chronovista takeout seed /path/to/takeout --dry-run
```

### Selective Import

```bash
# Import only specific data types
chronovista takeout seed /path/to/takeout --only channels,videos
chronovista takeout seed /path/to/takeout --only playlists,playlist_memberships

# Skip certain data types
chronovista takeout seed /path/to/takeout --skip user_videos
```

### Import Options

| Option | Description |
|--------|-------------|
| `--progress` | Show detailed progress bars |
| `--incremental` | Only add new data |
| `--dry-run` | Preview without database changes |
| `--only <types>` | Import only specified types |
| `--skip <types>` | Skip specified types |

## Data Types

### What Gets Imported

| Data Type | Description | Status |
|-----------|-------------|--------|
| Channels | All channels from subscriptions and history | Supported |
| Videos | Complete video metadata with historical data | Supported |
| User Videos | Personal watch history with timestamps | Supported |
| Playlists | Playlist metadata and structure | Supported |
| Playlist Memberships | Playlist-video relationships with positions | Supported |

### Data Quality

chronovista performs automatic data cleaning:

- **Video ID Sanitization** - Fixes malformed video IDs (925+ fixed in typical exports)
- **Duplicate Handling** - Prevents duplicate entries
- **Foreign Key Integrity** - Ensures referential consistency
- **Timestamp Normalization** - Standardizes date/time formats

## Analysis Commands

### Peek at Data

Preview your Takeout data structure:

```bash
chronovista takeout peek /path/to/takeout --summary
```

Sample output:
```
Takeout Data Summary
--------------------
Watch History: 15,847 videos
Playlists: 45
Subscriptions: 234
Comments: 1,234
Date Range: 2012-03-15 to 2024-01-20
```

### Analyze Patterns

```bash
# Viewing patterns analysis
chronovista takeout analyze /path/to/takeout --type viewing-patterns

# Channel relationships
chronovista takeout analyze /path/to/takeout --type channel-relationships

# Temporal patterns
chronovista takeout analyze /path/to/takeout --type temporal-patterns
```

### Topic-Filtered Analysis

```bash
# Analyze only educational content
chronovista takeout analyze /path/to/takeout --topic 27

# Group analysis by topics
chronovista takeout peek /path/to/takeout --by-topic
```

### Export Results

```bash
chronovista takeout analyze /path/to/takeout --export csv
chronovista takeout analyze /path/to/takeout --export json
```

## Example Analysis Output

```bash
$ chronovista takeout analyze ./takeout --type viewing-patterns

Viewing Pattern Analysis
========================

Total Videos Watched: 15,847
Total Watch Time: 2,341 hours
Date Range: 2012-03-15 to 2024-01-20
Most Active Period: 2020-2021 (pandemic era)

Top Content Categories:
   1. Technology & Programming (23.4%)
   2. News & Politics (18.7%)
   3. Educational Content (15.2%)
   4. Entertainment (12.8%)

Viewing Trends:
   - Peak viewing hours: 7-9 PM
   - Most active day: Sunday
   - Average session: 47 minutes
   - Binge-watching sessions: 234
```

## Combining with API Data

chronovista can merge Takeout data with live API data for the most complete picture:

### Option 1: Takeout First

```bash
# 1. Seed Takeout data
chronovista takeout seed /path/to/takeout

# 2. Enrich with API data
chronovista sync all
```

This approach:

- Preserves historical data from Takeout
- Enriches with current API information
- Updates metrics (views, likes) to current values

### Option 2: API First

```bash
# 1. Sync API data
chronovista sync all

# 2. Add Takeout data
chronovista takeout seed /path/to/takeout --incremental
```

This approach:

- Gets current data first
- Adds historical data that API can't provide
- Fills in deleted videos and old metadata

### Option 3: Integrated Analysis

```bash
chronovista takeout integrate /path/to/takeout --merge-with-api
```

Benefits of combined data:

- Current data from API (up-to-date metrics, current video status)
- Historical data from Takeout (deleted videos, old metadata)
- Complete timeline reconstruction with relationship integrity
- Queryable database for advanced analytics

## Data Quality Notes

### Takeout Limitations

!!! warning "Data Quality Considerations"

    - Some video IDs in Takeout may be malformed (chronovista sanitizes these)
    - Deleted videos have titles but limited metadata
    - Watch timestamps may have gaps in older data
    - Playlist positions may not perfectly match current state

### Validation

After import, validate your data:

```bash
chronovista status
```

Check for:

- Expected record counts
- Foreign key consistency
- Topic associations

## Troubleshooting

### Import Fails

If import fails:

1. Check Takeout extract completed successfully
2. Verify JSON files are valid
3. Check database connection
4. Try with `--dry-run` first

### Missing Data

If data seems incomplete:

1. Verify Takeout export included all data types
2. Check for extraction errors
3. Look for error logs: `~/.chronovista/logs/takeout.log`

### Performance Issues

For very large exports (10GB+):

```bash
# Import in chunks
chronovista takeout seed /path/to/takeout --only channels
chronovista takeout seed /path/to/takeout --only videos --incremental
chronovista takeout seed /path/to/takeout --only playlists --incremental
```

## Privacy Considerations

!!! tip "Privacy First"

    - All Takeout processing happens locally
    - No data is sent to external servers
    - You maintain complete control over your data
    - Delete Takeout files after import if desired

## Best Practices

### Before Import

1. Ensure database is set up: `make dev-db-up`
2. Run migrations: `make dev-migrate`
3. Sync topics first: `chronovista sync topics`

### During Import

1. Use `--progress` for visibility
2. Monitor disk space for large imports
3. Use `--dry-run` to preview

### After Import

1. Verify data: `chronovista status`
2. Sync API data to enrich: `chronovista sync all`
3. Explore topics: `chronovista topics chart`

## See Also

- [Data Synchronization](data-sync.md) - API synchronization
- [Topic Analytics](topic-analytics.md) - Analyze imported data
- [Configuration](../getting-started/configuration.md) - Database settings
