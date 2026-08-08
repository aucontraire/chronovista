# Database Schema

Every table in the PostgreSQL schema, generated from the SQLAlchemy models
at build time — the same metadata Alembic autogenerates migrations from, so
this page cannot drift from the shipped database.

**25 tables.** For the reasoning behind the design, see
[Data Model](../architecture/data-model.md).

## Core Content

Channels, videos, and the reference data they hang off.

### `channels`

YouTube channel model with subscription tracking.

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `channel_id` | VARCHAR(24) | no |  | **PK** |
| `title` | VARCHAR(255) | no |  |  |
| `description` | TEXT | yes |  |  |
| `subscriber_count` | BIGINT | yes |  |  |
| `video_count` | INTEGER | yes |  |  |
| `default_language` | VARCHAR(10) | yes |  |  |
| `country` | VARCHAR(2) | yes |  |  |
| `thumbnail_url` | VARCHAR(500) | yes |  |  |
| `is_subscribed` | BOOLEAN | no | `False` |  |
| `availability_status` | VARCHAR(20) | no | `'available'` |  |
| `recovered_at` | TIMESTAMP WITH TIME ZONE | yes |  |  |
| `recovery_source` | VARCHAR(50) | yes |  |  |
| `unavailability_first_detected` | TIMESTAMP WITH TIME ZONE | yes |  |  |
| `created_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |
| `updated_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |

### `videos`

Enhanced video model with language support and content restrictions.

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `video_id` | VARCHAR(20) | no |  | **PK** |
| `channel_id` | VARCHAR(24) | yes |  | FK → `channels.channel_id` |
| `channel_name_hint` | VARCHAR(255) | yes |  |  |
| `category_id` | VARCHAR(10) | yes |  | FK → `video_categories.category_id` |
| `title` | TEXT | no |  |  |
| `description` | TEXT | yes |  |  |
| `upload_date` | TIMESTAMP WITH TIME ZONE | no |  |  |
| `duration` | INTEGER | no |  |  |
| `made_for_kids` | BOOLEAN | no | `False` |  |
| `self_declared_made_for_kids` | BOOLEAN | no | `False` |  |
| `default_language` | VARCHAR(10) | yes |  |  |
| `default_audio_language` | VARCHAR(10) | yes |  |  |
| `available_languages` | JSONB | yes |  |  |
| `region_restriction` | JSONB | yes |  |  |
| `content_rating` | JSONB | yes |  |  |
| `like_count` | INTEGER | yes |  |  |
| `view_count` | BIGINT | yes |  |  |
| `comment_count` | INTEGER | yes |  |  |
| `availability_status` | VARCHAR(20) | no | `'available'` |  |
| `alternative_url` | VARCHAR(500) | yes |  |  |
| `recovered_at` | TIMESTAMP WITH TIME ZONE | yes |  |  |
| `recovery_source` | VARCHAR(50) | yes |  |  |
| `unavailability_first_detected` | TIMESTAMP WITH TIME ZONE | yes |  |  |
| `created_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |
| `updated_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |

### `video_categories`

YouTube video category model.

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `category_id` | VARCHAR(10) | no |  | **PK** |
| `name` | VARCHAR(100) | no |  |  |
| `assignable` | BOOLEAN | no | `True` |  |
| `created_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |

### `video_localizations`

Multi-language video content variants.

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `video_id` | VARCHAR(20) | no |  | **PK**, FK → `videos.video_id` |
| `language_code` | VARCHAR(10) | no |  | **PK** |
| `localized_title` | TEXT | no |  |  |
| `localized_description` | TEXT | yes |  |  |
| `created_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |

**Composite primary key:** `video_id`, `language_code`

## Transcripts

Transcript text, per-segment timing, and the append-only correction audit trail.

### `video_transcripts`

Multi-language video transcripts with quality indicators.

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `video_id` | VARCHAR(20) | no |  | **PK**, FK → `videos.video_id` |
| `language_code` | VARCHAR(10) | no |  | **PK** |
| `transcript_text` | TEXT | no |  |  |
| `transcript_type` | VARCHAR(20) | no |  |  |
| `download_reason` | VARCHAR(30) | no |  |  |
| `confidence_score` | FLOAT | yes |  |  |
| `is_cc` | BOOLEAN | no | `False` |  |
| `is_auto_synced` | BOOLEAN | no | `True` |  |
| `track_kind` | VARCHAR(20) | no | `'standard'` |  |
| `caption_name` | VARCHAR(255) | yes |  |  |
| `downloaded_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |
| `raw_transcript_data` | JSONB | yes |  |  |
| `has_timestamps` | BOOLEAN | no | `True` |  |
| `segment_count` | INTEGER | yes |  |  |
| `total_duration` | FLOAT | yes |  |  |
| `source` | VARCHAR(50) | no | `'youtube_transcript_api'` |  |
| `has_corrections` | BOOLEAN | no | `false` |  |
| `last_corrected_at` | TIMESTAMP WITH TIME ZONE | yes |  |  |
| `correction_count` | INTEGER | no | `0` |  |

**Composite primary key:** `video_id`, `language_code`

### `transcript_segments`

Individual timed text segment from a video transcript.

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `id` | INTEGER | no |  | **PK** |
| `video_id` | VARCHAR(20) | no |  | FK → `video_transcripts.video_id` |
| `language_code` | VARCHAR(10) | no |  | FK → `video_transcripts.language_code` |
| `text` | TEXT | no |  |  |
| `corrected_text` | TEXT | yes |  |  |
| `has_correction` | BOOLEAN | no | `False` |  |
| `start_time` | FLOAT | no |  |  |
| `duration` | FLOAT | no |  |  |
| `end_time` | FLOAT | no |  |  |
| `sequence_number` | INTEGER | no |  |  |
| `created_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |

**Constraints:**

- CHECK `chk_segment_duration_non_negative`: `duration >= 0`
- CHECK `chk_segment_sequence_non_negative`: `sequence_number >= 0`
- CHECK `chk_segment_start_time_non_negative`: `start_time >= 0`

### `transcript_corrections`

Append-only audit record for transcript segment corrections (Feature 033).

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `id` | UUID | no |  | **PK** |
| `video_id` | VARCHAR(20) | no |  | FK → `video_transcripts.video_id` |
| `language_code` | VARCHAR(10) | no |  | FK → `video_transcripts.language_code` |
| `segment_id` | INTEGER | yes |  | FK → `transcript_segments.id` |
| `correction_type` | VARCHAR(30) | no |  |  |
| `original_text` | TEXT | no |  |  |
| `corrected_text` | TEXT | no |  |  |
| `correction_note` | TEXT | yes |  |  |
| `corrected_by_user_id` | VARCHAR(100) | yes |  |  |
| `corrected_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |
| `version_number` | INTEGER | no |  |  |
| `batch_id` | UUID | yes |  |  |

**Constraints:**

- CHECK `chk_transcript_corrections_version_number_positive`: `version_number >= 1`

## User Data

The local user's own engagement data, keyed by the canonical identity.

### `app_identities`

Singleton row holding the canonical local-user identity (Feature 060).

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `id` | INTEGER | no |  | **PK** |
| `user_id` | VARCHAR(50) | no |  | unique |
| `source` | VARCHAR(20) | no |  |  |
| `created_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |
| `updated_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |

**Constraints:**

- CHECK `chk_app_identities_singleton`: `id = 1`

### `user_videos`

User interaction tracking with videos.

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `user_id` | VARCHAR(50) | no |  | **PK** |
| `video_id` | VARCHAR(20) | no |  | **PK**, FK → `videos.video_id` |
| `watched_at` | TIMESTAMP WITH TIME ZONE | yes |  |  |
| `rewatch_count` | INTEGER | no | `0` |  |
| `liked` | BOOLEAN | no | `False` |  |
| `saved_to_playlist` | BOOLEAN | no | `False` |  |
| `created_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |
| `updated_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |

**Composite primary key:** `user_id`, `video_id`

### `user_language_preferences`

User language preferences for content consumption and learning.

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `user_id` | VARCHAR(50) | no |  | **PK** |
| `language_code` | VARCHAR(10) | no |  | **PK** |
| `preference_type` | VARCHAR(20) | no |  |  |
| `priority` | INTEGER | no |  |  |
| `auto_download_transcripts` | BOOLEAN | no | `False` |  |
| `learning_goal` | TEXT | yes |  |  |
| `created_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |

**Composite primary key:** `user_id`, `language_code`

## Playlists

Playlists and their membership, including Takeout-imported system playlists.

### `playlists`

Enhanced playlists with language support.

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `playlist_id` | VARCHAR(50) | no |  | **PK** |
| `title` | VARCHAR(255) | no |  |  |
| `description` | TEXT | yes |  |  |
| `default_language` | VARCHAR(10) | yes |  |  |
| `privacy_status` | VARCHAR(20) | no | `'private'` |  |
| `channel_id` | VARCHAR(24) | yes |  | FK → `channels.channel_id` |
| `video_count` | INTEGER | no | `0` |  |
| `published_at` | TIMESTAMP WITH TIME ZONE | yes |  |  |
| `deleted_flag` | BOOLEAN | no | `False` |  |
| `playlist_type` | VARCHAR(20) | no | `'regular'` |  |
| `created_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |
| `updated_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |

### `playlist_memberships`

Playlist-video relationships with position tracking.

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `playlist_id` | VARCHAR(50) | no |  | **PK**, FK → `playlists.playlist_id` |
| `video_id` | VARCHAR(20) | no |  | **PK**, FK → `videos.video_id` |
| `position` | INTEGER | no |  |  |
| `added_at` | TIMESTAMP WITH TIME ZONE | yes |  |  |
| `created_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |

**Composite primary key:** `playlist_id`, `video_id`

## Topics

YouTube's topic taxonomy and its associations to videos and channels.

### `topic_categories`

YouTube topic classification system with dynamic resolution support.

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `topic_id` | VARCHAR(50) | no |  | **PK** |
| `category_name` | VARCHAR(255) | no |  |  |
| `parent_topic_id` | VARCHAR(50) | yes |  | FK → `topic_categories.topic_id` |
| `topic_type` | VARCHAR(20) | no | `'youtube'` |  |
| `wikipedia_url` | VARCHAR(500) | yes |  | unique |
| `normalized_name` | VARCHAR(255) | yes |  |  |
| `source` | VARCHAR(20) | no | `'seeded'` |  |
| `last_seen_at` | TIMESTAMP WITH TIME ZONE | yes |  |  |
| `occurrence_count` | INTEGER | no | `1` |  |
| `created_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |

### `topic_aliases`

Alias mappings for topic name variations (spelling, redirects, synonyms).

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `alias` | VARCHAR(255) | no |  | **PK** |
| `topic_id` | VARCHAR(50) | no |  | FK → `topic_categories.topic_id` |
| `alias_type` | VARCHAR(20) | no |  |  |
| `created_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |

### `video_topics`

Video-topic relationships for content classification.

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `video_id` | VARCHAR(20) | no |  | **PK**, FK → `videos.video_id` |
| `topic_id` | VARCHAR(50) | no |  | **PK**, FK → `topic_categories.topic_id` |
| `relevance_type` | VARCHAR(20) | no | `'primary'` |  |
| `created_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |

**Composite primary key:** `video_id`, `topic_id`

### `channel_topics`

Channel-topic relationships for channel classification.

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `channel_id` | VARCHAR(24) | no |  | **PK**, FK → `channels.channel_id` |
| `topic_id` | VARCHAR(50) | no |  | **PK**, FK → `topic_categories.topic_id` |
| `created_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |

**Composite primary key:** `channel_id`, `topic_id`

## Tags and Normalization

Raw tags plus the canonical-tag layer that collapses spelling variants.

### `video_tags`

Video-level tags for content analysis.

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `video_id` | VARCHAR(20) | no |  | **PK**, FK → `videos.video_id` |
| `tag` | VARCHAR(500) | no |  | **PK** |
| `tag_order` | INTEGER | yes |  |  |
| `created_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |

**Composite primary key:** `video_id`, `tag`

### `channel_keywords`

Channel keywords for topic analysis.

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `channel_id` | VARCHAR(24) | no |  | **PK**, FK → `channels.channel_id` |
| `keyword` | VARCHAR(100) | no |  | **PK** |
| `keyword_order` | INTEGER | yes |  |  |
| `created_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |

**Composite primary key:** `channel_id`, `keyword`

### `canonical_tags`

Canonical tag form with normalization and entity linking.

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `id` | UUID | no |  | **PK** |
| `canonical_form` | VARCHAR(500) | no |  |  |
| `normalized_form` | VARCHAR(500) | no |  | unique |
| `alias_count` | INTEGER | no | `1` |  |
| `video_count` | INTEGER | no | `0` |  |
| `entity_type` | VARCHAR(50) | yes |  |  |
| `entity_id` | UUID | yes |  | FK → `named_entities.id` |
| `status` | VARCHAR(20) | no | `'active'` |  |
| `merged_into_id` | UUID | yes |  | FK → `canonical_tags.id` |
| `created_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |
| `updated_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |

**Constraints:**

- CHECK `chk_canonical_tag_alias_count_positive`: `alias_count >= 0`
- CHECK `chk_canonical_tag_canonical_form_not_empty`: `canonical_form != ''`
- CHECK `chk_canonical_tag_entity_type_valid`: `entity_type IN ('person', 'organization', 'place', 'event', 'work', 'technical_term', 'concept', 'other', 'topic', 'descriptor') OR entity_type IS NULL`
- CHECK `chk_canonical_tag_status_valid`: `status IN ('active', 'merged', 'deprecated')`
- CHECK `chk_canonical_tag_video_count_non_negative`: `video_count >= 0`

### `tag_aliases`

Raw tag forms mapped to their canonical representation.

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `id` | UUID | no |  | **PK** |
| `raw_form` | VARCHAR(500) | no |  | unique |
| `normalized_form` | VARCHAR(500) | no |  |  |
| `canonical_tag_id` | UUID | no |  | FK → `canonical_tags.id` |
| `creation_method` | VARCHAR(30) | no | `'auto_normalize'` |  |
| `normalization_version` | INTEGER | no | `1` |  |
| `occurrence_count` | INTEGER | no | `1` |  |
| `first_seen_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |
| `last_seen_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |
| `created_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |

**Constraints:**

- CHECK `chk_tag_alias_creation_method_valid`: `creation_method IN ('auto_normalize', 'manual_merge', 'backfill', 'api_create')`
- CHECK `chk_tag_alias_occurrence_count_positive`: `occurrence_count >= 1`

### `tag_operation_logs`

Audit log for tag normalization and management operations.

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `id` | UUID | no |  | **PK** |
| `operation_type` | VARCHAR(30) | no |  |  |
| `source_canonical_ids` | JSONB | no | `'[]'::jsonb` |  |
| `target_canonical_id` | UUID | yes |  |  |
| `affected_alias_ids` | JSONB | no | `'[]'::jsonb` |  |
| `reason` | TEXT | yes |  |  |
| `performed_by` | VARCHAR(100) | no | `'system'` |  |
| `performed_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |
| `rollback_data` | JSONB | no | `'{}'::jsonb` |  |
| `rolled_back` | BOOLEAN | no | `False` |  |
| `rolled_back_at` | TIMESTAMP WITH TIME ZONE | yes |  |  |

**Constraints:**

- CHECK `chk_tag_operation_type_valid`: `operation_type IN ('merge', 'split', 'rename', 'delete', 'create', 'repair')`

## Named Entities

Curated entities, their aliases, and every place they are mentioned.

### `named_entities`

Named entities extracted from video tags (people, places, organizations, etc.).

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `id` | UUID | no |  | **PK** |
| `canonical_name` | VARCHAR(500) | no |  |  |
| `canonical_name_normalized` | VARCHAR(500) | no |  |  |
| `entity_type` | VARCHAR(50) | no |  |  |
| `entity_subtype` | VARCHAR(100) | yes |  |  |
| `description` | TEXT | yes |  |  |
| `external_ids` | JSONB | no | `'{}'::jsonb` |  |
| `exclusion_patterns` | JSONB | no | `'[]'::jsonb` |  |
| `mention_count` | INTEGER | no | `0` |  |
| `video_count` | INTEGER | no | `0` |  |
| `channel_count` | INTEGER | no | `0` |  |
| `discovery_method` | VARCHAR(30) | no | `'manual'` |  |
| `confidence` | FLOAT | no | `1.0` |  |
| `status` | VARCHAR(20) | no | `'active'` |  |
| `merged_into_id` | UUID | yes |  | FK → `named_entities.id` |
| `created_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |
| `updated_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |

**Constraints:**

- UNIQUE on `canonical_name_normalized`, `entity_type` (`uq_named_entity_canonical`)
- CHECK `chk_entity_confidence_range`: `confidence >= 0.0 AND confidence <= 1.0`
- CHECK `chk_entity_discovery_method_valid`: `discovery_method IN ('manual', 'spacy_ner', 'tag_bootstrap', 'llm_extraction', 'user_created')`
- CHECK `chk_entity_status_valid`: `status IN ('active', 'merged', 'deprecated')`
- CHECK `chk_entity_type_valid`: `entity_type IN ('person', 'organization', 'place', 'event', 'work', 'technical_term', 'concept', 'other')`

### `entity_aliases`

Alternative names and variations for named entities.

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `id` | UUID | no |  | **PK** |
| `entity_id` | UUID | no |  | FK → `named_entities.id` |
| `alias_name` | VARCHAR(500) | no |  |  |
| `alias_name_normalized` | VARCHAR(500) | no |  |  |
| `alias_type` | VARCHAR(30) | no | `'name_variant'` |  |
| `case_sensitive` | BOOLEAN | no | `false` |  |
| `occurrence_count` | INTEGER | no | `0` |  |
| `first_seen_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |
| `last_seen_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |

**Constraints:**

- UNIQUE on `alias_name_normalized`, `entity_id` (`uq_entity_alias_name`)
- CHECK `chk_alias_type_valid`: `alias_type IN ('name_variant', 'abbreviation', 'nickname', 'asr_error', 'translated_name', 'former_name')`

### `entity_mentions`

Entity mention records linking named entities to transcript segments.

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `id` | UUID | no |  | **PK** |
| `entity_id` | UUID | no |  | FK → `named_entities.id` |
| `segment_id` | INTEGER | yes |  | FK → `transcript_segments.id` |
| `video_id` | VARCHAR(20) | no |  |  |
| `language_code` | VARCHAR(10) | yes |  |  |
| `mention_text` | VARCHAR(500) | no |  |  |
| `detection_method` | VARCHAR(30) | no | `'rule_match'` |  |
| `confidence` | FLOAT | yes | `1.0` |  |
| `match_start` | INTEGER | yes |  |  |
| `match_end` | INTEGER | yes |  |  |
| `correction_id` | UUID | yes |  | FK → `transcript_corrections.id` |
| `mention_source` | VARCHAR(20) | no | `transcript` |  |
| `mention_context` | TEXT | yes |  |  |
| `created_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |

**Constraints:**

- CHECK `chk_entity_mention_confidence_range`: `confidence >= 0.0 AND confidence <= 1.0`
- CHECK `chk_entity_mention_detection_method_valid`: `detection_method IN ('rule_match', 'spacy_ner', 'llm_extraction', 'manual', 'user_correction')`
- CHECK `chk_entity_mention_source_valid`: `mention_source IN ('transcript', 'title', 'description')`

**Indexes:**

- INDEX `ix_entity_mentions_correction_id` on `correction_id`
- INDEX `ix_entity_mentions_detection_method` on `detection_method`
- INDEX `ix_entity_mentions_entity_id` on `entity_id`
- INDEX `ix_entity_mentions_mention_source` on `mention_source`
- INDEX `ix_entity_mentions_segment_id` on `segment_id`
- INDEX `ix_entity_mentions_video_id` on `video_id`
- INDEX `ix_entity_mentions_video_language` on `video_id`, `language_code`
- UNIQUE INDEX `uq_entity_mentions_description` on `entity_id`, `video_id`, `mention_source`, `mention_text`
- UNIQUE INDEX `uq_entity_mentions_manual` on `entity_id`, `video_id`, `detection_method`
- UNIQUE INDEX `uq_entity_mentions_title` on `entity_id`, `video_id`, `mention_source`
- UNIQUE INDEX `uq_entity_mentions_transcript` on `entity_id`, `segment_id`, `match_start`

### `entity_operation_logs`

Audit log for named-entity curation edits (name/description) — Feature 057.

| Column | Type | Null | Default | Notes |
|--------|------|------|---------|-------|
| `id` | UUID | no |  | **PK** |
| `entity_id` | UUID | no |  | FK → `named_entities.id` |
| `operation_type` | VARCHAR(30) | no | `'update'` |  |
| `rollback_data` | JSONB | no | `'{}'::jsonb` |  |
| `performed_by` | VARCHAR(100) | no | `'system'` |  |
| `performed_at` | TIMESTAMP WITH TIME ZONE | no | `now()` |  |
| `rolled_back` | BOOLEAN | no | `False` |  |
| `rolled_back_at` | TIMESTAMP WITH TIME ZONE | yes |  |  |

**Constraints:**

- CHECK `chk_entity_operation_type_valid`: `operation_type IN ('update')`

**Indexes:**

- INDEX `idx_entity_operation_logs_entity_id` on `entity_id`
- INDEX `idx_entity_operation_logs_performed_at` on `performed_at`
