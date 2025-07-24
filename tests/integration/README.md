# Integration Tests for ChronoVista YouTube API Data Flow

This directory contains comprehensive integration tests that validate the complete data flow from YouTube API through Pydantic models to SQLAlchemy database persistence.

## 🏗️ Test Architecture

### Tier-Based Testing Strategy

The integration tests follow the model dependency hierarchy identified in the codebase analysis:

```
Tier 1 (Independent) → Tier 2 (Channel-Deps) → Tier 3 (Video Core) → Tier 4 (Video-Deps)
```

#### **Tier 1: Independent Models**
- `test_tier1_independent.py`
- Models: `Channel`, `UserLanguagePreference`, `TopicCategory`
- Tests: API authentication, basic CRUD operations, field validation

#### **Tier 2: Channel-Dependent Models**
- `test_tier2_channel_deps.py`
- Models: `ChannelKeyword`, `Playlist`
- Dependencies: Requires established `Channel` from Tier 1
- Tests: Keyword extraction, playlist management, channel relationships

#### **Tier 3: Video Core Models**
- `test_tier3_video_core.py`
- Models: `Video`, `VideoWithChannel`, `VideoSearchFilters`, `VideoStatistics`
- Dependencies: Requires established `Channel` from Tier 1/2
- Tests: Complex video metadata, multi-language support, content analysis

#### **Tier 4: Video-Dependent Models**
- `test_tier4_video_deps.py` (to be implemented)
- Models: `VideoTranscript`, `VideoTag`, `VideoLocalization`, `UserVideo`
- Dependencies: Requires established `Video` from Tier 3
- Tests: Transcript download, quality indicators, user interactions

## 🚀 Running the Tests

### Prerequisites

1. **Database Setup**: The integration tests will use your existing development database container but with a separate database name. Make sure your development database is running:
   ```bash
   # Start the development database container
   docker-compose -f docker-compose.dev.yml up postgres-dev -d
   ```
   
   The integration tests will automatically use the `DATABASE_INTEGRATION_URL` from your `.env` file, which connects to:
   - **Port 5434** on your MacBook (avoiding conflicts with port 5432)
   - **Same Docker container** as your dev database
   - **Separate database name**: `chronovista_integration_test`

2. **YouTube API Credentials**: Set up OAuth credentials for YouTube API access:
   ```bash
   # Run authentication flow first
   poetry run python -m chronovista.cli.auth_commands login
   ```

3. **Environment Variables**:
   ```bash
   # Skip API tests if credentials not available
   export CHRONOVISTA_SKIP_API_TESTS=true  # Optional: to skip API-dependent tests
   ```

### Running Test Tiers

```bash
# Run all integration tests
poetry run pytest tests/integration/ -v

# Run specific tiers
poetry run pytest tests/integration/api/test_tier1_independent.py -v
poetry run pytest tests/integration/api/test_tier2_channel_deps.py -v
poetry run pytest tests/integration/api/test_tier3_video_core.py -v

# Run with specific markers
poetry run pytest -m "integration and api" -v
poetry run pytest -m "integration and not api" -v  # Skip API tests

# Run with custom pytest config
poetry run pytest -c pytest-integration.ini tests/integration/ -v
```

### Test Data Management

The tests use a combination of:
- **Real YouTube Data**: Stable, well-known channels and videos for consistent testing
- **Sample IDs**: Pre-defined channel/video IDs that are unlikely to be deleted
- **Test Isolation**: Each test tier can run independently with proper fixtures

## 📊 Test Coverage Areas

### **API Integration Points**
- ✅ YouTube Data API v3 authentication
- ✅ Channel information retrieval
- ✅ Video metadata fetching
- ✅ Playlist data synchronization
- 🔄 Transcript download (Tier 4)
- 🔄 Multi-language content handling (Tier 4)

### **Model Validation**
- ✅ Pydantic model validation with real API data
- ✅ Field constraints and business rules
- ✅ BCP-47 language code validation
- ✅ YouTube-specific data formats (IDs, durations, etc.)

### **Database Persistence**
- ✅ SQLAlchemy model creation and updates  
- ✅ Foreign key relationships
- ✅ Composite primary keys
- ✅ Timestamp management (created_at, updated_at)

### **Data Flow Integrity**
- ✅ API → Pydantic → SQLAlchemy transformation
- ✅ Complex metadata preservation
- ✅ Multi-language support
- 🔄 Error handling and graceful degradation (Resilience tests)

## 🛡️ Error Handling & Resilience

The framework includes provisions for testing real-world scenarios:

- **API Rate Limits**: Exponential backoff and retry logic
- **Network Failures**: Connection timeout and recovery
- **Data Inconsistencies**: Missing fields, malformed responses
- **Authentication Issues**: Token expiration, scope limitations
- **Content Restrictions**: Age-restricted, region-blocked content

## 🔧 Configuration

### Test Database
Integration tests use a separate database to avoid conflicts with development data:
```python
CHRONOVISTA_INTEGRATION_DB_URL = "postgresql+asyncpg://postgres:password@localhost:5432/chronovista_integration_test"
```

### Fixtures
- `authenticated_youtube_service`: Provides authenticated YouTube API client
- `established_channel`: Creates a channel for dependent tests
- `established_videos`: Creates videos for video-dependent tests
- `integration_db_session`: Database session with transaction rollback

### Sample Data
- **Channels**: Rick Astley, Google Developers, Stephen Colbert (stable, diverse content)
- **Videos**: Never Gonna Give You Up, Google I/O presentations, popular tech reviews
- **Languages**: English, Spanish, French, Chinese (multi-language testing)

## 📈 Expected Outcomes

Running these integration tests validates:

1. **API Compatibility**: ChronoVista models work correctly with real YouTube API responses
2. **Data Integrity**: Complete data preservation through the pipeline
3. **Performance**: Reasonable response times for API operations
4. **Scalability**: Batch operations and bulk data handling
5. **Reliability**: Graceful handling of API limitations and errors

## 🚧 Next Steps

1. **Complete Tier 4**: Implement video-dependent model tests
2. **End-to-End Flow**: Complete pipeline from API to analytics
3. **Performance Testing**: Load testing with large datasets
4. **Error Scenarios**: Comprehensive failure mode testing
5. **Monitoring Integration**: Test metrics and logging functionality

This integration test framework provides comprehensive validation of ChronoVista's core functionality with real YouTube data, ensuring robustness and reliability in production environments.