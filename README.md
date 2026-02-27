<h1 align="center">chronovista</h1>

<p align="center">
  <strong>A CLI + web dashboard for your YouTube history. Sync watch history, search transcripts by timestamp, recover deleted videos, and explore 124,000+ canonical tags — all stored privately in local PostgreSQL.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-AGPL--3.0-green.svg" alt="License: AGPL-3.0">
  <img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+">
  <img src="https://img.shields.io/badge/tests-7,670+-brightgreen.svg" alt="Tests: 7,670+">
  <img src="https://img.shields.io/badge/coverage-72%25-yellow.svg" alt="Coverage: 74%">
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

<!-- TODO: Add a screenshot of the React dashboard or a terminal recording (vhs/asciinema) here -->

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
poetry run chronovista auth login
poetry run chronovista sync all
# Or activate the virtualenv first: poetry shell
```

## Features

Most YouTube data tools require cloud sync or third-party services. chronovista runs entirely on your machine: PostgreSQL stores everything, the REST API is local, and the React dashboard is served from localhost. Deleted video metadata can be recovered automatically from the Wayback Machine, and the tag normalization system groups 141,000+ raw tag variations into 124,000+ canonical forms with fuzzy search.

| Category | Capabilities |
|----------|-------------|
| **Local-First Privacy** | All data in local PostgreSQL — no cloud sync, complete data ownership |
| **Multi-Language Transcripts** | 50+ languages with personal preferences (fluent, learning, curious, exclude) |
| **Transcript Search** | Timestamp-based queries — find what was said at any moment, export as SRT |
| **Tag Intelligence** | 124K canonical tags with variation grouping, fuzzy search, and 7 curation CLI commands |
| **Channel Analytics** | Subscription tracking, keyword extraction, topic analysis |
| **Google Takeout** | Import complete YouTube history including deleted/private videos |
| **Deleted Video Recovery** | Recover metadata for unavailable videos via the Wayback Machine CDX API |
| **REST API + Web UI** | FastAPI server (20+ endpoints) with React dashboard for browsing and filtering |
| **Write Operations** | Create playlists, like videos, subscribe to channels via OAuth |
| **Export** | CSV/JSON with language-aware filtering |

### Tech Stack

- **Backend:** Python 3.11+, FastAPI, SQLAlchemy 2.0 (async), Alembic, Typer, Pydantic V2
- **Frontend:** React 19, TypeScript 5.7 (strict), TanStack Query v5, Tailwind CSS 4
- **Database:** PostgreSQL 15 via asyncpg
- **Auth:** Google OAuth 2.0 with progressive scope management

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

### Tag Management

```bash
chronovista tags merge mejico mexiko --into mexico   # Merge spelling variants
chronovista tags split mexico --aliases "Mexican"    # Split incorrectly merged tags
chronovista tags rename mexico --to "Mexico"         # Change display form
chronovista tags classify mexico --type place        # Assign entity type
chronovista tags collisions                          # Review diacritic collision candidates
chronovista tags undo OPERATION_ID                   # Reverse any operation
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

### Recover Deleted Videos

Recover metadata for deleted or unavailable videos from the [Wayback Machine](https://web.archive.org/):

```bash
chronovista recover video --video-id VIDEO_ID                # Single video
chronovista recover video --all --limit 50                   # Batch recover
chronovista recover video --all --dry-run                    # Preview changes
chronovista recover video --video-id VIDEO_ID --start-year 2018  # Anchor to era
```

<details>
<summary>Recovery Details</summary>

**What gets recovered:**
- Title, description, upload date, channel info
- Tags, category, thumbnail URL
- View count, like count

**How it works:**
- Queries the Wayback Machine CDX API for archived YouTube video pages
- Extracts metadata from JSON or HTML meta tags
- Three-tier overwrite policy protects existing data
- Results cached locally for 24 hours

**Options:**
- `--start-year` / `--end-year` — Focus search on a specific archive era
- `--delay` — Rate limiting between videos in batch mode (default: 1s)
- `--dry-run` — Preview without making database changes
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

### Web Frontend

```bash
make dev               # Start backend (8765) + frontend (8766)
open http://localhost:8766
```

The React dashboard provides video browsing with tag/category/topic filters, transcript search, playlist navigation, and deleted video visibility controls.

## Development

### Workflow

```bash
# Install dev dependencies
poetry install --with dev

# Start the full local stack
make dev               # Backend on :8765, frontend on :8766

# Before committing — run all checks
make quality           # format + lint + type-check
```

### Testing

```bash
make test              # All backend tests (5,493+)
make test-cov          # With coverage
make test-fast         # Quick run

# Frontend tests (2,177+)
cd frontend && npm test
```

### Code Quality

```bash
make format            # black + isort
make lint              # ruff
make type-check        # mypy (strict, 0 errors across 415+ source files)
```

### Database

```bash
make db-upgrade        # Run migrations
make db-revision       # Create new migration
```

### Frontend Development

```bash
make dev-backend       # Backend only (port 8765)
make dev-frontend      # Frontend only (port 8766)
make generate-api      # Regenerate TypeScript API client after backend model changes
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
├── api/              # FastAPI REST API: 20+ endpoints, RFC 7807 errors, rate limiting
├── cli/              # Typer CLI: 40+ commands (auth, sync, topics, recovery, tags)
├── services/         # Business logic: sync orchestration, tag normalization, recovery pipeline
│   └── recovery/     # Wayback Machine recovery: CDX client, HTML parser, orchestrator
├── repositories/     # Async SQLAlchemy DAL: all DB access, composite key support
├── models/           # Pydantic V2 domain models (separate from ORM models in db/)
├── db/               # SQLAlchemy ORM models + Alembic migrations
└── auth/             # OAuth 2.0 with progressive scope management
```

**Key design decisions:**
- Async-first with full async/await (asyncpg, httpx)
- Strict type safety: Pydantic V2 models + mypy strict mode
- Repository pattern isolating all database access
- Layered architecture: CLI/API -> Services -> Repositories -> DB

See [System Architecture](src/chronovista/docs/architecture/system-architecture.md) for details.

## Roadmap

- [ ] ML-powered content insights and recommendations
- [ ] Screenshot/terminal recording for README
- [ ] CI/CD pipeline with automated badge generation

## Contributing

1. Fork the repository
2. Create a feature branch
3. Run `make quality` before committing
4. Submit a pull request

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[AGPL-3.0](LICENSE)
