# Quick Start

Get up and running with chronovista in minutes.

## Option 1: Docker (Recommended)

The fastest path — no Python or Node.js required.

**Prerequisites:** Docker with Compose, [YouTube Data API credentials](youtube-api-setup.md) (API key + OAuth client).

```bash
# Clone
git clone https://github.com/chronovista/chronovista.git
cd chronovista

# Configure
cp .env.example .env  # Add YouTube API credentials

# One-time OAuth setup (must run natively)
pip install chronovista  # or: poetry install
chronovista auth login

# Start the stack
make docker-setup
# Opens http://localhost:8765/onboarding
```

The guided onboarding wizard walks you through 4 steps: Seed Reference Data → Load Data Export → Enrich Metadata → Normalize Tags.

Run CLI commands inside the container:

```bash
make docker-shell          # Opens bash inside the container
chronovista videos list --limit 10
```

!!! note "What Runs Where"
    Docker is for **using** chronovista. The `chronovista auth` commands are the one exception — they must always run natively because the OAuth flow requires a browser redirect to `localhost` on your machine. Everything else runs inside the container via `make docker-shell`.

---

## Option 2: Native Development Setup

For contributors who want to develop chronovista locally.

### Prerequisites

- Python 3.11 or higher
- Poetry (dependency management)
- Docker (for the development database)
- YouTube Data API credentials (API key + OAuth client)

See [Prerequisites](prerequisites.md) for installation instructions and [YouTube API Setup](youtube-api-setup.md) for configuring Google Cloud credentials.

### Automated Setup

```bash
git clone https://github.com/chronovista/chronovista.git
cd chronovista

# Run automated setup script
./scripts/dev_setup.sh
```

### Manual Setup

```bash
git clone https://github.com/chronovista/chronovista.git
cd chronovista

# Install Poetry if you haven't already
curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies
poetry install
```

## Database Setup

The recommended approach uses Docker Compose, which runs PostgreSQL on port **5434** (to avoid conflicts with any local PostgreSQL):

```bash
# Start the development database
make dev-db-up

# Run database migrations
make dev-migrate
```

This creates a PostgreSQL database at `localhost:5434` with database `chronovista_dev`, user `dev_user`, password `dev_password`.

## Configuration

1. Copy the example environment file:

    ```bash
    cp .env.example .env
    ```

2. Edit `.env` with your YouTube credentials (see [YouTube API Setup](youtube-api-setup.md)):

    ```env
    YOUTUBE_API_KEY=your_youtube_api_key_here
    YOUTUBE_CLIENT_ID=your_oauth_client_id_here
    YOUTUBE_CLIENT_SECRET=your_oauth_client_secret_here
    ```

    !!! note "Database URL"
        When using the Docker Compose development database (recommended), set `DEVELOPMENT_MODE=true` in `.env`. This uses `DATABASE_DEV_URL` (port 5434) instead of `DATABASE_URL` (port 5432). The `.env.example` already has the correct dev URL pre-configured.

## First Steps

### Authenticate with YouTube

```bash
chronovista auth login
```

This will open a browser window for OAuth authentication.

### Check Status

```bash
chronovista auth status
```

### Sync Your Data

```bash
# Sync everything
chronovista sync all

# Or sync specific data types
chronovista sync topics      # Sync topic categories
chronovista sync playlists   # Sync your playlists
chronovista sync transcripts # Sync video transcripts
```

### Explore Topics

```bash
# List all topics
chronovista topics list

# View popular topics
chronovista topics popular

# Visual chart
chronovista topics chart
```

## Using Google Takeout

For complete historical data, import your Google Takeout:

1. Go to [Google Takeout](https://takeout.google.com/)
2. Deselect all, then check **YouTube and YouTube Music**
3. Click **"HTML format"** and change **history** to **JSON** (chronovista cannot import HTML)
4. If you're a content creator, click **"All YouTube data included"** and uncheck **videos** (avoids downloading your uploaded files)
5. Download and extract the archive
6. Import to chronovista:

```bash
chronovista takeout seed /path/to/your/takeout --progress
```

See the [Google Takeout Guide](../user-guide/google-takeout.md) for the full walkthrough with screenshots.

## Verify Everything Works

After completing the setup, run this quick smoke test:

```bash
# 1. Check CLI is working
chronovista --version

# 2. Check database connection
make dev-db-status

# 3. Authenticate with YouTube
chronovista auth login

# 4. Verify authentication
chronovista auth status

# 5. (Optional) Start the web frontend
cd frontend && npm install && cd ..
make dev  # Starts both backend (8765) and frontend (8766)
# Open http://localhost:8766
```

## Next Steps

- [Installation Guide](installation.md) - Detailed installation options
- [Configuration](configuration.md) - All configuration options
- [Data Population](../user-guide/data-population.md) - Recommended sync order
- [CLI Overview](../user-guide/cli-overview.md) - Complete command reference
- [Google Takeout Guide](../user-guide/google-takeout.md) - Full Takeout integration
