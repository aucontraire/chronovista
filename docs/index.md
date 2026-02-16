# chronovista

**Personal YouTube data analytics tool for comprehensive access to your YouTube engagement history.**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Type Checked](https://img.shields.io/badge/mypy-strict-blue.svg)](https://mypy.readthedocs.io/)
[![Code Coverage](https://img.shields.io/badge/coverage-90%25+-green.svg)](https://coverage.readthedocs.io/)
[![License: AGPL-3.0](https://img.shields.io/badge/license-AGPL--3.0-orange.svg)](https://www.gnu.org/licenses/agpl-3.0)

## Overview

chronovista is a CLI application that enables users to access, store, and explore their personal YouTube account data using the YouTube Data API combined with Google Takeout integration. Built with modern Python architecture and comprehensive testing, it provides insights into watch history, playlists, video metadata, transcripts, and engagement data with a focus on data ownership and privacy.

## Key Features

<div class="grid cards" markdown>

-   :material-translate:{ .lg .middle } **Multi-Language Intelligence**

    ---

    Smart transcript management with language preferences for fluent, learning, and curious languages

-   :material-youtube:{ .lg .middle } **Channel Management**

    ---

    Track subscriptions, drill down into channel analytics, and discover content patterns

-   :material-lock:{ .lg .middle } **OAuth 2.0 Authentication**

    ---

    Secure login with progressive scope management for read/write operations

-   :material-chart-bar:{ .lg .middle } **Topic Analytics**

    ---

    Advanced topic classification with 17 CLI commands for content discovery and trend analysis

-   :material-database:{ .lg .middle } **Local Storage**

    ---

    All data stored locally in PostgreSQL/MySQL with complete data ownership

-   :material-file-export:{ .lg .middle } **Advanced Export**

    ---

    Language-aware export to CSV, JSON with filtering by channel and language

-   :material-api:{ .lg .middle } **REST API**

    ---

    FastAPI-powered REST API with 20+ endpoints for programmatic access to videos, transcripts, and search

-   :material-delete-restore:{ .lg .middle } **Deleted Video Recovery**

    ---

    Recover metadata for deleted/unavailable videos from the Wayback Machine with configurable date ranges and batch processing

</div>

## Project Status

!!! success "Current Status"
    - **5,500+ tests** (4,500+ backend, 1,500+ frontend) with **90%+ coverage**
    - **Comprehensive Pydantic models** with advanced validation and type safety
    - **Real API integration testing** with YouTube API data validation
    - **Advanced repository pattern** with async support and composite keys
    - **Rate-limited API service** with intelligent error handling and retry logic
    - **Wayback Machine recovery** for deleted/unavailable video metadata (v0.27.0)
    - **React frontend** with video browsing, transcript search, and deep link navigation (v0.6.0)

## Quick Example

=== "CLI Usage"

    ```bash
    # Authenticate with YouTube
    chronovista auth login

    # Sync your data
    chronovista sync all

    # Sync transcripts with timestamp preservation
    chronovista sync transcripts --dry-run  # Preview
    chronovista sync transcripts --limit 50  # Download

    # Explore topics
    chronovista topics list
    chronovista topics popular --metric videos

    # Analyze with Google Takeout
    chronovista takeout seed /path/to/takeout --progress
    ```

=== "Import from Takeout"

    ```bash
    # Seed database with complete takeout data
    chronovista takeout seed /path/to/your/takeout

    # Incremental seeding (safe to re-run)
    chronovista takeout seed /path/to/your/takeout --incremental

    # Preview what will be imported
    chronovista takeout seed /path/to/your/takeout --dry-run
    ```

=== "REST API"

    ```bash
    # Start the API server
    chronovista api start --port 8765

    # Health check (no auth)
    curl http://localhost:8765/api/v1/health

    # List videos (requires auth - shares CLI OAuth)
    curl http://localhost:8765/api/v1/videos?limit=10

    # Search transcripts
    curl "http://localhost:8765/api/v1/search/segments?q=keyword"

    # Interactive API docs
    open http://localhost:8765/docs
    ```

=== "Recover Deleted Videos"

    ```bash
    # Recover a specific deleted video
    chronovista recover video --video-id dQw4w9WgXcQ

    # Batch recover all unavailable videos
    chronovista recover video --all --limit 50

    # Focus on a specific archive era
    chronovista recover video --all --start-year 2018 --end-year 2020

    # Preview without making changes
    chronovista recover video --all --dry-run
    ```

## Architecture Highlights

chronovista implements a sophisticated **layered architecture** with modern Python patterns:

- **CLI Layer** - Typer-based interface with rich formatting and comprehensive error handling
- **REST API Layer** - FastAPI server with OAuth integration and OpenAPI documentation
- **Service Layer** - Rate-limited YouTube API integration with retry logic and batch processing
- **Repository Layer** - Advanced async repository pattern with composite keys and quality scoring
- **Data Layer** - Comprehensive Pydantic models with custom validators and type safety
- **Database Layer** - Multi-language PostgreSQL schema with optimized indexing

## Documentation Structure

| Section | Description |
|---------|-------------|
| [Getting Started](getting-started/quickstart.md) | Installation and first steps |
| [User Guide](user-guide/cli-overview.md) | Comprehensive usage documentation |
| [Architecture](architecture/overview.md) | System design and technical details |
| [API Reference](api/index.md) | Detailed API documentation |
| [Development](development/index.md) | Contributing and development setup |
| [Maintaining](maintaining/index.md) | Release process and maintenance |

## Technology Stack

| Layer | Technologies |
|-------|--------------|
| Language | Python 3.11+ |
| CLI Framework | Typer, Rich |
| API Framework | FastAPI, uvicorn |
| Database | PostgreSQL (async), SQLAlchemy, Alembic |
| Data Validation | Pydantic V2 |
| API Integration | google-api-python-client, google-auth |
| Testing | pytest, pytest-asyncio, hypothesis, factory-boy |
| Type Checking | mypy (strict mode) |
| Code Quality | ruff, black, isort |

## License

chronovista is licensed under the [GNU Affero General Public License v3.0](https://www.gnu.org/licenses/agpl-3.0).

## Acknowledgments

Built with:

- [Typer](https://typer.tiangolo.com/) - CLI framework
- [Rich](https://rich.readthedocs.io/) - Terminal formatting
- [Pydantic](https://docs.pydantic.dev/) - Data validation
- [SQLAlchemy](https://www.sqlalchemy.org/) - Database ORM
- [Google API Client](https://github.com/googleapis/google-api-python-client) - YouTube API access
