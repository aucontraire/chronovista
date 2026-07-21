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
| `OAUTH_REDIRECT_URI` | OAuth callback URL | `http://localhost:8080/auth/callback` |
| `API_RATE_LIMIT` | Requests per minute | `100` |

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
Preferences are **stored in the database** (the `user_language_preferences`
table) — there is no YAML config file. Manage them with the `languages` command
group.

### Language Preference Types

| Type | Description | Auto-Download |
|------|-------------|---------------|
| `fluent` | Languages you speak fluently | Yes (default) |
| `learning` | Languages you're actively learning | Yes (default) |
| `curious` | Languages you find interesting | No (default) |
| `exclude` | Languages to skip entirely | Never |

### Managing Preferences via CLI

```bash
# Interactive setup / add preferences for one or more languages
chronovista languages set

# Add a single language at a given tier
chronovista languages add

# List current preferences
chronovista languages list

# Remove a language, or reset all preferences
chronovista languages remove
chronovista languages reset
```

Run `chronovista languages --help` (or see the generated
[CLI reference](../reference/cli.md)) for the exact flags each subcommand
accepts.

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

All application configuration is environment-based (via Pydantic `Settings`);
there is no `config.yaml`. Beyond the required variables above, these optional
environment variables tune behavior (defaults shown):

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Logging verbosity | `INFO` |
| `DATA_DIR` | Directory for the OAuth token and app data | `./data` |
| `CACHE_DIR` | Directory for the CDX/image cache | `./cache` |
| `LOGS_DIR` | Directory for log files | `./logs` |
| `EXPORT_DIR` | Default export output directory | `./exports` |
| `EXPORT_FORMAT` | Default export format | `csv` |
| `API_RATE_LIMIT` | YouTube API requests per minute | `100` |
| `CONCURRENT_REQUESTS` | Max concurrent API requests | (see `settings.py`) |
| `RETRY_ATTEMPTS` | Retry attempts for transient failures | `3` |
| `CDX_CACHE_TTL_HOURS` | Wayback CDX cache lifetime | (see `settings.py`) |

See `src/chronovista/config/settings.py` for the authoritative list and default
values.

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

The OAuth token is written to `youtube_token.json` inside the configured
`DATA_DIR` (default `./data/`):

```
$DATA_DIR/
└── youtube_token.json   # OAuth access + refresh token (JSON)
```

The token file contains a live refresh token, so treat it like a credential:
keep `DATA_DIR` out of version control and off shared storage. Delete the file
(or run the auth flow again) to force re-authentication.

## Next Steps

- [Quick Start](quickstart.md) - Start using chronovista
- [CLI Overview](../user-guide/cli-overview.md) - Command reference
- [Development Setup](../development/setup.md) - Contributing guide
