<h1 align="center">chronovista</h1>

<p align="center">
  <strong>Your YouTube data, your control. Local-first analytics for personal YouTube history.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/license-AGPL--3.0-green.svg" alt="License: AGPL-3.0">
  <img src="https://img.shields.io/badge/tests-5,473+-brightgreen.svg" alt="Tests: 5,473+">
  <img src="https://img.shields.io/badge/coverage-72%25-brightgreen.svg" alt="Coverage: 72%">
  <img src="https://img.shields.io/badge/code%20style-black-000000.svg" alt="Code style: black">
</p>

<p align="center">
  <a href="#quick-start">Quick Start</a> |
  <a href="#features">Features</a> |
  <a href="#installation">Installation</a> |
  <a href="#usage">Usage</a> |
  <a href="#development">Development</a> |
  <a href="docs/README.md">Docs</a>
</p>

---

## Quick Start

```bash
# Clone and install
git clone https://github.com/chronovista/chronovista.git
cd chronovista && poetry install

# Setup database (Docker Compose, port 5434)
make dev-db-up
cp .env.example .env  # Add YouTube API credentials, set DEVELOPMENT_MODE=true
make dev-migrate

# Authenticate and sync
chronovista auth login
chronovista sync all
```

## Features

| Category | Capabilities |
|----------|-------------|
| **Privacy-First** | All data stored locally in PostgreSQL - no cloud sync, complete data ownership |
| **Multi-Language** | Smart transcript management with language preferences (fluent, learning, curious) |
| **Transcript Queries** | Timestamp-based transcript search - find what was said at any moment |
| **Channel Analytics** | Subscription tracking, keyword extraction, topic analysis |
| **Topic Intelligence** | 17 CLI commands for content discovery, trends, and engagement scoring |
| **Google Takeout** | Import complete YouTube history including deleted videos |
| **Export Options** | CSV/JSON export with language-aware filtering |
| **Write Operations** | Create playlists, like videos, subscribe to channels |
| **REST API** | FastAPI server with 20+ endpoints for programmatic access |
| **Video Filtering** | Filter by tags, topics, categories with fuzzy search suggestions |

## Installation

### Prerequisites

- Python 3.11+
- [Poetry](https://python-poetry.org/)
- Docker (with Compose, for the development database)
- [YouTube Data API credentials](https://console.cloud.google.com/) (API key + OAuth client)

### Install

```bash
git clone https://github.com/chronovista/chronovista.git
cd chronovista
poetry install
```

### Database Setup

```bash
# Start development database (Docker Compose, port 5434)
make dev-db-up

# Configure environment
cp .env.example .env  # Add YouTube API credentials, set DEVELOPMENT_MODE=true

# Run migrations
make dev-migrate
```

<details>
<summary>MySQL Setup</summary>

```bash
docker run --name chronovista-mysql -e MYSQL_ROOT_PASSWORD=dev -e MYSQL_DATABASE=chronovista -p 3306:3306 -d mysql:8
```

Update `DATABASE_URL` in `.env`:
```
DATABASE_URL=mysql+aiomysql://root:dev@localhost:3306/chronovista
```
</details>

<details>
<summary>YouTube API Setup</summary>

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project and enable **YouTube Data API v3**
3. Create **OAuth 2.0 Client ID** credentials
4. Add redirect URI: `http://localhost:8080/auth/callback`
5. Add credentials to `.env`:
   ```env
   YOUTUBE_API_KEY=your_api_key
   YOUTUBE_CLIENT_ID=your_client_id
   YOUTUBE_CLIENT_SECRET=your_client_secret
   ```
</details>

## Usage

### Authentication

```bash
chronovista auth login     # OAuth login
chronovista auth status    # Check status
chronovista auth logout    # Logout
```

### Sync Your Data

```bash
chronovista sync history      # Watch history
chronovista sync playlists    # Playlists
chronovista sync transcripts  # Video transcripts
chronovista sync topics       # Topic categories
chronovista sync all          # Everything
```

### Transcript Queries

```bash
chronovista transcript segment VIDEO_ID 5:00      # Get segment at timestamp
chronovista transcript context VIDEO_ID 5:00      # Get 30s context window
chronovista transcript range VIDEO_ID 1:00 5:00   # Get segments in range
chronovista transcript range VIDEO_ID 0:00 10:00 --format srt  # SRT export
```

### Topic Analytics

```bash
chronovista topics list              # All topics with content counts
chronovista topics popular           # Most popular by content
chronovista topics videos 10         # Videos in Music category
chronovista topics trends            # Popularity over time
chronovista topics chart             # Visual ASCII chart
chronovista topics explore           # Interactive exploration
```

### Google Takeout Import

Import your complete YouTube history from [Google Takeout](https://takeout.google.com/):

```bash
chronovista takeout seed /path/to/takeout              # Full import
chronovista takeout seed /path/to/takeout --dry-run    # Preview changes
chronovista takeout seed /path/to/takeout --incremental # Safe re-run
chronovista takeout analyze /path/to/takeout           # Analyze patterns
```

<details>
<summary>Takeout Details</summary>

**What gets imported:**
- Channels, videos, and watch history with timestamps
- All playlists with video relationships
- Historical data including deleted/private videos

**Analysis commands:**
```bash
chronovista takeout peek /path/to/takeout --summary
chronovista takeout analyze /path/to/takeout --type viewing-patterns
chronovista takeout analyze /path/to/takeout --type channel-relationships
chronovista takeout inspect /path/to/takeout --focus playlists
```

**Combine with API data:**
```bash
chronovista takeout seed /path/to/takeout
chronovista sync all  # Enriches with current API data
```
</details>

### REST API

Start the REST API server for programmatic access:

```bash
chronovista api start --port 8765    # Start server

# Example requests (requires prior auth login)
curl http://localhost:8765/api/v1/health
curl http://localhost:8765/api/v1/videos?limit=10
curl "http://localhost:8765/api/v1/search/segments?q=keyword"

# Interactive API docs
open http://localhost:8765/docs
```

## Development

```bash
# Install dev dependencies
poetry install --with dev

# Run tests
make test              # All tests
make test-cov          # With coverage (90% threshold)
make test-fast         # Quick run

# Code quality
make format            # black + isort
make lint              # ruff
make type-check        # mypy
make quality           # All checks

# Database
make db-upgrade        # Run migrations
make db-revision       # Create migration
```

### Frontend Development

The project includes a React frontend for web-based video browsing.

```bash
# Start both backend and frontend
make dev

# Or start individually
make dev-backend  # Port 8765
make dev-frontend # Port 8766
```

After modifying backend Pydantic models, regenerate the API client:

```bash
make generate-api
```

See [`frontend/README.md`](frontend/README.md) for detailed frontend documentation.

<details>
<summary>All Makefile Commands</summary>

```bash
make help              # Show all commands
make install-dev       # Dev dependencies
make install-all       # All dependencies
make shell             # Poetry shell
make clean             # Clean artifacts
make env-info          # Environment info
make dev-db-admin      # Start pgAdmin (localhost:8081)
```
</details>

<details>
<summary>Integration Testing</summary>

```bash
# Full setup
make dev-full-setup

# Authenticate (one-time)
poetry run chronovista auth login

# Run integration tests
poetry run pytest tests/integration/api/ -v

# Reset if needed
make dev-full-reset
```

Tests validate the complete flow: YouTube API -> Pydantic models -> Database persistence.
</details>

<details>
<summary>Troubleshooting</summary>

**"No module named mypy":**
```bash
poetry install --with dev
```

**Poetry not found:**
```bash
curl -sSL https://install.python-poetry.org | python3 -
export PATH="$HOME/.local/bin:$PATH"
```

**Virtual environment issues:**
```bash
poetry env info
poetry env remove python
poetry install
```
</details>

## Architecture

```
chronovista/
├── api/          # FastAPI REST API (routers, schemas, deps)
├── cli/          # Typer CLI commands
├── services/     # Business logic (rate-limited API, retry logic)
├── repositories/ # Async data access with composite keys
├── models/       # Pydantic models with validation
├── db/           # SQLAlchemy + Alembic migrations
└── auth/         # OAuth 2.0 with progressive scopes
```

**Key design decisions:**
- Async-first with full async/await implementation
- Type-safe Pydantic models throughout
- Repository pattern with composite key support
- Multi-environment testing (dev, test, integration)

See [System Architecture](src/chronovista/docs/architecture/system-architecture.md) for details.

## Roadmap

- [x] Topic Analytics (17 CLI commands)
- [x] Graph Visualization (DOT/JSON export)
- [x] Interactive CLI with Rich UI
- [x] Timestamp-based transcript queries
- [x] REST API (20+ endpoints)
- [x] Web frontend (React + Vite)
- [x] Video search and filtering UI
- [ ] ML-powered insights


## Contributing

1. Fork the repository
2. Create a feature branch
3. Run `make quality` before committing
4. Submit a pull request

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[AGPL-3.0](LICENSE)

## Links

- [Documentation](src/chronovista/docs/chronovista_PRD.md)
- [Issues](https://github.com/chronovista/chronovista/issues)
- [Discussions](https://github.com/chronovista/chronovista/discussions)
