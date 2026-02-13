# Development Setup

Complete guide to setting up the development environment.

## Prerequisites

- Python 3.11 or higher
- Poetry
- Docker (with Docker Compose — **required** for the development database)
- Git
- Node.js 22.x LTS (optional, for the web frontend)

See [Prerequisites](../getting-started/prerequisites.md) for installation instructions.

## Quick Setup

```bash
# Clone and enter directory
git clone https://github.com/chronovista/chronovista.git
cd chronovista

# Run automated setup
./scripts/dev_setup.sh
```

!!! warning "About `dev_setup.sh`"
    The setup script assumes you have `pyenv` installed and uses Python 3.12.2. If you use a different Python version manager or a different Python version, follow the [Manual Setup](#manual-setup) instead.

## Manual Setup

### 1. Install Poetry

```bash
curl -sSL https://install.python-poetry.org | python3 -
export PATH="$HOME/.local/bin:$PATH"
```

### 2. Install Dependencies

```bash
# All development dependencies
poetry install --with dev

# Optional groups
poetry install --with dev,nlp,database
```

### 3. Setup Database

```bash
# Start Docker database
make dev-db-up

# Run migrations
make dev-migrate
```

### 4. Install Pre-commit Hooks

```bash
poetry run pre-commit install
```

### 5. Configure Environment

```bash
cp .env.example .env
# Edit .env with your YouTube API credentials
# Set DEVELOPMENT_MODE=true to use the Docker dev database
```

See [YouTube API Setup](../getting-started/youtube-api-setup.md) for obtaining credentials.

### 6. Verify Setup

```bash
# Check environment
make info

# Check database is running
make dev-db-status

# Run tests (unit tests don't require database)
make test-fast

# Run full test suite with coverage
make test-cov
```

## IDE Configuration

### PyCharm

1. Open project folder
2. Configure interpreter: Poetry environment
3. Enable mypy plugin
4. Set Black as formatter

### VS Code

Recommended extensions:

- Python
- Pylance
- Black Formatter
- mypy Type Checker

Settings:

```json
{
  "python.linting.mypyEnabled": true,
  "python.formatting.provider": "black",
  "editor.formatOnSave": true
}
```

## Environment Variables

Copy and configure:

```bash
cp .env.example .env
```

Required for full testing:

```env
YOUTUBE_API_KEY=your_key
YOUTUBE_CLIENT_ID=your_id
YOUTUBE_CLIENT_SECRET=your_secret
DATABASE_URL=postgresql+asyncpg://dev_user:dev_password@localhost:5434/chronovista_dev
```

## Common Issues

### Poetry Not Found

```bash
export PATH="$HOME/.local/bin:$PATH"
# Add to ~/.zshrc or ~/.bashrc
```

### Database Connection Failed

```bash
# Ensure Docker is running
docker ps

# Start database
make dev-db-up
```

### mypy Errors

```bash
# Install stubs
poetry run mypy --install-types
```

## Next Steps

- [Testing](testing.md) - Run the test suite
- [Database](database.md) - Database development
- [Code Style](code-style.md) - Formatting standards
- [Frontend Development](frontend-development.md) - Frontend setup and testing
- [Makefile Reference](makefile-reference.md) - All available make targets
