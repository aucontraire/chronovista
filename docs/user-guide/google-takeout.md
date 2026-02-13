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
2. Click **"Deselect all"** to start clean
3. Scroll down and check **YouTube and YouTube Music**

### Step 2: Change History Format to JSON

!!! danger "Critical: Change the format to JSON"
    The default export format for watch history is **HTML**, which chronovista cannot import. You must change it to **JSON**.

1. Under "YouTube and YouTube Music", click the **"HTML format"** button
2. Find the **history** row
3. Change the dropdown from **HTML** to **JSON**
4. Click **OK**

### Step 3: Customize Data Selection

Click **"All YouTube data included"** to choose what to export:

| Data type | Recommended | Notes |
|-----------|-------------|-------|
| **history** | Required | Your watch and search history (must be JSON format) |
| **playlists** | Required | All your playlists with video relationships |
| **subscriptions** | Required | Channel subscriptions with dates |
| channels | Recommended | Channel metadata |
| video metadata | Recommended | Metadata for videos you interacted with |
| comments | Optional | Your comments on videos |
| **videos** | **Uncheck if you're a content creator** | Downloads all your uploaded video files |

!!! warning "Content Creators: Uncheck 'videos'"
    The **videos** option downloads the actual video files you have uploaded to YouTube. If you are a content creator, this can be hundreds of gigabytes. Uncheck **videos** unless you specifically want to download your uploaded content. chronovista does not need video files — it only needs the metadata.

### Step 4: Configure Export Settings

| Setting | Recommended |
|---------|-------------|
| Frequency | Export once |
| File type | .zip |
| File size | Largest available (50GB) |

### Step 5: Download

1. Click **"Create export"**
2. Wait for email notification (can take minutes to hours depending on account size)
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

## Managing Multiple Takeout Exports

If you download Takeout exports periodically, you can keep them organized and use the `recover` command to process them all at once.

### Recommended Directory Structure

Append the export date to each extracted directory name using `YYYY-MM-DD` format:

```
takeout/
├── YouTube and YouTube Music/              # Most recent (no date)
├── YouTube and YouTube Music 2025-08-13/
├── YouTube and YouTube Music 2025-09-14/
├── YouTube and YouTube Music 2025-11-17/
├── YouTube and YouTube Music 2025-12-15/
├── YouTube and YouTube Music 2026-01-01/
└── YouTube and YouTube Music 2026-01-27/
```

Each subdirectory should contain the standard Takeout structure (`history/`, `playlists/`, etc.).

!!! important "Date Format Required"
    The `recover` command uses a `YYYY-MM-DD` date pattern in the directory name to identify and sort historical exports. Directories without a recognizable date in their name will be skipped.

### Seeding vs. Recovering

| Command | Purpose | Input |
|---------|---------|-------|
| `takeout seed` | Import **one** Takeout export | Path to a single export directory |
| `takeout recover` | Process **multiple** historical exports at once | Path to a base directory containing dated subdirectories |

### Using the Recover Command

The `recover` command scans a base directory for all date-suffixed subdirectories, sorts them oldest-first, and processes them so that **newer metadata overwrites older**:

```bash
# Preview what would be recovered
chronovista takeout recover --takeout-dir ./takeout --dry-run

# Run recovery across all historical exports
chronovista takeout recover --takeout-dir ./takeout
```

### Workflow for Periodic Exports

1. Download a new Takeout export from [Google Takeout](https://takeout.google.com/)
2. Extract it and rename the directory with today's date:
   ```bash
   # After extracting, rename with the date
   mv "YouTube and YouTube Music" "YouTube and YouTube Music 2026-02-13"
   ```
3. Move it into your `takeout/` directory alongside previous exports
4. Seed the new export:
   ```bash
   chronovista takeout seed ./takeout/"YouTube and YouTube Music 2026-02-13"
   ```
5. Or recover from all exports at once:
   ```bash
   chronovista takeout recover --takeout-dir ./takeout
   ```

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
