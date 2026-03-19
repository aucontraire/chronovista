# Migrating from Native to Docker

**For users who already have a running native chronovista setup and want to switch to the containerized version.**

## What Changes

The application runs inside Docker containers instead of a native Python environment. Everything else stays the same:

- **Same database**: PostgreSQL 15
- **Same API**: FastAPI on port 8765
- **Same web UI**: React frontend served by FastAPI
- **Same CLI**: All `chronovista` commands available via `make docker-shell`

Docker is for **using** chronovista. Native Python is for **developing** chronovista. The `chronovista auth` commands are the one exception — they must always run natively because the OAuth flow requires a browser redirect to `localhost` on your machine.

| Command | Where | Why |
|---------|-------|-----|
| `chronovista auth login/logout/status` | **Host (natively)** | Browser redirect needs host access |
| All other `chronovista` commands | **Container** (`make docker-shell`) | Full stack runs inside Docker |
| `make docker-*` commands | **Host** | Docker management |
| `make dev`, `make test`, `make quality` | **Host (natively)** | Development workflow |

## Prerequisites

- Docker with Compose v2 installed (`docker compose version`)
- Your existing `.env` file with YouTube API credentials

## Before You Start

Back up your current database:

```bash
pg_dump -h localhost -p 5434 -U dev_user chronovista_dev > backup.sql
```

This creates a full SQL dump of your native development database. You can restore it into the Docker database later if needed.

## Migration Steps

### 1. Ensure `.env` has YouTube credentials

Your `.env` file should contain your Google OAuth client ID and secret. The Docker container reads this file at startup.

### 2. Place Google Takeout exports in `./takeout/`

Copy or move your YouTube Takeout data into the `./takeout/` directory at the project root. The container mounts this directory read-only.

### 3. Start the containerized stack

For first-time setup (validates prerequisites, builds, starts, health check):

```bash
make docker-setup
```

Or if you've already built the image:

```bash
make docker-up
```

This starts a fresh PostgreSQL instance and the chronovista application container. Alembic migrations run automatically on startup.

### 4. Open the onboarding page

Navigate to `http://localhost:8765/onboarding` and follow the 4-step pipeline:

1. **Seed Reference Data** -- loads topic categories and reference tables
2. **Load Data Export** -- imports your Takeout data
3. **Enrich Metadata** -- fetches video/channel/playlist details from the YouTube API
4. **Normalize Tags** -- runs tag normalization (canonical tags, aliases)

### 5. Run CLI commands

CLI commands run inside the application container. Use `make docker-shell` for an interactive bash session:

```bash
make docker-shell
# Inside container:
chronovista videos list --limit 10
chronovista entities scan --channel "somechannel"
```

Or run individual commands directly:

```bash
docker exec -it chronovista-app chronovista videos list --limit 10
```

## Restoring Your Backup (Optional)

If you want to restore data from your native database into the Docker database instead of re-running the full onboarding pipeline:

```bash
# Start just PostgreSQL
docker compose up -d postgres

# Restore the backup into the Docker database
docker exec -i chronovista-postgres psql -U chronovista -d chronovista < backup.sql

# Start the full stack
make docker-up
```

**Important**: Restoring a backup replaces the Docker database data. Do this **before** running onboarding, or after `make docker-clean` to wipe the named volume and start fresh.

## Running Both

The native development setup (`docker-compose.dev.yml`, port 5434) and the full-stack Docker setup (`docker-compose.yml`, port 8765) are independent. You can run both simultaneously without conflicts:

- Native dev database: `localhost:5434`
- Docker full-stack: `localhost:8765` (API + UI)

## Data Persistence

| Data | Storage | Details |
|------|---------|---------|
| Database | Docker named volume (`chronovista-data`) | Survives `docker compose down`; destroyed by `docker compose down -v` |
| OAuth token | Bind mount `./data/youtube_token.json` | Persists on host filesystem |
| Takeout exports | Bind mount `./takeout/` (read-only) | Stays on host; container reads but never modifies |
| Image cache | Bind mount `./cache/` | Shared between host and container |

## Adding New Data

1. Drop new Takeout exports into the `./takeout/` directory
2. Refresh the onboarding page at `http://localhost:8765/onboarding`
3. Click **Start** on the **Load Data** step

The pipeline detects new data by comparing the takeout directory modification time against the most recent video `created_at` timestamp.

## Makefile Commands

| Command | Description |
|---------|-------------|
| `make docker-setup` | First-time setup: validates prereqs, builds, starts, health check |
| `make docker-up` | Start the stack |
| `make docker-down` | Stop the stack |
| `make docker-restart` | Stop and restart the stack |
| `make docker-build` | Rebuild the Docker image |
| `make docker-logs` | Stream application logs |
| `make docker-status` | Show container status and health |
| `make docker-shell` | Open bash shell inside the app container |
| `make docker-db-shell` | Open psql shell in the Docker PostgreSQL |
| `make docker-clean` | Stop stack and remove volumes (destroys DB data) |

## Troubleshooting

### Orphan containers warning

```
WARNING: Found orphan containers (chronovista-dev-postgres-1)
```

This is safe to ignore. It appears when you have containers from `docker-compose.dev.yml` running alongside `docker-compose.yml`. Add `--remove-orphans` to suppress:

```bash
docker compose up -d --remove-orphans
```

### Slow enrichment start

The **Enrich Metadata** step may take a moment to begin if you have a large video table. The initial query scans for unenriched videos before starting API calls.

### Image proxy 404s on first load

Thumbnail images are fetched on demand by the image cache proxy. The first page load may show broken images. Reload the page -- subsequent requests serve from the local cache.
