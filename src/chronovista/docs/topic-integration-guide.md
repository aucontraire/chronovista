# Topic Integration Guide

A comprehensive guide to using chronovista's topic functionality for categorizing and filtering your YouTube content.

## Overview

chronovista integrates with YouTube's topic classification system to help you organize and explore your content by categories like News & Politics, Music, Gaming, Education, and more. Topics are automatically associated with your videos and channels during sync operations.

## Getting Started

### 1. Sync Topic Categories

First, populate the topic database with YouTube's standard categories:

```bash
chronovista sync topics
# Output: ✅ Topics: 0 created, 32 updated
```

This creates a local database of all YouTube topic categories (Music, Gaming, News & Politics, etc.).

### 2. Sync Content with Topic Associations

When you sync videos and channels, topic associations are automatically created:

```bash
# Sync liked videos with automatic topic linking
chronovista sync liked
# Output: ✅ Found 10 liked videos
#         🏷️ Creating topic associations...

# Sync channel info with topic associations
chronovista sync channel
# Output: ✅ Channel synced: Your Channel
#         🏷️ Processing channel topics...
```

## Topic Commands

### List All Topics

View all available topic categories:

```bash
chronovista topics list
```

### Show Topic Details

Get detailed information about a specific topic:

```bash
chronovista topics show 25
# Shows details for "News & Politics" topic
```

### Find Content by Topic

View videos associated with a topic:

```bash
chronovista topics videos 25
# Shows all your News & Politics videos
```

View channels associated with a topic:

```bash
chronovista topics channels 10
# Shows all your Music-related channels
```

## Topic Filtering

### Filter Sync Operations

Only sync content matching specific topics:

```bash
# Only sync liked videos from News & Politics category
chronovista sync liked --topic 25

# Only sync channel if it matches the Music topic
chronovista sync channel --topic 10
```

### Filter Takeout Analysis

Apply topic filters to your Google Takeout analysis:

```bash
# Analyze takeout data grouped by topics
chronovista takeout analyze --by-topic

# Filter takeout analysis by specific topic
chronovista takeout analyze --topic 25

# Filter takeout peek by topic
chronovista takeout peek history --topic 10
```

## Common Topic Categories

Here are some frequently used YouTube topic IDs:

| ID | Category | Description |
|----|----------|-------------|
| 1  | Film & Animation | Movies, animations, film content |
| 2  | Autos & Vehicles | Car reviews, automotive content |
| 10 | Music | Songs, music videos, concerts |
| 15 | Pets & Animals | Animal videos, pet care |
| 17 | Sports | Sports highlights, games |
| 19 | Travel & Events | Travel vlogs, event coverage |
| 20 | Gaming | Video games, gaming content |
| 22 | People & Blogs | Personal vlogs, lifestyle |
| 23 | Comedy | Funny videos, comedy shows |
| 24 | Entertainment | General entertainment content |
| 25 | News & Politics | News, political commentary |
| 26 | Howto & Style | Tutorials, fashion, DIY |
| 27 | Education | Educational content, lectures |
| 28 | Science & Technology | Tech reviews, science content |

## How Topic Association Works

### Video Topics

Videos are linked to topics through their `categoryId` from the YouTube API:
- Each video has a primary topic category
- Association happens automatically during sync
- Stored as "primary" relevance type

### Channel Topics

Channels are associated with topics through YouTube's `topicDetails`:
- Channels may have multiple topic associations
- Only topics that exist in the database are linked
- Freebase topic IDs are gracefully handled (skipped if unknown)

## Error Handling

### Invalid Topic IDs

```bash
chronovista sync liked --topic 999
# Output: ❌ Invalid topic ID: 999
#         Use chronovista topics list to see available topics.
```

### No Matching Content

```bash
chronovista sync liked --topic 1
# Output: ℹ️ No videos found with topic ID: 1
#         Try a different topic or remove the --topic filter.
```

### Channel Topic Mismatch

```bash
chronovista sync channel --topic 25
# Output: ℹ️ Channel does not match topic ID: 25
#         Use chronovista sync channel without --topic to sync anyway.
```

## Best Practices

### 1. Regular Topic Sync

Update your topic categories periodically:

```bash
# Run this monthly to get any new categories
chronovista sync topics
```

### 2. Full Sync for Complete Coverage

Use full sync to ensure all content has topic associations:

```bash
chronovista sync all
# Syncs topics → channels → videos with all associations
```

### 3. Explore Before Filtering

List available topics before applying filters:

```bash
chronovista topics list
# See what categories you have content in
```

### 4. Targeted Analysis

Use topic filtering for focused analysis:

```bash
# Analyze only your educational content
chronovista takeout analyze --topic 27

# Focus on gaming content from takeout
chronovista takeout peek history --topic 20
```

## Advanced Usage

### Finding Your Content Distribution

```bash
# List topics with content counts
chronovista topics list

# Check which topics your channel covers
chronovista topics channels YOUR_TOPIC_ID
```

### Content Discovery

```bash
# Find all music videos you've liked
chronovista topics videos 10

# Discover educational channels you follow
chronovista topics channels 27
```

### Targeted Sync Workflows

```bash
# Sync only news content for focused analysis
chronovista sync liked --topic 25

# Keep entertainment content separate
chronovista sync liked --topic 24
```

## Troubleshooting

### Topics Not Showing Up

1. **Ensure topics are synced**: `chronovista sync topics`
2. **Sync content first**: `chronovista sync liked` or `chronovista sync channel`
3. **Check topic associations**: `chronovista topics videos TOPIC_ID`

### Filtering Returns No Results

1. **Verify topic ID**: `chronovista topics list`
2. **Check if you have content in that category**: `chronovista topics videos TOPIC_ID`
3. **Try without filters first**: `chronovista sync liked`

### Channel Topics Not Working

- Channel topic association depends on YouTube's API data
- Some channels may not have topic information
- Freebase topic IDs are filtered out (only standard YouTube categories are used)

## Technical Details

### Database Storage

- **Topic Categories**: Stored in `topic_categories` table
- **Video Topics**: Junction table `video_topics` with composite keys
- **Channel Topics**: Junction table `channel_topics`

### API Integration

- **Video Categories**: Extracted from `snippet.categoryId`
- **Channel Topics**: Extracted from `topicDetails.topicIds`
- **Validation**: All topic IDs validated against local database

### Type Safety

- Full mypy compliance
- Pydantic models for all topic data
- Robust error handling and validation

## Related Commands

- `chronovista topics --help` - Full topic command help
- `chronovista sync --help` - Sync command options
- `chronovista takeout --help` - Takeout analysis options

---

For more information, see the main [README.md](../../../README.md) or use `chronovista --help` for command-specific guidance.