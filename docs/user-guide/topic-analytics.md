# Topic Analytics

Comprehensive guide to chronovista's topic analytics and intelligence features.

## Overview

chronovista integrates with YouTube's topic classification system to help you organize and explore your content by categories like News & Politics, Music, Gaming, Education, and more. The system provides 17 specialized CLI commands for content discovery, trend analysis, and engagement scoring.

## Getting Started

### Sync Topic Categories

First, populate the database with YouTube's standard categories:

```bash
chronovista sync topics
```

This creates 32 topic categories in your local database.

### Sync Content with Topics

When syncing videos and channels, topic associations are automatically created:

```bash
chronovista sync all
```

## Core Commands

### List Topics

View all available topic categories:

```bash
chronovista topics list
```

### Show Topic Details

Get detailed information about a specific topic:

```bash
chronovista topics show 25  # News & Politics
```

### Find Content by Topic

```bash
# Videos in a topic
chronovista topics videos 25

# Channels in a topic
chronovista topics channels 10  # Music
```

## Popular Topics

Rank topics by content volume:

```bash
# By video count (default)
chronovista topics popular

# By channel count
chronovista topics popular --metric channels

# Combined ranking
chronovista topics popular --metric combined

# Limit results
chronovista topics popular --limit 5
```

## Similarity Analysis

Find topics with similar content patterns using cosine similarity:

```bash
# Find topics similar to Music
chronovista topics similar 10

# Adjust similarity threshold
chronovista topics similar 10 --min-similarity 0.3

# Limit results
chronovista topics similar 10 --limit 5
```

### How Similarity Works

The algorithm:

1. **Content Pattern Analysis** - Calculates video-to-channel ratios
2. **Volume Normalization** - Considers total content volume
3. **Cosine Similarity** - Measures similarity using dot product
4. **Weighted Scoring** - Combines volume (30%) and ratio (70%) similarity

## Visual Analytics

### Topic Charts

Display ASCII bar charts of topic popularity:

```bash
# Default chart (videos)
chronovista topics chart

# By channels
chronovista topics chart --metric channels

# Combined metric
chronovista topics chart --metric combined

# Customize display
chronovista topics chart --limit 15 --width 50
```

Example output:
```
Topic Popularity Chart (Videos)

Music            ######################## 847
Gaming           ####################     623
Entertainment    ################         456
Education        ############             289
News & Politics  ##########               234
```

### Relationship Trees

Visualize topic relationships hierarchically:

```bash
# Basic tree
chronovista topics tree 25

# Customize depth and confidence
chronovista topics tree 25 --max-depth 3 --min-confidence 0.2

# Hide statistics
chronovista topics tree 25 --no-stats
```

Example output:
```
News & Politics (25)
|-- Related Topics
|   |-- Nonprofits & Activism (29) [confidence: 0.65]
|   |-- Education (27) [confidence: 0.43]
|   +-- People & Blogs (22) [confidence: 0.31]
+-- Statistics: 156 videos, 23 channels
```

## Interactive Exploration

Launch an interactive topic exploration session:

```bash
chronovista topics explore
```

Features:

- **Multi-phase workflow**: Topic selection, Analytics, Action selection
- **Progress indicators**: Visual feedback during analysis
- **Rich formatting**: Professional tables and panels
- **Guided experience**: Clear instructions at each step

Options:

| Option | Description |
|--------|-------------|
| `--auto-advance` | Demo mode with auto-navigation |
| `--no-analytics` | Skip analytics for faster browsing |

## Trend Analysis

Track topic popularity over time:

```bash
# Monthly trends (default)
chronovista topics trends

# Weekly trends
chronovista topics trends --period weekly

# Custom time range
chronovista topics trends --months-back 6

# Filter by direction
chronovista topics trends --direction growing
chronovista topics trends --direction declining
chronovista topics trends --direction stable
```

Output includes:

- Time periods analyzed
- Growth rates compared to previous periods
- Trend direction indicators
- Visual formatting with symbols

## Personalized Insights

Get AI-powered recommendations based on your viewing patterns:

```bash
# Default insights
chronovista topics insights

# For specific user
chronovista topics insights --user-id "your-channel-id"

# Limit recommendations
chronovista topics insights --limit 10
```

Insight categories:

- **Emerging Interests**: Newly discovered topics with growth potential
- **Dominant Interests**: Your primary topic preferences
- **Underexplored Topics**: Suggested areas for exploration
- **Similar Recommendations**: Topics matching current interests

## Graph Visualization

Export topic relationship data for external visualization tools:

```bash
# DOT format (for Graphviz)
chronovista topics graph --format dot

# JSON format (for D3.js, vis.js)
chronovista topics graph --format json

# Customize and save
chronovista topics graph --format json --output network.json --min-confidence 0.3
```

### Using DOT Output

```bash
# Generate PNG with Graphviz
dot -Tpng topic_graph.dot -o topic_network.png

# Generate SVG
dot -Tsvg topic_graph.dot -o topic_network.svg
```

### Using JSON Output

JSON output is compatible with:

- [D3.js](https://d3js.org/) force-directed graphs
- [vis.js](https://visjs.org/) network visualization
- [Cytoscape](https://cytoscape.org/) graph analysis

## Heatmap Data

Generate temporal activity data for heatmap visualizations:

```bash
# Monthly activity heatmap
chronovista topics heatmap

# Weekly activity
chronovista topics heatmap --period weekly

# Custom time range
chronovista topics heatmap --period daily --months-back 3

# Save to file
chronovista topics heatmap --output activity_data.json
```

Output structure:
```json
{
  "periods": ["2024-01", "2024-02", "2024-03"],
  "topics": {
    "Music": [120, 145, 167],
    "Gaming": [89, 94, 112]
  },
  "metadata": {
    "period_type": "monthly",
    "total_activity": 885
  }
}
```

## Engagement Analytics

Analyze topic performance based on likes, views, and comments:

```bash
# Overall engagement
chronovista topics engagement

# Specific topic
chronovista topics engagement --topic-id "/m/04rlf"

# Sort by different metrics
chronovista topics engagement --sort-by avg_likes --limit 15
```

### Engagement Scoring

The weighted scoring system:

| Metric | Weight | Calculation |
|--------|--------|-------------|
| Views | 30% | min(avg_views / 10000, 100) |
| Likes | 40% | min(avg_likes / 100, 100) |
| Comments | 30% | min(avg_comments / 10, 100) |

### Engagement Tiers

| Tier | Score Range | Description |
|------|-------------|-------------|
| High | >= 70 | Excellent audience interaction |
| Medium | 40-69 | Good engagement levels |
| Low | < 40 | Room for improvement |

## Channel Engagement

Analyze how channels perform within specific topics:

```bash
# Channel performance for Music topic
chronovista topics channel-engagement "/m/04rlf"

# Top performers only
chronovista topics channel-engagement "/m/04rlf" --limit 5
```

Analysis includes:

- Channel rankings by total views
- Engagement rates per channel
- Comparative performance analysis

## Discovery Patterns

Understand how users discover topics:

```bash
# All discovery patterns
chronovista topics discovery

# Filter by method
chronovista topics discovery --method liked_content

# With minimum interactions
chronovista topics discovery --min-interactions 5
```

Discovery methods analyzed:

- `liked_content` - Topics discovered through likes
- `watched_complete` - Topics from fully watched videos
- `watched_partial` - Topics from partially watched
- `browsed` - Topics from casual browsing

## Common Topic IDs

| ID | Category |
|----|----------|
| 1 | Film & Animation |
| 2 | Autos & Vehicles |
| 10 | Music |
| 15 | Pets & Animals |
| 17 | Sports |
| 19 | Travel & Events |
| 20 | Gaming |
| 22 | People & Blogs |
| 23 | Comedy |
| 24 | Entertainment |
| 25 | News & Politics |
| 26 | Howto & Style |
| 27 | Education |
| 28 | Science & Technology |

## Best Practices

### Initial Setup

```bash
# 1. Sync topics first
chronovista sync topics

# 2. Sync content
chronovista sync all

# 3. Explore
chronovista topics chart
```

### Regular Analysis

```bash
# Weekly trend check
chronovista topics trends --period weekly

# Monthly insights
chronovista topics insights
```

### Deep Dives

```bash
# Find your main topic
chronovista topics popular --limit 1

# Explore relationships
chronovista topics tree 10 --max-depth 3

# Find similar content
chronovista topics similar 10
```

## See Also

- [CLI Overview](cli-overview.md) - All commands
- [Data Synchronization](data-sync.md) - Syncing topic data
- [Google Takeout](google-takeout.md) - Historical analysis
