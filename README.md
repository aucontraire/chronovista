# chronovista

Personal YouTube data analytics tool for comprehensive access to your YouTube engagement history.

## Overview

chronovista is a CLI-first application that enables users to access, store, and explore their personal YouTube account data using the YouTube Data API. It provides insights into watch history, playlists, video metadata, transcripts, and engagement data with a focus on data ownership and privacy.

## Features

- **🌐 Multi-Language Intelligence** - Smart transcript management with language preferences for fluent, learning, and curious languages
- **📺 Channel Management** - Track subscriptions, drill down into channel analytics, and discover content patterns
- **🔐 OAuth 2.0 Authentication** - Secure login with progressive scope management for read/write operations
- **📊 Enhanced Watch History** - Complete watch history with channel filtering, language tracking, and rewatch analytics
- **📝 Smart Transcript Processing** - Intelligent multi-language transcript downloading based on user preferences
- **🏷️ Content Intelligence** - Handle "made for kids" restrictions, region limitations, and content ratings automatically
- **💾 Local Storage** - All data including language preferences stored locally in PostgreSQL/MySQL
- **🚀 Write Operations** - Create playlists, like videos, subscribe to channels, and manage content (Phase 3)
- **📤 Advanced Export** - Language-aware export to CSV, JSON with filtering by channel and language
- **🔒 Privacy-First** - Complete data ownership with no cloud sync or language profiling

## Installation

### Prerequisites

- Python 3.11 or higher
- Poetry (dependency management)
- PostgreSQL or MySQL database
- YouTube Data API credentials

### Install from Source

#### Option 1: Automated Setup (Recommended)
```bash
git clone https://github.com/chronovista/chronovista.git
cd chronovista

# Run automated setup script
./scripts/dev_setup.sh
```

#### Option 2: Manual Setup
```bash
git clone https://github.com/chronovista/chronovista.git
cd chronovista

# Install Poetry if you haven't already
curl -sSL https://install.python-poetry.org | python3 -

# Ensure you have Python 3.12.2 and chronovista-env
pyenv install 3.12.2  # if not already installed
pyenv virtualenv 3.12.2 chronovista-env  # if not already created

# Configure Poetry to use chronovista-env
poetry env use ~/.pyenv/versions/3.12.2/envs/chronovista-env/bin/python

# Install dependencies
poetry install
```

### Database Setup

#### PostgreSQL (Recommended)
```bash
# Using Docker
docker run --name chronovista-db -e POSTGRES_PASSWORD=dev -p 5432:5432 -d postgres:15

# Or install locally
createdb chronovista
```

#### MySQL
```bash
# Using Docker
docker run --name chronovista-mysql -e MYSQL_ROOT_PASSWORD=dev -e MYSQL_DATABASE=chronovista -p 3306:3306 -d mysql:8

# Or install locally
mysql -u root -p -e "CREATE DATABASE chronovista;"
```

### Configuration

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

## Usage

### Authentication

```bash
# Login to your YouTube account
chronovista auth login

# Check authentication status
chronovista auth status

# Logout
chronovista auth logout
```

### Data Synchronization

```bash
# Sync watch history
chronovista sync history

# Sync playlists
chronovista sync playlists

# Sync transcripts
chronovista sync transcripts

# Full synchronization
chronovista sync all
```

### Application Status

```bash
# Check application status
chronovista status

# Show version
chronovista --version
```

## Development

### Setup Development Environment

```bash
# Install Poetry if you haven't already
curl -sSL https://install.python-poetry.org | python3 -

# Install all dependencies (including dev dependencies)
poetry install --with dev

# Install pre-commit hooks
poetry run pre-commit install

# Optional: Enter Poetry shell for development
poetry shell
```

### Using the Makefile (Recommended)

The project includes a comprehensive Makefile that works seamlessly with Poetry:

```bash
# Show all available commands
make help

# Setup development environment
make install-dev         # Install dev dependencies
make install-nlp         # Install NLP dependencies
make install-db          # Install database dependencies
make install-all         # Install all dependencies

# Code quality and formatting
make format             # Format code with black + isort
make lint              # Run linting with ruff
make type-check        # Run type checking with mypy
make quality           # Run all quality checks

# Testing
make test              # Run all tests
make test-cov          # Run tests with coverage (90% threshold)
make test-cov-dev      # Run tests with coverage (development-friendly)
make test-fast         # Quick test run

# Development
make run               # Show CLI help
make run-status        # Test CLI status command
make shell             # Enter Poetry shell
make clean             # Clean build artifacts
make info              # Show project information

# Database
make db-upgrade        # Run database migrations
make db-downgrade      # Rollback migrations
make db-revision       # Create new migration

# Environment management
make env-info          # Show virtual environment info
make deps-show         # Show installed dependencies
make deps-outdated     # Show outdated dependencies
```

### Manual Commands (Alternative)

If you prefer running commands manually with Poetry:

```bash
# Run all tests
poetry run pytest

# Run with coverage
poetry run pytest --cov=chronovista --cov-report=html

# Run specific test file
poetry run pytest tests/test_cli.py -v

# Format code
poetry run black src/chronovista/
poetry run isort src/chronovista/

# Type checking
poetry run mypy src/chronovista/

# Linting
poetry run ruff check src/chronovista/

# Run CLI commands
poetry run chronovista --help
poetry run chronovista status
```

### Quick Development Workflow

For the most common development tasks with Poetry:

```bash
# 1. Setup (one-time)
make install-dev      # Install all dev dependencies
# or: poetry install --with dev

# 2. Development workflow
make shell           # Enter Poetry shell (optional)
make format          # Format your code
make lint           # Check for issues
make test-cov-dev   # Run tests with coverage

# 3. Full quality check
make quality        # Run all quality checks

# 4. Database operations
make db-upgrade     # Apply migrations
make db-revision    # Create new migration

# 5. Quick testing
make test-fast      # Fast test run during development
make run           # Test CLI functionality

# 6. Environment management
make env-info      # Check environment status
make deps-show     # View installed packages
make deps-outdated # Check for updates
```

### Troubleshooting

**"No module named mypy" Error:**
```bash
# This usually means dev dependencies aren't installed
make install-dev     # Install all dev dependencies
# or manually:
poetry install --with dev
```

**Poetry Not Found:**
```bash
# Install Poetry
curl -sSL https://install.python-poetry.org | python3 -
# Add to PATH (check installer output for exact path)
export PATH="$HOME/.local/bin:$PATH"
```

**Virtual Environment Issues:**
```bash
# Check Poetry environment info
make env-info
# or manually:
poetry env info

# Remove and recreate environment if needed
poetry env remove python
poetry install
```

**Missing Dependencies:**
```bash
# Install all dependencies at once
make install-all     # Install main + dev + nlp + database
# or selectively:
make install-dev     # Just development dependencies
make install-nlp     # Just NLP dependencies
make install-db      # Just database dependencies
```

**pyenv + Poetry Issues:**
```bash
# Ensure Poetry uses the correct Python version
pyenv local 3.12.2  # Set local Python version
poetry env use python  # Use current Python for Poetry
poetry install       # Reinstall dependencies
```

## Architecture

chronovista follows a layered architecture pattern:

- **CLI Layer** - Typer-based command-line interface
- **Service Layer** - Business logic and API integration
- **Data Layer** - SQLAlchemy models and repositories
- **Database Layer** - PostgreSQL/MySQL storage

For detailed architecture information, see [System Architecture Document](src/chronovista/docs/architecture/system-architecture.md).

## Configuration

### Environment Variables

See `.env.example` for all available configuration options.

### Database Configuration

- **PostgreSQL**: `postgresql+asyncpg://user:password@localhost:5432/chronovista`
- **MySQL**: `mysql+aiomysql://user:password@localhost:3306/chronovista`

### YouTube API Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable YouTube Data API v3
4. Create credentials (OAuth 2.0 Client ID)
5. Add authorized redirect URIs: `http://localhost:8080/auth/callback`

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and quality checks
5. Submit a pull request

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Support

- **Issues**: [GitHub Issues](https://github.com/chronovista/chronovista/issues)
- **Documentation**: [docs.chronovista.dev](https://docs.chronovista.dev)
- **Discussions**: [GitHub Discussions](https://github.com/chronovista/chronovista/discussions)

## Roadmap

- [ ] Web dashboard interface
- [ ] Advanced analytics and visualizations
- [ ] Machine learning insights
- [ ] Multi-user support
- [ ] Cloud deployment options
- [ ] API integrations with other platforms

## Status

=� **Alpha** - Initial development phase  
=� **Current**: Foundation and CLI setup  
<� **Next**: OAuth implementation and data synchronization