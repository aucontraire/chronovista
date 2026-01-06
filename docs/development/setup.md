# Development Setup

Complete guide to setting up the development environment.

## Prerequisites

- Python 3.11 or higher
- Poetry
- Docker (for database)
- Git

## Quick Setup

```bash
# Clone and enter directory
git clone https://github.com/chronovista/chronovista.git
cd chronovista

# Run automated setup
./scripts/dev_setup.sh
```

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

### 5. Verify Setup

```bash
# Check environment
make info

# Run tests
make test
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
