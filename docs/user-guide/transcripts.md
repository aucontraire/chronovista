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
# Sync transcripts for all videos without transcripts
chronovista sync transcripts

# Preview what would be synced (dry run)
chronovista sync transcripts --dry-run

# Sync specific video(s)
chronovista sync transcripts --video-id VIDEO_ID
chronovista sync transcripts --video-id ID1 --video-id ID2

# Sync with language preference
chronovista sync transcripts --language es --language en

# Limit number of videos processed
chronovista sync transcripts --limit 50

# Force re-download existing transcripts
chronovista sync transcripts --force

# Download specific transcript (legacy command)
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

## Timestamp-Based Queries (v0.11.0+)

Query transcript segments by timestamp to find what was said at specific moments in a video.

### Get Segment at Timestamp

```bash
# Get the segment containing timestamp 5:00
chronovista transcript segment VIDEO_ID 5:00

# Output formats: human (default), json, srt
chronovista transcript segment VIDEO_ID 5:00 --format json

# Specify language (default: en)
chronovista transcript segment VIDEO_ID 5:00 --language es
```

### Get Context Around Timestamp

```bash
# Get segments within 30 seconds of timestamp (default)
chronovista transcript context VIDEO_ID 5:00

# Custom window size (60 seconds before and after)
chronovista transcript context VIDEO_ID 5:00 --window 60
```

### Get Segments in Time Range

```bash
# Get all segments from 1:00 to 5:00
chronovista transcript range VIDEO_ID 1:00 5:00

# Export as SRT subtitle format
chronovista transcript range VIDEO_ID 0:00 10:00 --format srt

# Export as JSON
chronovista transcript range VIDEO_ID 0:00 10:00 --format json
```

### Timestamp Format Support

The CLI accepts flexible timestamp formats:

| Format | Example | Seconds |
|--------|---------|---------|
| `MM:SS` | `5:30` | 330 |
| `HH:MM:SS` | `1:05:30` | 3930 |
| `MM:SS.ms` | `5:30.5` | 330.5 |
| Seconds | `330` | 330 |

### Understanding Segment Data

YouTube transcripts are stored as small overlapping segments (typically 2-5 seconds each). The `>>` marker in segment text indicates speaker changes:

```
#152 [4:55-5:00] march and see what's going to be popping
#153 [4:57-5:02] up on walls, on posters, you know,
#154 [5:00-5:03] across social media and all that. Um
#155 [5:02-5:04] >> megaphones.
```

Note: YouTube's UI combines multiple segments for display, but chronovista preserves the original segment boundaries for precise timestamp queries.

## Inline Transcript Corrections (v0.38.0)

Edit transcript segments directly in the web UI to fix ASR errors, spelling mistakes, and formatting issues.

### Editing a Segment

1. Hover over any transcript segment to reveal the **Edit** button (pencil icon)
2. Click Edit or press Enter/Space to enter edit mode
3. Modify the text in the textarea
4. Select the correction type from the dropdown:
   - **asr_error** (default) — Automatic speech recognition mistake
   - **spelling** — Spelling or typo correction
   - **context_correction** — Contextual word replacement
   - **profanity_fix** — Profanity or inappropriate content fix
   - **formatting** — Punctuation, capitalization, or formatting change
5. Click **Save** or press Enter to submit

The correction is applied instantly (optimistic update) and confirmed by the server. If the server rejects it, the text rolls back automatically.

### Validation

- Empty text is rejected: "Correction text cannot be empty."
- Identical text is rejected: "Correction is identical to the current text."
- Validation runs on Save, not on every keystroke

### Reverting a Correction

When a segment has been corrected, a **Revert** button appears:

1. Click Revert to show the confirmation: "Revert to previous version?"
2. Click **Confirm** to revert, or **Cancel** to dismiss
3. Revert goes back one version — if multiple corrections exist, it restores the previous correction's text (not the original)

### Viewing Correction History

When a segment has been corrected one or more times, a **History** button appears:

1. Click History to expand the correction history panel below the segment
2. Each entry shows: correction type, date, original text, corrected text, version number, and optional note
3. Click **Load more** to see older entries
4. Press **Escape** to close the panel

### Correction Badges

- **Segment badge**: A "Corrected" badge appears on corrected segments. Hover to see correction count and timestamp.
- **Video badge**: A "Corrections" badge appears on video cards when any segment in that video's transcript has been corrected.
- **Transcript panel**: "This transcript has corrections" indicator appears in the panel header.

### Keyboard Navigation

The entire correction workflow is keyboard-accessible:

- **Tab** to reach Edit, Revert, and History buttons
- **Enter/Space** to activate buttons
- **Tab** within edit mode: textarea → correction type → Save → Cancel
- **Escape** to cancel any action and return focus to the originating button

### Limitations

- Only one segment can be edited at a time
- Revert goes back one version only (not to a specific earlier version)
- The Full Text view does not reflect corrections (it uses the original transcript text)
- For batch corrections across multiple segments, use the CLI — see [Batch Transcript Corrections (CLI)](#batch-transcript-corrections-cli-v0390) below

## Batch Transcript Corrections (CLI) (v0.39.0)

The `chronovista corrections` CLI commands enable bulk correction operations across your entire transcript library. While the inline web UI edits one segment at a time, the CLI tools can find and replace patterns across thousands of segments in a single command.

### Quick Start

```bash
# Find a recurring ASR error and preview what would change
chronovista corrections find-replace --pattern "Chsky" --replacement "Chomsky" --dry-run

# Apply the correction (with confirmation prompt)
chronovista corrections find-replace --pattern "Chsky" --replacement "Chomsky"

# Rebuild full transcript text to reflect corrections
chronovista corrections rebuild-text
```

### Available Commands

| Command | Description |
|---------|-------------|
| `find-replace` | Batch find-and-replace text patterns across transcript segments |
| `rebuild-text` | Regenerate full transcript text from corrected segments |
| `export` | Export correction audit records as CSV or JSON |
| `stats` | Display aggregate correction statistics |
| `patterns` | Discover recurring correction patterns with suggested fix commands |
| `batch-revert` | Batch revert corrections matching a pattern |

### Pattern Matching

The `find-replace` and `batch-revert` commands support several matching modes:

- **Substring match** (default): `--pattern "Chsky"` matches any segment containing "Chsky"
- **Case-insensitive**: `--pattern "chsky" --case-insensitive` matches "Chsky", "CHSKY", etc.
- **Regex**: `--pattern "finkel(state|stein)" --regex` matches Python regular expressions

Pattern matching is performed database-side using SQL operators (`LIKE`, `ILIKE`, `~`, `~*`), so scans are efficient even for large transcript libraries (500,000+ segments).

### Safety Features

All batch operations include safety mechanisms to prevent accidental changes:

- **Dry-run mode**: Add `--dry-run` to any write command to preview changes without modifying the database
- **Confirmation prompt**: Write operations display the scope ("This will correct N segments across M videos. Proceed? [y/N]") before executing
- **Transaction batching**: Segments are processed in configurable batches (default: 100). If a batch fails, only that batch is rolled back — previously committed batches are preserved
- **Idempotency**: Running the same find-replace twice is safe — the second run finds zero matches and reports "0 corrections applied"
- **Full audit trail**: Every correction creates a `transcript_corrections` audit record, just like inline edits

### Rebuilding Full Text

After applying corrections to individual segments, the `video_transcripts.transcript_text` column may be out of date. The `rebuild-text` command regenerates it by concatenating each segment's effective text (corrected if available, otherwise original), ordered by timestamp and separated by spaces.

```bash
# Preview which transcripts would change
chronovista corrections rebuild-text --dry-run

# Rebuild all corrected transcripts
chronovista corrections rebuild-text
```

### Discovering Patterns

The `patterns` command analyzes your existing corrections to find recurring error patterns. Each result includes a copy-paste command to fix remaining instances:

```bash
chronovista corrections patterns
```

This is useful for discovering ASR errors that you've corrected one at a time via the web UI and want to batch-fix across the rest of your library.

### Exporting and Statistics

Back up your correction work or analyze patterns:

```bash
# Export all corrections as CSV
chronovista corrections export --format csv --output corrections.csv

# View aggregate statistics
chronovista corrections stats
```

For full command options, see the [CLI Overview](cli-overview.md#corrections-commands).

### Limitations and Edge Cases

When running bulk corrections, be aware of these known limitations:

**Cross-segment matches (issue [#71](https://github.com/chronovista/chronovista/issues/71)):**
YouTube's auto-generated transcripts split text into small overlapping segments (typically 2–5 seconds). If a misspelling spans two adjacent segments (e.g., "Claudia" at the end of one segment and "Shembun" at the start of the next), `find-replace` will not match it because each segment is searched independently. You must correct such cases manually via the inline web UI.

**Regex pattern safety:**
Broad regex patterns can match unintended text. For example, `--pattern "Sham\w*" --regex` will match "Shambo", "Shamado", but also "Shame", "Sham", etc. Always run with `--dry-run` first and review every match before applying. Consider adding more specificity to your pattern (e.g., `Claudia Sham\w+` instead of just `Sham\w*`).

**Substring mode vs. word boundaries:**
The default substring mode uses SQL `LIKE '%pattern%'`, which matches anywhere inside a word. For example, `--pattern "art"` matches "art", "start", "party", etc. If you need exact word matching, use `--regex` with word boundaries: `--pattern '\bart\b' --regex`.

**Order of operations after corrections:**
After running `find-replace`, you should:

1. Run `rebuild-text` to regenerate the full transcript text column
2. Then run `entities scan` to pick up new entity mentions from corrected text

The entity scan reads segment-level effective text (corrected_text if available), but `rebuild-text` keeps the full-text search index and the "Full Text" view in the web UI in sync.

**ASR alias registration (v0.41.0+):**
When `find-replace` corrects text that matches a known entity name, the original misspelling form is automatically registered as an `asr_error` alias on that entity. In regex mode, each distinct matched form (e.g., "Shambo", "Shamado", "Shambom") is registered as a separate alias. This means a subsequent `entities scan` will find more mentions because the alias list has grown. This is the intended closed-loop pipeline: corrections → aliases → expanded mention coverage.

## Entity Mention Scanning (v0.41.0+)

After correcting transcripts, you can scan your library to discover where named entities are mentioned. The scanner matches entity names and all their known aliases (including ASR error aliases) against transcript segments using word-boundary regex.

### Quick Start

```bash
# Preview what the scanner would find
chronovista entities scan --dry-run

# Run the scan
chronovista entities scan

# View statistics
chronovista entities stats
```

### Recommended Workflow

The most effective workflow combines corrections with scanning:

```bash
# 1. Fix a recurring ASR error across all transcripts
chronovista corrections find-replace \
  --pattern 'Claudia Sham\w+' \
  --replacement 'Claudia Sheinbaum' \
  --regex --dry-run

# Review the dry-run output, then apply:
chronovista corrections find-replace \
  --pattern 'Claudia Sham\w+' \
  --replacement 'Claudia Sheinbaum' \
  --regex

# 2. Rebuild full transcript text
chronovista corrections rebuild-text

# 3. Scan for entity mentions (new aliases were auto-created in step 1)
chronovista entities scan --full

# 4. Check results
chronovista entities stats
chronovista entities list --has-mentions --sort mentions
```

### Scan Modes

| Mode | Flag | Behavior |
|------|------|----------|
| Incremental (default) | _(none)_ | Skips segments with existing mentions |
| Full rescan | `--full` | Deletes existing `rule_match` mentions, then rescans |
| New entities only | `--new-entities-only` | Only scans entities with zero existing mentions |

### Limitations

- **Segment-level only**: The scanner currently matches against transcript segments only — not video titles or descriptions (planned in issue #73)
- **Short aliases skipped**: Aliases shorter than 3 characters are excluded to avoid excessive false positives
- **Word boundaries**: Uses `\b` (word boundary) matching, so "Aaron" will not match "Aaronson" — this is by design to prevent false positives
- **Cross-segment names**: A name split across two adjacent segments will not be detected

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

**Timestamp Data (v0.10.0+):**

| Field | Description |
|-------|-------------|
| `raw_transcript_data` | Complete API response with timestamps (JSONB) |
| `has_timestamps` | Whether timing data is available |
| `segment_count` | Number of transcript segments |
| `total_duration` | Total transcript duration in seconds |
| `source` | Transcript source (youtube_transcript_api, manual_upload, etc.) |

The `raw_transcript_data` field contains the complete response from youtube-transcript-api, including:

```json
{
  "video_id": "abc123",
  "language_code": "en",
  "language_name": "English",
  "snippets": [
    {"text": "Hello world", "start": 0.0, "duration": 2.5},
    {"text": "This is a transcript", "start": 2.5, "duration": 3.0}
  ],
  "metadata": {
    "is_generated": true,
    "transcript_count": 150
  }
}
```

### Querying by Metadata

Filter transcripts by their characteristics:

```bash
# Find long transcripts (future CLI feature)
# Videos with >100 segments or >10 minutes duration

# Via SQL for advanced queries
SELECT video_id, segment_count, total_duration
FROM video_transcripts
WHERE has_timestamps = true
  AND segment_count > 100
ORDER BY total_duration DESC;
```

### Storage Considerations

For large libraries:

- Average transcript: 5-20 KB (text only)
- With raw_transcript_data: 20-100 KB per transcript
- 10,000 videos: ~200-500 MB
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
- **Deleted or unavailable videos** - Transcripts cannot be downloaded for videos that no longer exist on YouTube. However, you can recover the video's metadata (title, description, tags, etc.) from the Wayback Machine using `chronovista recover video --video-id VIDEO_ID`. Note that transcript text itself is not recoverable from the Wayback Machine.

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
