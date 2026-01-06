# Google Takeout Data Quality Guide

**Last Updated:** 2025-12-29
**Version:** 3.0

This document explains the data quality challenges when importing YouTube data from Google Takeout, why they occur, how to diagnose them, and how to remediate them.

---

## Table of Contents

1. [Overview](#overview)
2. [Google Takeout Data Sources](#google-takeout-data-sources)
3. [Data Quality Issues](#data-quality-issues)
   - [Community Posts (Not Videos)](#1-community-posts-not-videos)
   - [Videos Missing Channel Info](#2-videos-missing-channel-info)
   - [Playlist-Only Videos](#3-playlist-only-videos)
   - [Actually Deleted/Private Videos](#4-actually-deletedprivate-videos)
4. [Critical Lessons Learned](#critical-lessons-learned)
5. [Database Indicators](#database-indicators)
6. [Diagnostic Queries](#diagnostic-queries)
7. [Remediation Scripts](#remediation-scripts)
8. [Recovery Statistics](#recovery-statistics)
9. [YouTube API Enrichment](#youtube-api-enrichment)
10. [Data Files Reference](#data-files-reference)
11. [Formalization Roadmap](#formalization-roadmap)

---

## Overview

Google Takeout provides a snapshot of your YouTube data, but different data sources contain varying levels of detail. This creates data quality challenges when building a unified database of your viewing history.

**Key Insights:**
1. The completeness of metadata depends on which Takeout file the data originated from
2. **Missing channel info does NOT mean a video is deleted** - this was a wrong assumption
3. Watch history contains non-video entries (Community Posts) that must be filtered out

### The Core Problem

| Data Source | Video ID | Video Title | Channel ID | Channel Name |
|-------------|----------|-------------|------------|--------------|
| Watch History (video, complete) | ✅ | ✅ | ✅ | ✅ |
| Watch History (video, incomplete) | ✅ | ✅ or URL | ❌ | ❌ |
| Watch History (Community Post) | ❌ | Post text | ❌ | ❌ |
| Playlist CSV | ✅ | ❌ | ❌ | ❌ |
| Subscriptions | N/A | N/A | ✅ | ✅ |

---

## Google Takeout Data Sources

### Watch History (`history/watch-history.json`)

Watch history contains **two types of entries** that must be distinguished:

#### Video Watches (title starts with "Watched")

**Complete Entry:**
```json
{
  "header": "YouTube",
  "title": "Watched Some Video Title",
  "titleUrl": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "subtitles": [{
    "name": "Channel Name",
    "url": "https://www.youtube.com/channel/UCuAXFkgsw1L7xaCfnd5JJOw"
  }],
  "time": "2025-01-15T10:30:00.000Z"
}
```

**Incomplete Entry (missing channel info):**
```json
{
  "header": "YouTube",
  "title": "Watched https://www.youtube.com/watch?v=XYZABC12345",
  "titleUrl": "https://www.youtube.com/watch?v=XYZABC12345",
  "time": "2025-01-15T10:30:00.000Z"
}
```
Note: No `subtitles` field. **This does NOT mean the video is deleted!**

#### Community Post Views (title starts with "Viewed")

```json
{
  "header": "YouTube",
  "title": "Viewed Some community post content here...",
  "time": "2025-01-15T10:30:00.000Z"
}
```
**Important:** These are NOT videos. They have no video ID and should NOT be imported into the videos table.

### Subscriptions (`subscriptions/subscriptions.csv`)

**Contains:**
- Channel ID
- Channel URL
- Channel title

**Limitation:** Only includes channels you're currently subscribed to.

### Playlists (`playlists/*.csv`)

**Contains:**
- Video ID
- Timestamp when added to playlist

**Critical Limitation:** Does NOT include video title, channel name, or channel ID.

---

## Data Quality Issues

### 1. Community Posts (Not Videos)

**What:** YouTube Community Post views mixed in with video watches.

**How to Identify:**
- Title starts with "Viewed" (not "Watched")
- No `titleUrl` field
- No video ID extractable

**Why It Happens:**
Google Takeout exports ALL YouTube activity to watch-history.json, including Community Post views.

**Impact if Not Filtered:**
- Generated fake video IDs (MD5 hashes)
- Records that can never be enriched via API
- Polluted video statistics

**Solution:** Filter out entries where title starts with "Viewed" during seeding.

**Count Found:** 1,923 Community Post records were incorrectly imported as videos.

### 2. Videos Missing Channel Info

**What:** Real videos that exist on YouTube but have no channel information in Takeout.

**How to Identify:**
- Title starts with "Watched"
- Has valid `titleUrl` with video ID
- No `subtitles` field (no channel info)

**Why It Happens:**
This is **NOT necessarily because the video is deleted**. Possible causes:
- Takeout data export timing issues
- YouTube API inconsistencies during export
- Video privacy temporarily changed during export
- Unknown Google-side data issues

**Critical Correction:** Our initial assumption that "no channel info = deleted video" was **WRONG**.

**API Verification Results:**
- 6,692 videos were marked as "deleted" based on missing channel info
- 3,302 (49%) were found to **still exist on YouTube** via API
- Only 3,390 (51%) were actually deleted/private

**Solution:**
- Do NOT auto-mark as deleted based on missing channel info
- Use YouTube API to verify actual deletion status
- Only set `deleted_flag = true` after API confirms video doesn't exist

### 3. Playlist-Only Videos

**What:** Videos added to playlists but never watched.

**How to Identify:**
- Video title is "[Placeholder] Video {video_id}"
- Channel title is "[Placeholder] Unknown Channel"
- Channel ID is a generated hash

**Why It Happens:**
Playlist CSV files only contain video IDs - no titles or channel info.

**Solution:** Enrich via YouTube API (these usually still exist).

### 4. Actually Deleted/Private Videos

**What:** Videos that genuinely no longer exist on YouTube.

**How to Identify:**
- YouTube API returns no results for the video ID
- `deleted_flag = true` (after API verification)

**Why It Happens:**
- Creator deleted the video
- Creator made video private
- YouTube removed for policy violations
- Channel terminated

**This is the only case where `deleted_flag` should be `true`.**

---

## Critical Lessons Learned

### Lesson 1: "Missing Channel Info" ≠ "Deleted Video"

**Wrong Assumption:**
> If a watch history entry has no `subtitles` field, the video must be deleted.

**Reality:**
- 49% of videos marked as "deleted" were actually still on YouTube
- Missing channel info is often just incomplete Takeout data
- Always verify via API before marking as deleted

### Lesson 2: Watch History Contains Non-Video Content

**Wrong Assumption:**
> All watch-history.json entries are video watches.

**Reality:**
- Entries starting with "Viewed" are Community Post views
- These have no video ID and must be filtered out
- Generating fake IDs for them pollutes the database

### Lesson 3: Generated IDs Are Problematic

**Problem:**
When no video ID is available, seeding generated fake MD5-based IDs.

**Why This Is Bad:**
- Can't query YouTube API with fake IDs
- Creates records that can never be verified or enriched
- Pollutes statistics and queries

**Solution:**
- Skip entries without extractable video IDs entirely
- Or store in a separate table for non-video activity

---

## Database Indicators

### Video Table Flags

| Field | Value | Meaning |
|-------|-------|---------|
| `deleted_flag` | `true` | **API-verified** as deleted/private |
| `deleted_flag` | `false` | Video exists OR not yet verified |
| `title` | Starts with `http` | Title couldn't be retrieved |
| `title` | `[Placeholder] Video {id}` | From playlist, never watched |
| `title` | Starts with `Viewed` | **ERROR:** Community Post incorrectly imported |

### Distinguishing Real vs Generated IDs

**Real YouTube Video IDs:**
- 11 characters
- Base64-like alphabet: `a-zA-Z0-9_-`
- Contains uppercase letters, underscores, or dashes
- Example: `dQw4w9WgXcQ`, `hwRMkJRM-G8`

**Generated Video IDs (SHOULD NOT EXIST):**
- 11 characters
- Hex characters only: `0-9a-f`
- Example: `3d4343a1b1a`

**Detection Query:**
```sql
-- Real YouTube ID
video_id ~ '[A-Z_-]'

-- Generated/fake ID (indicates a bug)
video_id !~ '[A-Z_-]'
```

---

## Diagnostic Queries

### Quick Health Check

```sql
-- Data Quality Summary
SELECT 'Total Videos' as metric, COUNT(*)::text as count FROM videos
UNION ALL
SELECT 'Total Channels', COUNT(*)::text FROM channels
UNION ALL
SELECT 'Videos with REAL IDs', COUNT(*)::text FROM videos WHERE video_id ~ '[A-Z_-]'
UNION ALL
SELECT 'Videos with GENERATED IDs (ERROR)', COUNT(*)::text FROM videos WHERE video_id !~ '[A-Z_-]'
UNION ALL
SELECT 'Videos API-verified deleted', COUNT(*)::text FROM videos WHERE deleted_flag = true
UNION ALL
SELECT 'Placeholder Channels', COUNT(*)::text FROM channels
WHERE title LIKE '[Placeholder]%' OR title LIKE '[Unknown Channel]%';
```

### Find Community Posts (Should Not Exist)

```sql
-- These are errors - Community Posts incorrectly imported as videos
SELECT video_id, LEFT(title, 80) as title_preview
FROM videos
WHERE title LIKE 'Viewed %'
LIMIT 20;
```

### API Enrichment Candidates

```sql
-- Videos that can be enriched via YouTube API
SELECT
    'HIGH: Real IDs, not yet verified' as priority,
    COUNT(*) as count
FROM videos v
JOIN channels c ON v.channel_id = c.channel_id
WHERE v.video_id ~ '[A-Z_-]'
  AND (c.title LIKE '[Placeholder]%' OR c.title LIKE '[Unknown Channel]%')
  AND v.deleted_flag = false;
```

---

## Remediation Scripts

### 1. Recover from Historical Takeouts

**Scripts:**
- `scripts/utilities/recover_deleted_videos.py`
- `scripts/utilities/recover_placeholder_channels.py`

These search older Takeout snapshots for metadata.

### 2. YouTube API Enrichment

**Script:** `scripts/utilities/enrich_via_youtube_api.py`

```bash
# Enrich videos likely to exist (recommended first)
python scripts/utilities/enrich_via_youtube_api.py --priority high

# Enrich all videos including "deleted" (verifies actual status)
python scripts/utilities/enrich_via_youtube_api.py --priority all
```

### 3. Cleanup Community Posts (Needed)

```sql
-- Delete incorrectly imported Community Posts
DELETE FROM videos WHERE video_id !~ '[A-Z_-]';
```

---

## Recovery Statistics

### After Full Enrichment Pipeline

| Stage | Videos | Notes |
|-------|--------|-------|
| Initial seeding | 44,319 | Raw import from Takeout |
| Community Posts (error) | -1,923 | Should not have been imported |
| Actually deleted (API verified) | 3,390 | Confirmed by YouTube API |
| Videos with real metadata | 39,063 | 88% of valid videos |

### API Enrichment Results

| Priority | Videos Checked | Found on YouTube | Not Found | Recovery Rate |
|----------|----------------|------------------|-----------|---------------|
| HIGH (non-deleted) | 958 | 958 | 0 | 100% |
| ALL (including "deleted") | 6,692 | 3,302 | 3,390 | 49% |
| **Total** | **7,650** | **4,260** | **3,390** | **56%** |

**Key Finding:** 49% of videos we assumed were deleted were actually still on YouTube!

---

## YouTube API Enrichment

### API Quota

- **Free tier:** 10,000 units/day
- **videos.list:** 1 unit per request (up to 50 videos batched)
- **Our usage:** ~154 units for full enrichment (1.5% of daily quota)

### Recommended Workflow

1. **Filter Community Posts during seeding** (prevents fake IDs)
2. **Don't auto-mark as deleted** (let API verify)
3. **Run API enrichment** to get real metadata and verify deletion status
4. **Only then set deleted_flag = true** for videos API can't find

---

## Data Files Reference

| File | Description |
|------|-------------|
| `data/recovered_deleted_videos.json` | Videos recovered from historical Takeouts |
| `data/recovered_placeholder_channels.json` | Playlist videos enriched from watch history |
| `data/api_enrichment_report.json` | Results of YouTube API enrichment |

---

## Formalization Roadmap

### Seeding Logic Fixes Needed

1. **Filter Community Posts:**
   - Skip entries where `title.startswith("Viewed")`
   - These are not videos

2. **Don't Generate Fake IDs:**
   - If no video ID extractable, skip the entry
   - Don't create records with MD5 hash IDs

3. **Don't Auto-Mark Deleted:**
   - Remove logic that sets `deleted_flag = true` based on missing channel info
   - Only set after API verification

### Target Architecture

```
Seeding:
  - Only import entries with real video IDs
  - Set deleted_flag = false initially
  - Create placeholder channels as needed

Enrichment (post-seeding):
  - Query YouTube API for videos with placeholders
  - Update with real metadata
  - Set deleted_flag = true ONLY if API returns nothing
```
