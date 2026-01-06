# Configuration

Complete configuration reference for chronovista.

## Environment Variables

chronovista uses environment variables for configuration. Create a `.env` file in the project root.

### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `YOUTUBE_API_KEY` | YouTube Data API key | `AIzaSy...` |
| `YOUTUBE_CLIENT_ID` | OAuth 2.0 client ID | `123456...apps.googleusercontent.com` |
| `YOUTUBE_CLIENT_SECRET` | OAuth 2.0 client secret | `GOCSPX-...` |
| `DATABASE_URL` | Database connection string | `postgresql+asyncpg://user:pass@localhost/db` |
| `SECRET_KEY` | Application secret key | Random 32+ character string |

### Optional Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Logging verbosity | `INFO` |
| `YOUTUBE_REDIRECT_URI` | OAuth callback URL | `http://localhost:8080/auth/callback` |
| `API_RATE_LIMIT` | Requests per minute | `100` |
| `TRANSCRIPT_DOWNLOAD_DELAY` | Delay between transcript downloads (seconds) | `5` |

## Database Configuration

### PostgreSQL (Recommended)

```env
DATABASE_URL=postgresql+asyncpg://username:password@localhost:5432/chronovista
```

For development with Docker:

```env
DATABASE_URL=postgresql+asyncpg://dev_user:dev_password@localhost:5434/chronovista_dev
```

### MySQL

```env
DATABASE_URL=mysql+aiomysql://username:password@localhost:3306/chronovista
```

## Language Configuration

chronovista supports multi-language preferences for transcript management.

Create `~/.chronovista/language_config.yaml`:

```yaml
language_preferences:
  fluent:
    - en-US  # Native English
    - es-ES  # Fluent Spanish
  learning:
    - it-IT  # Studying Italian
    - pt-BR  # Learning Portuguese
  curious:
    - fr-FR  # Sometimes interesting
  exclude:
    - zh-CN  # Not interested

auto_download_rules:
  fluent_languages: true
  learning_languages: true
  curious_languages: false
  max_transcripts_per_video: 3
  short_video_threshold: 300  # seconds
```

### Language Preference Types

| Type | Description | Auto-Download |
|------|-------------|---------------|
| `fluent` | Languages you speak fluently | Yes (default) |
| `learning` | Languages you're actively learning | Yes (default) |
| `curious` | Languages you find interesting | No (default) |
| `exclude` | Languages to skip entirely | Never |

### Setting Preferences via CLI

```bash
# Set language preferences
chronovista languages set --fluent en-US,es-ES --learning it-IT --curious fr-FR

# View current preferences
chronovista languages show

# Configure auto-download behavior
chronovista languages config --auto-download learning
```

## OAuth Scope Management

chronovista uses progressive scope management for YouTube API access.

### Read Scopes (Default)

Used for data retrieval operations:

```python
READ_SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/youtube.force-ssl"
]
```

### Write Scopes (Phase 3)

Required for playlist management and interactions:

```python
WRITE_SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.force-ssl"
]
```

## Rate Limiting

### YouTube Transcript API

The `youtube-transcript-api` library has IP-based rate limiting:

```yaml
# Recommended limits
max_requests_per_hour: 50-100
min_delay_between_requests: 5  # seconds
daily_limit: 300-500  # requests per IP
```

### YouTube Data API

Official API quota limits:

| Operation | Quota Units |
|-----------|-------------|
| `videos.list` | 1 |
| `channels.list` | 1 |
| `playlists.list` | 1 |
| `captions.list` | 50 |
| `captions.download` | 200 |

Daily quota: 10,000 units (default)

### Proxy Configuration

For high-volume transcript downloads:

```python
from youtube_transcript_api.proxies import WebshareProxyConfig

proxy_config = WebshareProxyConfig(
    proxy_username="your-username",
    proxy_password="your-password",
    filter_ip_locations=["us", "ca"]
)
```

## Application Configuration

### CLI Configuration

Configure CLI behavior in `~/.chronovista/config.yaml`:

```yaml
cli:
  output_format: rich  # rich, json, plain
  color_enabled: true
  progress_bars: true
  verbose: false

export:
  default_format: csv
  include_headers: true
  date_format: "%Y-%m-%d"

sync:
  batch_size: 50
  retry_attempts: 3
  retry_delay: 5
```

### Logging Configuration

```yaml
logging:
  level: INFO
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  file: ~/.chronovista/logs/chronovista.log
  max_size: 10MB
  backup_count: 5
```

## Development Configuration

### Testing Configuration

See `pyproject.toml` for pytest configuration:

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = [
    "-v",
    "--cov=chronovista",
    "--cov-report=term-missing",
    "--cov-fail-under=90"
]
```

### Database Development

For development, use the Docker-based database:

```bash
# Start development database
make dev-db-up

# Run migrations
make dev-migrate

# Reset database
make dev-db-reset
```

## Security Best Practices

!!! warning "Security Considerations"
    - Never commit `.env` files to version control
    - Use strong, unique `SECRET_KEY` values
    - Rotate API credentials periodically
    - Store OAuth tokens securely

### Generating a Secret Key

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Credential Storage

OAuth tokens are stored encrypted in `~/.chronovista/credentials/`:

```
~/.chronovista/
├── credentials/
│   └── youtube_token.json  # Encrypted OAuth token
├── config.yaml
└── language_config.yaml
```

## Next Steps

- [Quick Start](quickstart.md) - Start using chronovista
- [CLI Overview](../user-guide/cli-overview.md) - Command reference
- [Development Setup](../development/setup.md) - Contributing guide
