# Data Model

Database schema and entity relationships.

## Entity Relationship Diagram

```
+-------------------+     +-------------------+
|     channels      |     |  topic_categories |
+-------------------+     +-------------------+
| PK channel_id     |     | PK topic_id       |
|    title          |     |    category_name  |
|    description    |     |    parent_topic_id|
|    subscriber_cnt |     |    topic_type     |
|    video_count    |     +--------+----------+
|    default_lang   |              |
+--------+----------+              |
         |                         |
         |  +-------------------+  |
         +--| channel_topics    |--+
         |  +-------------------+
         |  | FK channel_id    |
         |  | FK topic_id      |
         |  +------------------+
         |
         |  +-------------------+
         +--| channel_keywords  |
         |  +-------------------+
         |  | FK channel_id    |
         |  |    keyword        |
         |  |    keyword_order  |
         |  +------------------+
         |
+--------+-----------+     +-------------------+
|      videos        |     |   video_topics    |
+--------------------+     +-------------------+
| PK video_id        |-----| FK video_id       |
| FK channel_id      |     | FK topic_id       |
|    title           |     |    relevance_type |
|    description     |     +-------------------+
|    duration        |
|    made_for_kids   |     +-------------------+
|    default_lang    |     |   video_tags      |
|    region_restrict |-----+-------------------+
+--------+-----------+     | FK video_id       |
         |                 |    tag            |
         |                 |    tag_order      |
         |                 +-------------------+
         |
         |                 +-------------------+
         +-----------------|video_transcripts  |
         |                 +-------------------+
         |                 | FK video_id       |
         |                 |    language_code  |
         |                 |    transcript_text|
         |                 |    transcript_type|
         |                 |    is_cc          |
         |                 |    is_auto_synced |
         |                 +-------------------+
         |
         |                 +-------------------+
         +-----------------|video_localizations|
                           +-------------------+
                           | FK video_id       |
                           |    language_code  |
                           |    localized_title|
                           +-------------------+

+-------------------+     +-------------------+     +-------------------+
| named_entities    |     | canonical_tags    |     | tag_operation_logs|
+-------------------+     +-------------------+     +-------------------+
| PK id (UUID)      |     | PK id (UUID)      |     | PK id (UUID)      |
|    canonical_name |     |    canonical_form |     |    operation_type |
|    entity_type    |     |    normalized_form|     |    rollback_data  |
|    discovery_method|    |    entity_type    |     |    performed_by   |
|    confidence     |     | FK entity_id      |     |    rolled_back    |
+--------+----------+     |    status         |     +-------------------+
         |                +--------+----------+
         |  1:N                    |  1:N
         |                         |
+--------+----------+     +--------+----------+
| entity_aliases    |     | tag_aliases       |
+-------------------+     +-------------------+
| PK id (UUID)      |     | PK id (UUID)      |
| FK entity_id      |     |    raw_form       |-----> video_tags.tag
|    alias_name     |     |    normalized_form|
|    alias_type     |     | FK canonical_tag_id|
+-------------------+     +-------------------+
```

## Core Tables

### channels

```sql
CREATE TABLE channels (
    channel_id VARCHAR(24) PRIMARY KEY,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    subscriber_count BIGINT,
    video_count INTEGER,
    default_language VARCHAR(10),
    country VARCHAR(2),
    thumbnail_url VARCHAR(500),
    availability_status VARCHAR(20) DEFAULT 'available',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### videos

```sql
CREATE TABLE videos (
    video_id VARCHAR(20) PRIMARY KEY,
    channel_id VARCHAR(24) REFERENCES channels(channel_id),
    title TEXT NOT NULL,
    description TEXT,
    upload_date TIMESTAMP NOT NULL,
    duration INTEGER NOT NULL,
    made_for_kids BOOLEAN DEFAULT FALSE,
    self_declared_made_for_kids BOOLEAN DEFAULT FALSE,
    default_language VARCHAR(10),
    default_audio_language VARCHAR(10),
    available_languages TEXT,  -- JSON array
    region_restriction JSONB,
    content_rating JSONB,
    like_count INTEGER,
    view_count BIGINT,
    comment_count INTEGER,
    deleted_flag BOOLEAN DEFAULT FALSE,  -- Legacy; prefer availability_status
    availability_status VARCHAR(20) DEFAULT 'available',
    alternative_url VARCHAR(500),
    recovered_at TIMESTAMP WITH TIME ZONE,
    recovery_source VARCHAR(255),  -- e.g. "wayback:20220106075526"
    unavailability_first_detected TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Availability Status Values:** `available`, `deleted`, `private`, `unavailable`, `region_restricted`

**Recovery Columns:**
- `recovered_at` — When metadata was last recovered from an external source
- `recovery_source` — Provenance identifier (e.g., `wayback:20220106075526`)
- `alternative_url` — Alternate URL if the video is available elsewhere
- `unavailability_first_detected` — When the video was first detected as unavailable

### user_language_preferences

```sql
CREATE TABLE user_language_preferences (
    user_id VARCHAR(255),
    language_code VARCHAR(10),
    preference_type VARCHAR(20),  -- FLUENT, LEARNING, CURIOUS, EXCLUDE
    priority INTEGER,
    auto_download_transcripts BOOLEAN DEFAULT FALSE,
    learning_goal TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, language_code)
);
```

### video_transcripts

```sql
CREATE TABLE video_transcripts (
    video_id VARCHAR(20) REFERENCES videos(video_id),
    language_code VARCHAR(10),
    transcript_text TEXT NOT NULL,
    transcript_type VARCHAR(20),  -- AUTO, MANUAL, TRANSLATED
    download_reason VARCHAR(30),  -- USER_REQUEST, AUTO_PREFERRED, LEARNING_LANGUAGE
    confidence_score FLOAT,
    is_cc BOOLEAN DEFAULT FALSE,
    is_auto_synced BOOLEAN DEFAULT TRUE,
    track_kind VARCHAR(20) DEFAULT 'standard',
    caption_name VARCHAR(255),
    downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (video_id, language_code)
);
```

## Tag and Topic Tables

### topic_categories

```sql
CREATE TABLE topic_categories (
    topic_id VARCHAR(50) PRIMARY KEY,
    category_name VARCHAR(255) NOT NULL,
    parent_topic_id VARCHAR(50) REFERENCES topic_categories(topic_id),
    topic_type VARCHAR(20) DEFAULT 'youtube',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### video_tags

```sql
CREATE TABLE video_tags (
    video_id VARCHAR(20) REFERENCES videos(video_id),
    tag VARCHAR(100) NOT NULL,
    tag_order INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (video_id, tag)
);
```

### channel_keywords

```sql
CREATE TABLE channel_keywords (
    channel_id VARCHAR(24) REFERENCES channels(channel_id),
    keyword VARCHAR(100) NOT NULL,
    keyword_order INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (channel_id, keyword)
);
```

## Relationship Tables

### video_topics

```sql
CREATE TABLE video_topics (
    video_id VARCHAR(20) REFERENCES videos(video_id),
    topic_id VARCHAR(50) REFERENCES topic_categories(topic_id),
    relevance_type VARCHAR(20),  -- primary, relevant, suggested
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (video_id, topic_id)
);
```

### channel_topics

```sql
CREATE TABLE channel_topics (
    channel_id VARCHAR(24) REFERENCES channels(channel_id),
    topic_id VARCHAR(50) REFERENCES topic_categories(topic_id),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (channel_id, topic_id)
);
```

## User Interaction Tables

### user_videos

```sql
CREATE TABLE user_videos (
    user_id VARCHAR(255),
    video_id VARCHAR(20) REFERENCES videos(video_id),
    watched_count INTEGER DEFAULT 0,
    last_watched_at TIMESTAMP,
    watch_percentage FLOAT DEFAULT 0,
    liked BOOLEAN,
    saved_to_watch_later BOOLEAN DEFAULT FALSE,
    first_watched_at TIMESTAMP,
    total_watch_time INTEGER,  -- seconds
    PRIMARY KEY (user_id, video_id)
);
```

### user_subscriptions

```sql
CREATE TABLE user_subscriptions (
    user_id VARCHAR(255),
    channel_id VARCHAR(24) REFERENCES channels(channel_id),
    subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    notification_preference VARCHAR(20) DEFAULT 'all',
    PRIMARY KEY (user_id, channel_id)
);
```

## Playlist Tables

### playlists

The `playlist_id` field serves as the single source of truth, supporting:
- **YouTube IDs** (PL prefix, 30-50 chars): `PLdU2XMVb99xMxwMeeLWDqmyW8GFqpvgVC`
- **Internal IDs** (int_ prefix, 36 chars): `int_5d41402abc4b2a76b9719d911017c592`
- **System playlists**: `LL` (Liked), `WL` (Watch Later), `HL` (History)

Link status is derived from the `playlist_id` prefix, not stored separately.

```sql
CREATE TABLE playlists (
    playlist_id VARCHAR(50) PRIMARY KEY,  -- Consolidated ID (YouTube or internal)
    channel_id VARCHAR(24) REFERENCES channels(channel_id),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    default_language VARCHAR(10),
    privacy_status VARCHAR(20),
    playlist_type VARCHAR(20) DEFAULT 'regular',  -- regular, liked, watch_later, history
    video_count INTEGER DEFAULT 0,
    published_at TIMESTAMP,  -- From Google Takeout playlists.csv
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### playlist_memberships

```sql
CREATE TABLE playlist_memberships (
    playlist_id VARCHAR(50) REFERENCES playlists(playlist_id),
    video_id VARCHAR(20) REFERENCES videos(video_id),
    position INTEGER NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (playlist_id, video_id)
);
```

## Localization Tables

### video_localizations

```sql
CREATE TABLE video_localizations (
    video_id VARCHAR(20) REFERENCES videos(video_id),
    language_code VARCHAR(10),
    localized_title TEXT NOT NULL,
    localized_description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (video_id, language_code)
);
```

## Tag Normalization Tables

### canonical_tags

The authoritative/display form of each unique tag concept. Maps raw tag variations to canonical forms via `tag_aliases`.

```sql
CREATE TABLE canonical_tags (
    id UUID PRIMARY KEY,  -- UUIDv7 generated application-side
    canonical_form VARCHAR(500) NOT NULL,
    normalized_form VARCHAR(500) NOT NULL UNIQUE,
    alias_count INTEGER NOT NULL DEFAULT 1,
    video_count INTEGER NOT NULL DEFAULT 0,
    entity_type VARCHAR(50),  -- person, organization, place, event, work, technical_term, topic, descriptor
    entity_id UUID REFERENCES named_entities(id) ON DELETE SET NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active',  -- active, merged, deprecated
    merged_into_id UUID REFERENCES canonical_tags(id),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
```

### tag_aliases

Maps every raw tag variation to its canonical form. Joins to `video_tags.tag` via `raw_form`.

```sql
CREATE TABLE tag_aliases (
    id UUID PRIMARY KEY,  -- UUIDv7 generated application-side
    raw_form VARCHAR(500) NOT NULL UNIQUE,
    normalized_form VARCHAR(500) NOT NULL,
    canonical_tag_id UUID NOT NULL REFERENCES canonical_tags(id) ON DELETE CASCADE,
    creation_method VARCHAR(30) NOT NULL DEFAULT 'auto_normalize',
    normalization_version INTEGER NOT NULL DEFAULT 1,
    occurrence_count INTEGER NOT NULL DEFAULT 1,
    first_seen_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
);
```

### named_entities

Entity knowledge base for named entities extracted from tags.

```sql
CREATE TABLE named_entities (
    id UUID PRIMARY KEY,  -- UUIDv7 generated application-side
    canonical_name VARCHAR(500) NOT NULL,
    canonical_name_normalized VARCHAR(500) NOT NULL,
    entity_type VARCHAR(50) NOT NULL,  -- person, organization, place, event, work, technical_term
    entity_subtype VARCHAR(100),
    description TEXT,
    external_ids JSONB DEFAULT '{}',
    mention_count INTEGER NOT NULL DEFAULT 0,
    video_count INTEGER NOT NULL DEFAULT 0,
    channel_count INTEGER NOT NULL DEFAULT 0,
    discovery_method VARCHAR(30) NOT NULL DEFAULT 'manual',
    confidence FLOAT NOT NULL DEFAULT 1.0,
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    merged_into_id UUID REFERENCES named_entities(id),
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_entity_normalized_type UNIQUE (canonical_name_normalized, entity_type)
);
```

### entity_aliases

Name variations for entities. Created when a tag is classified as an entity type.

```sql
CREATE TABLE entity_aliases (
    id UUID PRIMARY KEY,  -- UUIDv7 generated application-side
    entity_id UUID NOT NULL REFERENCES named_entities(id) ON DELETE CASCADE,
    alias_name VARCHAR(500) NOT NULL,
    alias_name_normalized VARCHAR(500) NOT NULL,
    alias_type VARCHAR(30) NOT NULL DEFAULT 'name_variant',
    occurrence_count INTEGER NOT NULL DEFAULT 0,
    first_seen_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_entity_alias_normalized UNIQUE (alias_name_normalized, entity_id)
);
```

### tag_operation_logs

Audit trail for tag management operations (merge, split, rename, classify, deprecate). Stores self-contained `rollback_data` JSONB for undo capability.

```sql
CREATE TABLE tag_operation_logs (
    id UUID PRIMARY KEY,  -- UUIDv7 generated application-side
    operation_type VARCHAR(30) NOT NULL,  -- merge, split, rename, delete, create
    source_canonical_ids JSONB NOT NULL DEFAULT '[]',
    target_canonical_id UUID,
    affected_alias_ids JSONB NOT NULL DEFAULT '[]',
    reason TEXT,
    performed_by VARCHAR(100) NOT NULL DEFAULT 'system',
    performed_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    rollback_data JSONB NOT NULL DEFAULT '{}',
    rolled_back BOOLEAN NOT NULL DEFAULT FALSE,
    rolled_back_at TIMESTAMP WITH TIME ZONE
);
```

## Indexes

### Performance Indexes

```sql
-- Channel queries
CREATE INDEX idx_channels_language ON channels(default_language);
CREATE INDEX idx_channels_country ON channels(country);

-- Video queries
CREATE INDEX idx_videos_channel ON videos(channel_id);
CREATE INDEX idx_videos_upload_date ON videos(upload_date);
CREATE INDEX idx_videos_language ON videos(default_language);

-- Transcript queries
CREATE INDEX idx_transcripts_language ON video_transcripts(language_code);
CREATE INDEX idx_transcripts_type ON video_transcripts(transcript_type);

-- Topic queries
CREATE INDEX idx_video_topics_topic ON video_topics(topic_id);
CREATE INDEX idx_channel_topics_topic ON channel_topics(topic_id);

-- User queries
CREATE INDEX idx_user_videos_user ON user_videos(user_id);
CREATE INDEX idx_user_videos_watched ON user_videos(last_watched_at);

-- Tag normalization queries
CREATE INDEX idx_canonical_tags_video_count_desc ON canonical_tags(video_count DESC);
CREATE INDEX idx_canonical_tags_canonical_pattern ON canonical_tags(canonical_form varchar_pattern_ops);
CREATE INDEX idx_canonical_tags_entity_id ON canonical_tags(entity_id) WHERE entity_id IS NOT NULL;
CREATE INDEX idx_canonical_tags_active_normalized ON canonical_tags(normalized_form) WHERE status = 'active';
CREATE INDEX idx_tag_aliases_normalized ON tag_aliases(normalized_form);
CREATE INDEX idx_tag_aliases_canonical_id ON tag_aliases(canonical_tag_id);
CREATE INDEX idx_tag_aliases_raw_pattern ON tag_aliases(raw_form varchar_pattern_ops);
CREATE INDEX idx_named_entities_normalized ON named_entities(canonical_name_normalized);
CREATE INDEX idx_named_entities_type ON named_entities(entity_type);
CREATE INDEX idx_entity_aliases_entity_id ON entity_aliases(entity_id);
CREATE INDEX idx_tag_operation_logs_performed_at ON tag_operation_logs(performed_at);
CREATE INDEX idx_video_tags_tag ON video_tags(tag);
```

## Pydantic Models

### Channel

```python
class Channel(BaseModel):
    channel_id: ChannelId
    title: str
    description: str
    subscriber_count: int
    video_count: int
    default_language: Optional[str]
    country: Optional[str]
    is_subscribed: bool
    subscription_date: Optional[datetime]
    thumbnail_url: Optional[str]
```

### Video

```python
class Video(BaseModel):
    video_id: VideoId
    channel_id: ChannelId
    title: str
    description: str
    upload_date: datetime
    duration: int
    made_for_kids: bool
    self_declared_made_for_kids: bool
    default_language: Optional[str]
    default_audio_language: Optional[str]
    available_languages: List[str]
    region_restriction: Optional[Dict[str, List[str]]]
    content_rating: Optional[Dict[str, str]]
```

### VideoTranscript

```python
class VideoTranscript(BaseModel):
    video_id: VideoId
    language_code: str
    transcript_text: str
    transcript_type: TranscriptType
    download_reason: DownloadReason
    confidence_score: Optional[float]
    is_cc: bool
    is_auto_synced: bool
    track_kind: str
    caption_name: Optional[str]
    downloaded_at: datetime
```

## See Also

- [Architecture Overview](overview.md) - System context
- [System Design](system-design.md) - Service layer
- [API Integration](api-integration.md) - YouTube API mapping
