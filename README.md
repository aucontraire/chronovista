# chronovista

Personal YouTube data analytics tool for comprehensive access to your YouTube engagement history.

## Overview

chronovista is a CLI application that enables users to access, store, and explore their personal YouTube account data using the YouTube Data API. Built with modern Python architecture and comprehensive testing, it provides insights into watch history, playlists, video metadata, transcripts, and engagement data with a focus on data ownership and privacy.

### **Project Status**
- **1,365+ tests** with **90%+ coverage** across all modules
- **Comprehensive Pydantic models** with advanced validation and type safety
- **Real API integration testing** with YouTube API data validation
- **Advanced repository pattern** with async support and composite keys
- **Rate-limited API service** with intelligent error handling and retry logic

## Features

- **🌐 Multi-Language Intelligence** - Smart transcript management with language preferences for fluent, learning, and curious languages
- **📺 Channel Management** - Track subscriptions, drill down into channel analytics, and discover content patterns
- **🔐 OAuth 2.0 Authentication** - Secure login with progressive scope management for read/write operations
- **📊 Enhanced Watch History** - Complete watch history with channel filtering, language tracking, and rewatch analytics
- **📝 Smart Transcript Processing** - Intelligent multi-language transcript downloading based on user preferences
- **🏷️ Topic Analytics & Intelligence** - Advanced topic classification with 17 CLI commands for content discovery, trend analysis, and engagement scoring
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
- Docker (optional for database setup)

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

# Topic analytics
chronovista sync topics

# Full synchronization
chronovista sync all
```

### Google Takeout Integration

chronovista provides comprehensive Google Takeout integration, enabling you to both **analyze** and **import** your complete YouTube history into a local database for advanced analytics and insights.

#### **What is Google Takeout?**

Google Takeout is Google's data export service that lets you download a complete archive of your YouTube data, including:
- **Complete watch history** (including deleted videos with titles preserved)
- **All playlists** (including private ones) with full video relationships
- **Search history** with timestamps
- **Comments and live chat messages**
- **Channel subscriptions** with dates
- **Liked videos** and other interactions

#### **Getting Your Takeout Data**

1. Go to [Google Takeout](https://takeout.google.com/)
2. Select **YouTube and YouTube Music**
3. Choose your preferred format (JSON recommended)
4. Download and extract the archive
5. Use chronovista to analyze or import your data

#### **Database Seeding from Takeout**

Transform your Takeout data into a structured, queryable database with complete foreign key integrity and relationship management:

```bash
# Seed database with complete takeout data
chronovista takeout seed /path/to/your/takeout

# Incremental seeding (safe to re-run)
chronovista takeout seed /path/to/your/takeout --incremental

# Preview what will be imported (no database changes)
chronovista takeout seed /path/to/your/takeout --dry-run

# Seed specific data types only
chronovista takeout seed /path/to/your/takeout --only channels,videos
chronovista takeout seed /path/to/your/takeout --only playlists,playlist_memberships

# Skip certain data types
chronovista takeout seed /path/to/your/takeout --skip user_videos

# Monitor progress with detailed progress bars
chronovista takeout seed /path/to/your/takeout --progress
```

**What gets imported:**
- ✅ **Channels** - All channels from subscriptions, watch history, and playlists
- ✅ **Videos** - Complete video metadata with historical data preservation
- ✅ **User Videos** - Your personal watch history with timestamps
- ✅ **Playlists** - Playlist metadata and structure
- ✅ **Playlist Memberships** - Complete playlist-video relationships with position tracking
- ✅ **Data Quality** - Automatic cleanup of malformed data (925+ video IDs sanitized)
- ✅ **Foreign Key Integrity** - Proper dependency resolution and referential integrity

#### **Takeout Analysis Commands**

```bash
# Explore your takeout data structure
chronovista takeout peek /path/to/your/takeout --summary

# Analyze watch history patterns
chronovista takeout analyze /path/to/your/takeout --type viewing-patterns

# Discover channel relationships and subscriptions
chronovista takeout analyze /path/to/your/takeout --type channel-relationships

# Examine temporal viewing patterns
chronovista takeout analyze /path/to/your/takeout --type temporal-patterns

# Deep-dive into specific content types
chronovista takeout inspect /path/to/your/takeout --focus playlists
chronovista takeout inspect /path/to/your/takeout --focus comments
chronovista takeout inspect /path/to/your/takeout --focus searches

# Export analysis results
chronovista takeout analyze /path/to/your/takeout --export csv
chronovista takeout analyze /path/to/your/takeout --export json
```

#### **Why Takeout Analysis Matters**

**🔍 Complete Historical Data**: Unlike the YouTube API which has limitations, Takeout contains your *entire* YouTube history, including:
- Videos that have since been deleted or made private
- Historical data going back to when you first used YouTube
- Private playlists and unlisted content interactions
- Detailed timestamps for every interaction

**📊 Advanced Analytics**: chronovista's Takeout analysis provides insights like:
- **Viewing patterns over time** - See how your interests evolved
- **Channel relationship mapping** - Discover your subscription clusters
- **Content discovery paths** - How you found your favorite creators
- **Engagement analysis** - Your commenting and interaction patterns
- **Search behavior** - What you were looking for and when

**🔒 Privacy-First Exploration**: All analysis happens locally on your machine - your personal data never leaves your control.

#### **Example Analysis Output**

```bash
$ chronovista takeout analyze ./takeout --type viewing-patterns

📊 YouTube Viewing Pattern Analysis
════════════════════════════════════

📺 Total Videos Watched: 15,847
⏱️  Total Watch Time: 2,341 hours
📅 Date Range: 2012-03-15 to 2024-01-20
🎯 Most Active Period: 2020-2021 (pandemic era)

🔥 Top Content Categories:
   1. Technology & Programming (23.4%)
   2. News & Politics (18.7%)
   3. Educational Content (15.2%)
   4. Entertainment (12.8%)

📈 Viewing Trends:
   • Peak viewing hours: 7-9 PM
   • Most active day: Sunday
   • Average session: 47 minutes
   • Binge-watching sessions: 234
```

#### **Integration with API Data**

chronovista can **combine** your Takeout data with live YouTube API data for the most complete picture:

```bash
# Option 1: Seed Takeout data first, then sync API data
chronovista takeout seed /path/to/takeout
chronovista sync all  # Enriches seeded data with current API information

# Option 2: Sync API data first, then import Takeout data
chronovista sync all
chronovista takeout seed /path/to/takeout --incremental  # Adds historical data

# Option 3: Combined analysis without database import
chronovista takeout integrate /path/to/takeout --merge-with-api

# This gives you:
# ✅ Current data from API (up-to-date metrics, current video status)
# ✅ Historical data from Takeout (deleted videos, old metadata, complete playlists)
# ✅ Complete timeline reconstruction with relationship integrity
# ✅ Queryable database for advanced analytics and insights
```

**Benefits of Database Seeding:**
- 🏗️ **Structured Storage** - Query your data with SQL for complex analytics
- 🔗 **Relationship Mapping** - Complete playlist-video relationships with position tracking  
- 📊 **Advanced Analytics** - Join watch history with playlist memberships and channel data
- 🔍 **Historical Preservation** - Deleted videos and historical metadata preserved permanently
- ⚡ **Performance** - Fast queries on indexed, structured data vs. parsing files repeatedly

### Topic Analytics

```bash
# Explore topics
chronovista topics list              # View all available topics
chronovista topics popular           # Most popular topics by content
chronovista topics videos 10         # Videos in Music category
chronovista topics related 25        # Topics related to News & Politics

# Advanced analytics
chronovista topics chart             # Visual topic popularity chart
chronovista topics explore           # Interactive topic exploration
chronovista topics trends            # Topic popularity over time 
```

### Application Status

```bash
# Check application status
chronovista status

# Show version
chronovista --version
```

## 🚦 Transcript Download Rate Limiting

### Understanding the Fallback Strategy

The transcript service uses a three-tier fallback approach to maximize success rates:

1. **youtube-transcript-api (Primary)** - Web scraping approach
   - ✅ Works for most public videos
   - ✅ No quota limits
   - ⚠️ Subject to IP-based rate limiting
   
2. **YouTube Data API v3 (Secondary)** - Official Google API  
   - ✅ Reliable and quota-based
   - ✅ No IP-based restrictions
   - ❌ Only works for videos you own or with explicit third-party permissions
   
3. **Mock Transcript (Fallback)** - For testing/development
   - ✅ Prevents script failures
   - ⚠️ Not real content

### Rate Limiting Guidelines

**youtube-transcript-api Limits:**
```python
# Recommended limits to avoid IP bans
MAX_REQUESTS_PER_HOUR = 50-100
MIN_DELAY_BETWEEN_REQUESTS = 5  # seconds
DAILY_LIMIT = 300-500  # requests per IP
```

**Signs you're hitting limits:**
- `RequestBlocked` exceptions
- `IpBlocked` exceptions  
- Videos that should have transcripts returning "not found"

**Mitigation strategies:**
```bash
# Add delays between requests
time.sleep(5)  # Add to your scripts

# Use residential proxies for high-volume usage
# See proxy configuration section below

# Monitor error rates and back off automatically
# Implement exponential backoff in your code
```

**Official API Limits:**
- **Daily quota**: 10,000 units (captions.list = 50 units, captions.download = 200 units)
- **No IP-based restrictions** - only quota-based
- **Request quota increases** via Google Cloud Console if needed

### Proxy Configuration (For High-Volume Usage)

If you're processing many videos and hitting IP blocks, consider using proxy services:

**Recommended Proxy Services:**
- **Webshare** (Most reliable, official integration): $40-80/mo
- **Residential Proxy Services**: $50-100/mo  
- **Premium VPN with rotation**: $15-30/mo

**Integration Example:**
```python
from youtube_transcript_api.proxies import WebshareProxyConfig

# Configure proxy for high-volume usage
proxy_config = WebshareProxyConfig(
    proxy_username="your-username",
    proxy_password="your-password",
    filter_ip_locations=["us", "ca"]  # Reduce latency
)

# Apply to transcript service
transcript_service = TranscriptService(proxy_config=proxy_config)
```

**Budget Alternatives:**
- Start with request delays (free)
- Use VPN with manual server rotation ($15/mo)
- Self-hosted proxy infrastructure (advanced users)

### Production Usage Best Practices

For production environments processing many videos:

1. **Implement request delays**: Always add 5+ second delays between transcript requests
2. **Monitor error rates**: Track `RequestBlocked`/`IpBlocked` exceptions
3. **Use exponential backoff**: Automatically slow down when hitting limits
4. **Set up quota monitoring**: Track official API quota usage
5. **Consider proxy services**: For sustained high-volume usage (>100 requests/hour)

**Example rate-limited usage:**
```python
import time
import random

for video_id in video_ids:
    try:
        transcript = await transcript_service.get_transcript(video_id)
        # Random delay between 5-10 seconds
        await asyncio.sleep(random.uniform(5, 10))
    except (RequestBlocked, IpBlocked):
        # Exponential backoff on rate limit
        await asyncio.sleep(60)  # Wait 1 minute before retrying
```

## Documentation

### Topic Analytics & Intelligence

chronovista features a comprehensive **Topic Analytics System** with 17 specialized CLI commands for content discovery, trend analysis, and intelligent insights. Built with advanced mathematical algorithms including cosine similarity and Jaccard analysis.

📖 **[Complete Topic Integration Guide](src/chronovista/docs/topic-integration-guide.md)**

#### **🔍 Core Topic Commands**
```bash
# Basic topic exploration
chronovista topics list                    # List all topic categories with content counts
chronovista topics show <topic_id>         # Show detailed topic information
chronovista topics channels <topic_id>     # Show channels associated with a topic
chronovista topics videos <topic_id>       # Show videos associated with a topic

# Advanced analytics
chronovista topics popular --metric videos # Most popular topics by video count
chronovista topics related <topic_id>      # Find related topics through shared content
chronovista topics overlap <id1> <id2>     # Content overlap analysis between topics
chronovista topics similar <topic_id>      # Find similar topics using content patterns
```

#### **📊 Advanced Analytics & Visualizations**
```bash
# Visual analytics
chronovista topics chart --metric combined # ASCII bar charts of topic popularity
chronovista topics tree <topic_id>         # Hierarchical relationship trees
chronovista topics explore                 # Interactive topic exploration interface

# Trend analysis
chronovista topics trends --period monthly # Topic popularity trends over time
chronovista topics discovery               # How users discover topics
chronovista topics insights --user-id me   # Personalized topic recommendations

# Engagement metrics
chronovista topics engagement              # Topic engagement scoring
chronovista topics channel-engagement 25   # Channel performance by topic
```

#### **🕸️ Graph Visualization & Export**
```bash
# Export for visualization tools
chronovista topics graph --format dot      # Export DOT format for Graphviz
chronovista topics graph --format json     # Export JSON for D3.js/network tools
chronovista topics heatmap --period monthly # Generate temporal activity heatmaps
chronovista topics export --format csv     # Export topic data and associations
```

#### **🎯 Smart Filtering & Integration**
```bash
# Topic-aware sync operations
chronovista sync topics                     # Populate topic categories (32 categories)
chronovista sync liked --topic 10          # Only sync Music-related videos
chronovista sync channel --topic 25        # Only sync News & Politics channels

# Takeout integration with topics
chronovista takeout analyze --topic 27     # Analyze only Educational content
chronovista takeout peek --by-topic        # Group takeout analysis by topics
```

#### **🏆 Key Technical Features**
- **Mathematical Algorithms**: Cosine similarity for content patterns, Jaccard analysis for overlap
- **Interactive Components**: Multi-phase exploration workflows with Rich terminal UI
- **Graph Visualization**: Export to DOT (Graphviz) and JSON (D3.js) formats
- **Engagement Scoring**: Advanced metrics with tier classifications (High/Medium/Low)
- **Temporal Analysis**: Time-series trends with growth rate calculations
- **Performance Optimization**: Query caching, async processing, efficient indexing

#### **📈 Real-World Analytics Examples**
```bash
# Discover your content evolution
chronovista topics trends --direction growing  # Find your growing interests
chronovista topics insights --user-id your_id # Get personalized recommendations
chronovista topics similar 10                 # Find topics similar to Music

# Analyze relationships
chronovista topics overlap 25 22              # Compare News & Politics vs People & Blogs
chronovista topics tree 10 --max-depth 3      # Explore Music topic relationships

# Export for external analysis
chronovista topics graph --format json --min-confidence 0.2 --output my_graph.json
chronovista topics heatmap --period weekly --months-back 24 --output heatmap.json
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
make test              # Run all tests (including integration tests)
make test-cov          # Run tests with coverage (90% threshold)
make test-cov-dev      # Run tests with coverage (development-friendly)
make test-fast         # Quick test run
make test-integration  # Run integration tests only (requires YouTube API auth)
make test-integration-reset  # Reset integration test database (clean slate)

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

### Integration Testing with Real YouTube API Data

ChronoVista includes comprehensive integration tests that validate the complete data flow from YouTube API through Pydantic models to database persistence. These tests use real YouTube API data to ensure robustness in production.

#### **Quick Setup**
```bash
# 1. Setup everything (dev DB + integration test DB + migrations)
make dev-full-setup

# 2. Authenticate with YouTube API (one-time setup)
poetry run chronovista auth login

# 3. Run all tests including integration tests
make test

# Or run integration tests only:
poetry run pytest tests/integration/api/ -v

# If tests are failing due to stale database state, reset everything:
make dev-full-reset

# Or run specific test tiers
poetry run pytest tests/integration/api/test_tier1_independent.py -v    # Channel, UserLanguagePreference
poetry run pytest tests/integration/api/test_tier2_channel_deps.py -v   # ChannelKeyword, Playlist  
poetry run pytest tests/integration/api/test_tier3_video_core.py -v     # Video models
```

#### **Test Architecture**
The integration tests follow a **tier-based dependency hierarchy**:

- **Tier 1** (Independent): `Channel`, `UserLanguagePreference`, `TopicCategory`
- **Tier 2** (Channel-Dependent): `ChannelKeyword`, `Playlist`  
- **Tier 3** (Video Core): `Video`, `VideoStatistics`, `VideoSearchFilters`
- **Tier 4** (Video-Dependent): `VideoTranscript`, `VideoTag`, `VideoLocalization`, `UserVideo`

#### **What Gets Tested**
- ✅ **Real API Data**: Actual YouTube API responses with your authentication
- ✅ **Model Validation**: Pydantic models with real-world data constraints
- ✅ **Database Persistence**: Complete data flow from API → Models → Database
- ✅ **Multi-Language Support**: International content and BCP-47 language codes
- ✅ **Complex Metadata**: YouTube's rich data structures (ratings, restrictions, etc.)
- ✅ **Relationship Integrity**: Foreign keys, composite keys, and cascading operations

#### **Configuration**
Integration tests use a separate database to avoid conflicts:
- **Port**: 5434 (avoids conflict with your MacBook's port 5432)
- **Database**: `chronovista_integration_test` (separate from dev data)
- **Container**: Reuses your existing development PostgreSQL container

See [`tests/integration/README.md`](tests/integration/README.md) for comprehensive documentation and advanced usage.

## Architecture & Technical Highlights

chronovista implements a sophisticated **layered architecture** with modern Python patterns:

- **CLI Layer** - Typer-based interface with rich formatting and comprehensive error handling
- **Service Layer** - Rate-limited YouTube API integration with retry logic and batch processing
- **Repository Layer** - Advanced async repository pattern with composite keys and quality scoring
- **Data Layer** - Comprehensive Pydantic models with custom validators and type safety
- **Database Layer** - Multi-language PostgreSQL schema with optimized indexing

### 🏗️ **Technical Architecture**
- **Async-first design** - Full async/await implementation with proper session management
- **Type-safe models** - Comprehensive Pydantic hierarchy with 10+ core models
- **Composite key support** - Advanced database relationships with multi-column keys
- **Quality scoring system** - Intelligent transcript quality assessment with confidence metrics
- **Multi-environment testing** - Separate dev, test, and integration database environments

### 🧪 **Testing Infrastructure**
- **Real API integration** - Tests validate complete YouTube API → Database workflows
- **Factory pattern** - Comprehensive test data generation with factory-boy
- **Tiered testing** - Dependency-aware test architecture across 4 model tiers
- **Database automation** - Automated integration database reset and migration
- **Performance optimized** - 1,365 tests execute in ~20 seconds

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

GNU Affero General Public License v3.0 - see [LICENSE](LICENSE) for details.

## Support

- **Issues**: [GitHub Issues](https://github.com/chronovista/chronovista/issues)
- **Documentation**: [docs.chronovista.dev](https://docs.chronovista.dev)
- **Discussions**: [GitHub Discussions](https://github.com/chronovista/chronovista/discussions)

## Roadmap

- [x] **Topic Analytics & Intelligence** - 17 CLI commands with advanced analytics ✅
- [x] **Graph Visualization** - DOT/JSON export for external visualization tools ✅
- [x] **Interactive CLI Components** - Rich terminal UI with progress bars and workflows ✅
- [ ] Web dashboard interface
- [ ] Machine learning insights expansion
- [ ] Multi-user support
- [ ] Cloud deployment options
- [ ] API integrations with other platforms

## Status

=� **Alpha** - Initial development phase  
=� **Current**: Foundation and CLI setup  
<� **Next**: OAuth implementation and data synchronization