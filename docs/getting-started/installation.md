# Installation

Complete installation guide for chronovista.

## System Requirements

| Requirement | Minimum | Recommended |
|-------------|---------|-------------|
| Python | 3.11 | 3.12 |
| Memory | 2GB | 4GB+ |
| Storage | 1GB | 10GB+ (for transcripts) |
| Database | PostgreSQL 13 / MySQL 8 | PostgreSQL 15 |

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

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable YouTube Data API v3:
   - Navigate to "APIs & Services" > "Library"
   - Search for "YouTube Data API v3"
   - Click "Enable"
4. Create OAuth 2.0 credentials:
   - Navigate to "APIs & Services" > "Credentials"
   - Click "Create Credentials" > "OAuth client ID"
   - Select "Desktop application"
   - Download the credentials JSON
5. Configure redirect URI:
   - Add `http://localhost:8080/auth/callback`

## Environment Configuration

Create your `.env` file:

```bash
cp .env.example .env
```

Edit with your settings:

```env
# YouTube API Configuration
YOUTUBE_API_KEY=your_api_key
YOUTUBE_CLIENT_ID=your_client_id
YOUTUBE_CLIENT_SECRET=your_client_secret

# Database Configuration
DATABASE_URL=postgresql+asyncpg://user:password@localhost:5432/chronovista

# Security
SECRET_KEY=your_secure_random_key

# Optional: Logging
LOG_LEVEL=INFO
```

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

## Next Steps

- [Configuration](configuration.md) - Detailed configuration options
- [Quick Start](quickstart.md) - Get started using chronovista
- [Development Setup](../development/setup.md) - Set up for contributing
