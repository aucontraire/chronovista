# Transcripts

Guide to managing video transcripts and multi-language support.

## Overview

chronovista provides intelligent transcript management with:

- Multi-language support with user preferences
- Quality-aware downloading (CC vs auto-generated)
- Rate limiting to respect API limits
- Fallback strategies for reliability

## Quick Start

```bash
# Sync transcripts for your videos
chronovista sync transcripts

# Download specific transcript
chronovista transcripts download VIDEO_ID --language en-US

# List available languages
chronovista transcripts list VIDEO_ID
```

## Language Preferences

### Setting Preferences

Configure which languages to download automatically:

```bash
# Set language preferences
chronovista languages set --fluent en-US,es-ES --learning it-IT --curious fr-FR

# View current settings
chronovista languages show
```

### Preference Types

| Type | Description | Auto-Download |
|------|-------------|---------------|
| `fluent` | Languages you speak fluently | Yes |
| `learning` | Languages you're actively learning | Yes |
| `curious` | Interesting but not priority | No |
| `exclude` | Languages to skip | Never |

### Configuration File

Create `~/.chronovista/language_config.yaml`:

```yaml
language_preferences:
  fluent:
    - en-US
    - es-ES
  learning:
    - it-IT
    - pt-BR
  curious:
    - fr-FR
  exclude:
    - zh-CN

auto_download_rules:
  fluent_languages: true
  learning_languages: true
  curious_languages: false
  max_transcripts_per_video: 3
  short_video_threshold: 300  # seconds
```

## Downloading Transcripts

### Single Video

```bash
# Download default language
chronovista transcripts download VIDEO_ID

# Specific language
chronovista transcripts download VIDEO_ID --language it-IT

# Prioritize closed captions
chronovista transcripts download VIDEO_ID --priority-cc
```

### Batch Download

```bash
# All videos from a channel
chronovista transcripts batch-download --channel CHANNEL_ID

# Only learning languages
chronovista transcripts batch-download --learning-languages

# With limits
chronovista transcripts batch-download --limit 100 --delay 10
```

### Download Options

| Option | Description |
|--------|-------------|
| `--language <code>` | BCP-47 language code |
| `--priority-cc` | Prefer closed captions |
| `--priority-manual` | Prefer manual captions |
| `--include-auto` | Include auto-generated |

## Transcript Sources

### Three-Tier Fallback

chronovista uses multiple sources for reliability:

1. **youtube-transcript-api** (Primary)
   - Web scraping approach
   - No quota limits
   - Subject to IP-based rate limiting

2. **YouTube Data API v3** (Secondary)
   - Official Google API
   - Quota-based (200 units per download)
   - Only works for owned videos or with permissions

3. **Fallback** (Development)
   - Prevents script failures
   - Used for testing

### Quality Indicators

| Indicator | Description | Quality |
|-----------|-------------|---------|
| `is_cc` | Closed captions | High |
| `manual` | Manually created | High |
| `auto` | Auto-generated | Medium |
| `translated` | Auto-translated | Low |

## Rate Limiting

### youtube-transcript-api Limits

```
Max requests/hour: 50-100
Delay between requests: 5 seconds
Daily limit: 300-500 requests
```

### Signs of Rate Limiting

- `RequestBlocked` exceptions
- `IpBlocked` exceptions
- Videos returning "not found" unexpectedly

### Mitigation Strategies

```bash
# Add delays between requests
chronovista transcripts batch-download --delay 10

# Use smaller batches
chronovista transcripts batch-download --limit 50

# Monitor and pause
chronovista transcripts batch-download --progress
```

### Proxy Configuration

For high-volume usage, configure proxy:

```python
from youtube_transcript_api.proxies import WebshareProxyConfig

proxy_config = WebshareProxyConfig(
    proxy_username="your-username",
    proxy_password="your-password",
    filter_ip_locations=["us", "ca"]
)
```

## Viewing Transcripts

### List Available

```bash
# Show available languages
chronovista transcripts list VIDEO_ID

# With quality information
chronovista transcripts list VIDEO_ID --show-quality
```

### View Transcript

```bash
# Display transcript text
chronovista transcripts show VIDEO_ID --language en-US

# Export to file
chronovista transcripts show VIDEO_ID > transcript.txt
```

## Filtering and Search

### Filter by Properties

```bash
# Videos with transcripts
chronovista videos filter --has-transcripts

# Specific language transcripts
chronovista transcripts filter --language it-IT

# High-quality only
chronovista transcripts filter --quality manual
```

### Search in Transcripts

```bash
# Search across all transcripts
chronovista transcripts search "machine learning"

# Filter by language
chronovista transcripts search "tutorial" --language en-US
```

## Storage and Database

### Schema

Transcripts are stored with rich metadata:

| Field | Description |
|-------|-------------|
| `video_id` | Associated video |
| `language_code` | BCP-47 language code |
| `transcript_text` | Full transcript content |
| `transcript_type` | AUTO, MANUAL, TRANSLATED |
| `download_reason` | Why it was downloaded |
| `confidence_score` | Quality confidence (0-1) |
| `is_cc` | Closed captions flag |
| `is_auto_synced` | Auto-generated flag |
| `track_kind` | standard, ASR, forced |
| `downloaded_at` | Download timestamp |

### Storage Considerations

For large libraries:

- Average transcript: 5-20 KB
- 10,000 videos: ~100-200 MB
- With multiple languages: 2-3x storage

## Export

### Export Transcripts

```bash
# CSV export
chronovista export transcripts --format csv --output transcripts.csv

# JSON export
chronovista export transcripts --format json

# With video metadata
chronovista export transcripts --include-video-metadata

# Filter by language
chronovista export transcripts --language en-US
```

## API Quotas

### YouTube Data API

| Operation | Quota Units |
|-----------|-------------|
| captions.list | 50 |
| captions.download | 200 |
| Daily limit | 10,000 |

With 200 units per download, you can download ~50 transcripts/day using the official API.

### Monitoring Quota

```bash
chronovista status --quota
```

## Troubleshooting

### No Transcripts Available

Some videos don't have transcripts:

- Live streams may not have captions
- Very new videos may not be processed yet
- Creator disabled captions
- Regional restrictions

### Rate Limited

If you hit rate limits:

```bash
# Wait and retry
sleep 3600  # 1 hour
chronovista transcripts batch-download --incremental
```

### Wrong Language Downloaded

Check language preferences:

```bash
chronovista languages show
```

Verify language code is correct (BCP-47 format).

### Quality Issues

Auto-generated transcripts may have errors. Prefer manual captions:

```bash
chronovista transcripts download VIDEO_ID --priority-manual
```

## Best Practices

### Initial Download

```bash
# 1. Set language preferences
chronovista languages set --fluent en-US --learning es-ES

# 2. Start with small batch
chronovista transcripts batch-download --limit 50 --delay 10

# 3. Monitor for issues
chronovista status
```

### Ongoing Maintenance

```bash
# Incremental updates
chronovista sync transcripts --incremental

# Periodic full sync
chronovista sync transcripts --full --delay 10
```

### Production Usage

```python
import time
import random

for video_id in video_ids:
    try:
        transcript = await transcript_service.get_transcript(video_id)
        # Random delay 5-10 seconds
        await asyncio.sleep(random.uniform(5, 10))
    except (RequestBlocked, IpBlocked):
        # Exponential backoff
        await asyncio.sleep(60)
```

## See Also

- [Data Synchronization](data-sync.md) - Sync operations
- [Configuration](../getting-started/configuration.md) - Rate limit settings
- [API Reference](../api/services/transcript.md) - Transcript service API
