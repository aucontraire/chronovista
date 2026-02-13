# Installation

Complete installation guide for chronovista.

## System Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| Python | 3.11 | 3.12 |
| Node.js (frontend) | 20.x LTS | 22.x LTS |
| Memory | 2GB | 4GB+ |
| Storage | 1GB | 10GB+ (for transcripts) |
| Database | PostgreSQL 13 / MySQL 8 | PostgreSQL 15 |

!!! note "Node.js for Frontend"
    Node.js is only required if you want to use the web frontend. The CLI works without Node.js.

## Python Version Management

We recommend using [pyenv](https://github.com/pyenv/pyenv) for Python version management.

### Install pyenv

=== "macOS"

    ```bash
    brew install pyenv
    echo 'eval "$(pyenv init -)"' >> ~/.zshrc
    source ~/.zshrc
    ```

=== "Linux"

    ```bash
    curl https://pyenv.run | bash
    echo 'export PATH="$HOME/.pyenv/bin:$PATH"' >> ~/.bashrc
    echo 'eval "$(pyenv init -)"' >> ~/.bashrc
    source ~/.bashrc
    ```

### Install Python

```bash
pyenv install 3.12.2
pyenv local 3.12.2
```

## Poetry Installation

chronovista uses [Poetry](https://python-poetry.org/) for dependency management.

```bash
curl -sSL https://install.python-poetry.org | python3 -

# Add to PATH
export PATH="$HOME/.local/bin:$PATH"

# Verify installation
poetry --version
```

## Installing chronovista

### From Source (Development)

```bash
git clone https://github.com/chronovista/chronovista.git
cd chronovista

# Configure Poetry to use your Python version
poetry env use ~/.pyenv/versions/3.12.2/bin/python

# Install all dependencies
poetry install

# Install with optional groups
poetry install --with dev       # Development tools
poetry install --with nlp       # NLP features (spaCy, keyBERT)
poetry install --with database  # Database drivers
poetry install --with dev,nlp,database  # Everything
```

### Using the Makefile

```bash
# Show all available commands
make help

# Install dev dependencies
make install-dev

# Install all optional groups
make install-all
```

## Database Setup

### PostgreSQL with Docker (Recommended)

The project includes Docker Compose configuration for development:

```bash
# Start development database
make dev-db-up

# Run migrations
make dev-migrate

# Check status
make dev-db-status
```

The development database runs on port 5434 to avoid conflicts with local PostgreSQL.

### PostgreSQL Local Installation

=== "macOS"

    ```bash
    brew install postgresql@15
    brew services start postgresql@15
    createdb chronovista
    ```

=== "Ubuntu/Debian"

    ```bash
    sudo apt update
    sudo apt install postgresql postgresql-contrib
    sudo -u postgres createdb chronovista
    ```

### MySQL Setup

=== "Docker"

    ```bash
    docker run --name chronovista-mysql \
        -e MYSQL_ROOT_PASSWORD=dev \
        -e MYSQL_DATABASE=chronovista \
        -p 3306:3306 \
        -d mysql:8
    ```

=== "Local"

    ```bash
    mysql -u root -p -e "CREATE DATABASE chronovista;"
    ```

## YouTube API Setup

See the dedicated [YouTube API Setup](youtube-api-setup.md) guide for the complete walkthrough, including:

- Creating a Google Cloud project
- Configuring the OAuth consent screen (required before creating credentials)
- Creating an API key
- Creating OAuth 2.0 credentials
- Adding yourself as a test user

## Environment Configuration

Create your `.env` file:

```bash
cp .env.example .env
```

Edit with your credentials (see [YouTube API Setup](youtube-api-setup.md) for how to obtain these):

```env
# YouTube API Configuration
YOUTUBE_API_KEY=your_api_key
YOUTUBE_CLIENT_ID=your_client_id
YOUTUBE_CLIENT_SECRET=your_client_secret

# Use development database (Docker Compose on port 5434)
DEVELOPMENT_MODE=true

# Security (generate a random string for production use)
SECRET_KEY=your_secure_random_key
```

!!! important "Credentials come from environment variables"
    chronovista reads `YOUTUBE_CLIENT_ID` and `YOUTUBE_CLIENT_SECRET` from your `.env` file. It does **not** use the `client_secret.json` file that Google Cloud Console offers for download. See [YouTube API Setup](youtube-api-setup.md#step-6-add-credentials-to-env) for details.

!!! note "Database URLs"
    The `.env.example` has pre-configured database URLs. When using the Docker Compose development database, set `DEVELOPMENT_MODE=true` to use `DATABASE_DEV_URL` (port 5434). The `DATABASE_URL` (port 5432) is for a local or production PostgreSQL instance.

## Verifying Installation

```bash
# Check CLI is working
chronovista --version

# Check application status
chronovista status

# Run tests to verify everything works
make test
```

## Troubleshooting

### Poetry Not Found

```bash
# Check installation
which poetry

# Reinstall if needed
curl -sSL https://install.python-poetry.org | python3 -

# Add to PATH permanently
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

### Virtual Environment Issues

```bash
# Check Poetry environment
poetry env info

# Remove and recreate
poetry env remove python
poetry install
```

### Database Connection Issues

```bash
# Check PostgreSQL is running
pg_isready -h localhost -p 5432

# Check Docker containers
docker ps

# View logs
make dev-db-logs
```

### Missing Dependencies

```bash
# Install all dependencies at once
make install-all

# Or selectively
make install-dev
make install-nlp
make install-db
```

## Frontend Setup (Optional)

The web frontend provides a browser-based interface for browsing your video library.

### Prerequisites

- Node.js 22.x LTS or 20.x LTS
- npm 10.x or higher

### Install Node.js

=== "macOS"

    ```bash
    # Using Homebrew
    brew install node@22

    # Or using nvm
    nvm install 22
    nvm use 22
    ```

=== "Linux"

    ```bash
    # Using nvm (recommended)
    curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
    source ~/.bashrc
    nvm install 22
    nvm use 22
    ```

### Install Frontend Dependencies

```bash
cd frontend
npm install
cd ..
```

### Start Development Servers

```bash
# Start both backend and frontend
make dev

# Or start individually
make dev-backend  # Port 8765
make dev-frontend # Port 8766
```

Open http://localhost:8766 to access the web interface.

### Regenerate API Client

After modifying backend Pydantic models:

```bash
make generate-api
```

See [`frontend/README.md`](../frontend/README.md) for detailed frontend documentation.

## Next Steps

- [Configuration](configuration.md) - Detailed configuration options
- [Quick Start](quickstart.md) - Get started using chronovista
- [Development Setup](../development/setup.md) - Set up for contributing
