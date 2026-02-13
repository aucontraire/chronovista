# Data Population

Recommended order for populating your chronovista database with YouTube data.

## Overview

chronovista pulls data from two sources:

| Source | What it provides | Command |
|--------|-----------------|---------|
| **YouTube Data API** | Current data (videos, channels, playlists, transcripts) | `chronovista sync` |
| **Google Takeout** | Historical data (watch history, deleted videos) | `chronovista takeout seed` |

## Recommended Population Order

Follow this sequence for the best results. Each step builds on the previous one.

### Step 1: Authenticate

```bash
chronovista auth login
chronovista auth status  # Verify: should show "Authenticated"
```

### Step 2: Sync Topic Categories

Topic categories are YouTube's content classification system. Sync these first because videos reference them.

```bash
chronovista sync topics
```

This is fast (single API call) and creates the foundation for topic analytics.

### Step 3: Import Google Takeout (Optional but Recommended)

If you have a Google Takeout export, import it now to seed your database with historical data including deleted and private videos:

```bash
# Preview what will be imported
chronovista takeout seed /path/to/takeout --dry-run

# Import
chronovista takeout seed /path/to/takeout --progress
```

!!! tip "Get Your Takeout"
    1. Go to [Google Takeout](https://takeout.google.com/)
    2. Select **YouTube and YouTube Music** only
    3. Choose your preferred export format
    4. Download and extract the archive

### Step 4: Sync All Data

This fetches current data from the YouTube API and enriches any Takeout-seeded records:

```bash
chronovista sync all
```

This syncs (in order): subscriptions, playlists, videos, and video metadata.

!!! note "Rate Limits"
    The YouTube Data API has a quota of 10,000 units per day. Large syncs may need to span multiple days. chronovista tracks progress and supports incremental syncs.

### Step 5: Download Transcripts

Transcripts are fetched separately because they use a different API and have their own rate limits:

```bash
chronovista sync transcripts
```

!!! warning "IP Throttling"
    YouTube may temporarily block your IP after ~40 rapid transcript requests. If this happens, wait 24 hours and retry. Consider using smaller batches with pauses between them.

### Step 6: Verify

```bash
# Check what's in your database
chronovista status

# Explore topics
chronovista topics list
chronovista topics popular
```

## Incremental Updates

After initial population, keep your data current with:

```bash
# Sync new data (skips already-synced items)
chronovista sync all

# Re-import Takeout with new export
chronovista takeout seed /path/to/new-takeout --incremental
```

## Summary

| Step | Command | Time | Notes |
|------|---------|------|-------|
| 1. Auth | `chronovista auth login` | 1 min | One-time setup |
| 2. Topics | `chronovista sync topics` | < 1 min | Fast, single API call |
| 3. Takeout | `chronovista takeout seed ...` | 5-30 min | Depends on history size |
| 4. Sync all | `chronovista sync all` | 10-60 min | Depends on library size, API quota |
| 5. Transcripts | `chronovista sync transcripts` | 30+ min | Rate-limited by YouTube |

## See Also

- [Data Sync](data-sync.md) - Detailed sync command reference
- [Google Takeout](google-takeout.md) - Full Takeout guide
- [Transcripts](transcripts.md) - Transcript management
- [CLI Overview](cli-overview.md) - All commands
