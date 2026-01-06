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
    deleted_flag BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

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

```sql
CREATE TABLE playlists (
    playlist_id VARCHAR(255) PRIMARY KEY,
    channel_id VARCHAR(24) REFERENCES channels(channel_id),
    title VARCHAR(255) NOT NULL,
    description TEXT,
    default_language VARCHAR(10),
    privacy_status VARCHAR(20),
    is_user_playlist BOOLEAN DEFAULT FALSE,
    podcast_enabled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### playlist_items

```sql
CREATE TABLE playlist_items (
    playlist_id VARCHAR(255) REFERENCES playlists(playlist_id),
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
