# CLI Workflows

Common command-line workflows for chronovista, with the most-used command
groups and end-to-end recipes. For the complete, auto-generated list of every
command and option, see the [CLI reference](../reference/cli.md).

## Command Structure

```
chronovista [OPTIONS] COMMAND [ARGS]...
```

## Global Options

| Option | Description |
|--------|-------------|
| `--version` | Show version and exit |
| `--help` | Show help and exit |
| `--verbose` | Enable verbose output |

## Command Groups

chronovista organizes its commands into these groups: `auth`, `sync`, `topics`,
`categories`, `tags`, `playlist`, `enrich`, `takeout`, `languages`, `recover`,
`entities`, `corrections`, and `api`.

The complete, always-current list of every command, argument, and option is
generated from the Typer application — see the
**[CLI reference](../reference/cli.md)**, or run `chronovista <group> --help`.
The workflows below show how these commands fit together for common tasks.

## Common Workflows

### Basic Workflow

```bash
# 1. Authenticate
chronovista auth login

# 2. Sync topics first
chronovista sync topics

# 3. Full sync
chronovista sync all

# 4. Explore your data
chronovista topics popular
chronovista topics chart --metric combined
```

### Takeout Analysis

```bash
# Preview Takeout data
chronovista takeout peek playlists --path /path/to/takeout

# Seed database
chronovista takeout seed /path/to/takeout --progress

# Analyze patterns
chronovista takeout analyze --path /path/to/takeout
```

### Topic Deep Dive

```bash
# Find popular topics
chronovista topics popular --limit 5

# Explore relationships
chronovista topics similar 10 --min-similarity 0.3
chronovista topics tree 10 --max-depth 3

# Export for visualization
chronovista topics graph --format json --output topics.json
```

### Category Exploration

```bash
# List all categories with video counts
chronovista categories list

# Show only assignable categories
chronovista categories list --assignable-only

# View category details (by name or ID)
chronovista categories show Comedy
chronovista categories show 23

# Browse videos in a category
chronovista categories videos Music --limit 50
```

### Tag Exploration

```bash
# List most popular tags
chronovista tags list --limit 20

# View tag details (note: use --tag for tags starting with -)
chronovista tags show --tag "music"
chronovista tags show --tag "-ALFIE"

# Find videos with specific tag
chronovista tags videos --tag "gaming" --limit 30

# Search for tags matching a pattern
chronovista tags search --pattern "python"

# View tag statistics
chronovista tags stats

# View all tags for a specific video
chronovista tags by-video --id "dQw4w9WgXcQ"
chronovista tags by-video --id "-2kc5xfeQEs"  # Video ID starting with -
```

### Tag Normalization

```bash
# Preview normalization analysis (read-only)
chronovista tags analyze
chronovista tags analyze --format json > analysis.json

# Full backfill (populates canonical_tags and tag_aliases)
chronovista tags normalize
chronovista tags normalize --batch-size 500

# Incremental: process only new/unresolved tags
chronovista tags normalize --incremental
chronovista tags normalize --incremental --dry-run

# Recalculate counts after manual changes
chronovista tags recount
chronovista tags recount --dry-run  # Preview count deltas
```

### Deleted Video Recovery

```bash
# Recover a specific deleted video
chronovista recover video --video-id dQw4w9WgXcQ

# Recover all unavailable videos (batch mode)
chronovista recover video --all --limit 50

# Preview recovery without making changes
chronovista recover video --all --dry-run

# Focus search on a specific era (faster for older videos)
chronovista recover video --video-id VIDEO_ID --start-year 2018

# Batch recovery with custom rate limiting
chronovista recover video --all --limit 20 --delay 2.0
```

### REST API Workflow

```bash
# 1. Authenticate (same as CLI)
chronovista auth login

# 2. Start API server
chronovista api start --port 8765

# 3. Access via HTTP
curl http://localhost:8765/api/v1/health
curl http://localhost:8765/api/v1/videos?limit=10

# 4. View interactive docs
open http://localhost:8765/docs
```

### Entity Management

```bash
# Create a standalone entity with aliases
chronovista entities create "Noam Chomsky" --type person --description "Linguist and political commentator" --alias "Chomsky"

# List all person entities
chronovista entities list --type person

# Search entities by name
chronovista entities list --search "chomsky"

# Backfill descriptions from classify --reason text
chronovista entities backfill-descriptions --dry-run
chronovista entities backfill-descriptions

# Classify a tag as an entity (creates entity + aliases from tag)
chronovista tags classify "aaron mate" --type person --description "Journalist, The Grayzone" --reason "The Grayzone reporter"
```

### Entity Mention Scanning (v0.41.0+)

Scan your transcript library to discover where known entities are mentioned, building a searchable cross-reference between entities and the specific video segments where they appear.

```bash
# Preview entity mentions without writing (dry-run)
chronovista entities scan --dry-run --limit 100

# Run a full scan across all transcripts
chronovista entities scan

# Scan only person entities in a specific video
chronovista entities scan --entity-type person --video-id VIDEO_ID

# Full rescan (deletes existing rule_match mentions first)
chronovista entities scan --full

# Scan only entities with zero existing mentions
chronovista entities scan --new-entities-only

# Audit: report user-correction mentions with unregistered text forms
chronovista entities scan --audit

# Custom batch size for large libraries
chronovista entities scan --batch-size 1000

# Scan all transcripts for a single entity by ID
chronovista entities scan --entity-id 019d1d2a-719b-7552-97d1-ea9aa08d3b47

# Dry-run preview for a single entity
chronovista entities scan --entity-id 019d1d2a-719b-7552-97d1-ea9aa08d3b47 --dry-run

# Single entity with language filter
chronovista entities scan --entity-id 019d1d2a-719b-7552-97d1-ea9aa08d3b47 --language en

# Full rescan for a single entity (deletes only that entity's rule_match mentions)
chronovista entities scan --entity-id 019d1d2a-719b-7552-97d1-ea9aa08d3b47 --full

# Scan one video for one specific entity (combined filter)
chronovista entities scan --entity-id 019d1d2a-719b-7552-97d1-ea9aa08d3b47 --video-id dQw4w9WgXcQ

# View entity mention statistics
chronovista entities stats --top 20

# List entities filtered by mention status
chronovista entities list --has-mentions --sort mentions
chronovista entities list --no-mentions
```

**Recommended workflow after bulk corrections:**

```bash
# 1. Apply corrections (e.g., fix ASR errors for an entity name)
chronovista corrections find-replace --pattern 'Claudia Sham\w+' --replacement 'Claudia Sheinbaum' --regex

# 2. Rebuild full transcript text to reflect corrections
chronovista corrections rebuild-text

# 3. Rescan for entity mentions (corrections create new aliases automatically)
chronovista entities scan --full
```

**Scan Options:**

| Flag | Description |
|------|-------------|
| `--dry-run` | Preview mentions without writing |
| `--full` | Delete existing `rule_match` mentions and rescan |
| `--audit` | Report user-correction mentions with unregistered text forms. Displays a Rich table showing entities with mention texts that don't match any registered alias or canonical name, along with suggested CLI commands to register them. Read-only operation. Mutually exclusive with `--full`. |
| `--new-entities-only` | Scan only entities with zero existing mentions |
| `--entity-id` | Scan for a single entity by UUID. Takes precedence over `--entity-type` and `--new-entities-only` |
| `--entity-type` | Filter by entity type (e.g., `person`) |
| `--video-id` | Filter by video ID |
| `--batch-size` | Custom batch size for large libraries |
| `--limit` | Limit number of segments to scan |

**Limitations:**

- Entity scanning uses word-boundary regex matching — partial word matches inside larger words are excluded (e.g., "Aaron" won't match "Aaronson")
- Short aliases (<3 characters) are skipped with a warning to avoid excessive false positives
- Cross-segment matches (a name split across two adjacent segments) are not detected; these must be corrected manually
- The scan processes segments independently; it does not yet scan video titles or descriptions (see issue #73)

### Batch Transcript Corrections

```bash
# 1. Discover patterns in existing corrections
chronovista corrections patterns --min-occurrences 2

# 2. Preview a batch correction
chronovista corrections find-replace --pattern "Chsky" --replacement "Chomsky" --dry-run

# 3. Apply the correction
chronovista corrections find-replace --pattern "Chsky" --replacement "Chomsky"

# 4. Rebuild full transcript text
chronovista corrections rebuild-text

# 5. Check correction statistics
chronovista corrections stats

# 6. Export corrections for backup
chronovista corrections export --format json --output corrections-backup.json

# 7. If a correction was wrong, batch revert it
chronovista corrections batch-revert --pattern "Chomsky" --dry-run
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | General error |
| 2 | Invalid arguments |
| 3 | Authentication required |
| 4 | API error |
| 5 | Database error |

## See Also

- [Authentication](authentication.md)
- [Data Synchronization](data-sync.md)
- [Topic Analytics](topic-analytics.md)
- [Google Takeout](google-takeout.md)
- [Data Population](data-population.md) - Recommended data population order (including recovery)
- [REST API](rest-api.md)
