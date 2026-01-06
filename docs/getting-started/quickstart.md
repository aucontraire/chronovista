# Quick Start

Get up and running with chronovista in minutes.

## Prerequisites

Before you begin, ensure you have:

- Python 3.11 or higher
- Poetry (dependency management)
- PostgreSQL or MySQL database
- YouTube Data API credentials
- Docker (optional, for database setup)

## Installation

### Option 1: Automated Setup (Recommended)

```bash
git clone https://github.com/chronovista/chronovista.git
cd chronovista

# Run automated setup script
./scripts/dev_setup.sh
```

### Option 2: Manual Setup

```bash
git clone https://github.com/chronovista/chronovista.git
cd chronovista

# Install Poetry if you haven't already
curl -sSL https://install.python-poetry.org | python3 -

# Install dependencies
poetry install
```

## Database Setup

=== "PostgreSQL (Docker)"

    ```bash
    docker run --name chronovista-db \
        -e POSTGRES_PASSWORD=dev \
        -p 5432:5432 \
        -d postgres:15
    ```

=== "PostgreSQL (Local)"

    ```bash
    createdb chronovista
    ```

=== "MySQL (Docker)"

    ```bash
    docker run --name chronovista-mysql \
        -e MYSQL_ROOT_PASSWORD=dev \
        -e MYSQL_DATABASE=chronovista \
        -p 3306:3306 \
        -d mysql:8
    ```

## Configuration

1. Copy the example environment file:

    ```bash
    cp .env.example .env
    ```

2. Edit `.env` with your settings:

    ```env
    YOUTUBE_API_KEY=your_youtube_api_key_here
    YOUTUBE_CLIENT_ID=your_oauth_client_id_here
    YOUTUBE_CLIENT_SECRET=your_oauth_client_secret_here
    DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/chronovista
    SECRET_KEY=your_secret_key_here
    ```

3. Initialize the database:

    ```bash
    poetry run alembic upgrade head
    ```

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
2. Select **YouTube and YouTube Music**
3. Download and extract the archive
4. Import to chronovista:

```bash
chronovista takeout seed /path/to/your/takeout --progress
```

## Next Steps

- [Installation Guide](installation.md) - Detailed installation options
- [Configuration](configuration.md) - All configuration options
- [CLI Overview](../user-guide/cli-overview.md) - Complete command reference
- [Google Takeout Guide](../user-guide/google-takeout.md) - Full Takeout integration
