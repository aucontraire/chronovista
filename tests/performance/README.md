# Performance Tests

Performance tests for chronovista validating query response times and system scalability.

## Feature 007: Transcript Timestamp Preservation

### Success Criteria Being Validated

These tests validate the performance requirements for Feature 007:

- **SC-003**: Query by segment count <2s for 10,000 transcripts
- **SC-004**: Query by duration <2s for 10,000 transcripts
- **SC-005**: Query by timestamp availability <2s for 10,000 transcripts
- **SC-006**: Query by source <2s for 10,000 transcripts

### Test Coverage

**Tests T042-T048** in `test_transcript_query_performance.py`:

- **T042**: Create performance test fixtures (10,000 transcripts with varied metadata)
- **T043**: Test `has_timestamps` filter performance (SC-005)
- **T044**: Test `min_segment_count` filter performance (SC-003)
- **T045**: Test `min_duration` filter performance (SC-004)
- **T046**: Test `source` filter performance (SC-006)
- **T047**: Test combined filters with AND logic
- **T048**: Document comprehensive performance baseline results

## Requirements

### Database Setup

Performance tests require a **real PostgreSQL database** (not SQLite) to accurately measure query performance:

```bash
# Create integration test database
createdb chronovista_integration_test

# Set environment variable
export CHRONOVISTA_INTEGRATION_DB_URL="postgresql+asyncpg://user:password@localhost:5432/chronovista_integration_test"
```

Or use the default Docker compose setup:
```bash
docker-compose up -d postgres-test
# Default URL: postgresql+asyncpg://dev_user:dev_password@localhost:5434/chronovista_integration_test
```

### Environment Variables

- `CHRONOVISTA_INTEGRATION_DB_URL` - Database connection URL
- `DATABASE_INTEGRATION_URL` - Alternative database URL (fallback)

## Running Performance Tests

### Run All Performance Tests

```bash
# Run only performance tests
pytest tests/performance/ -v -m performance

# Run with detailed output
pytest tests/performance/ -v -m performance -s

# Run with coverage
pytest tests/performance/ -v -m performance --cov=chronovista.repositories.video_transcript_repository
```

### Skip Performance Tests

Performance tests are marked with `@pytest.mark.performance` and can be excluded:

```bash
# Run all tests EXCEPT performance tests
pytest -v -m "not performance"

# This is useful for regular CI/CD runs
```

### Run Specific Tests

```bash
# Run only baseline documentation test
pytest tests/performance/test_transcript_query_performance.py::TestTranscriptQueryPerformance::test_performance_baseline_documentation -v -s

# Run only has_timestamps performance test
pytest tests/performance/test_transcript_query_performance.py::TestTranscriptQueryPerformance::test_filter_has_timestamps_performance -v -s
```

## Test Execution Flow

### First Run (Cold Start)

On the first run, the tests will:

1. **Create 1,000 video records** (takes ~5-10 seconds)
2. **Create 10,000 transcript records** with varied metadata (takes ~30-60 seconds)
3. **Run performance queries** and measure response times
4. **Output comprehensive baseline results**

Total setup time: ~1-2 minutes

### Subsequent Runs (Warm Start)

On subsequent runs, the tests will:

1. **Detect existing test data** (videos and transcripts)
2. **Skip data creation** (instant)
3. **Run performance queries** immediately
4. **Output baseline results**

Total time: ~5-15 seconds

### Data Cleanup

Test data is **NOT** automatically cleaned up to allow repeated test runs. To clean up:

```bash
# Connect to database
psql chronovista_integration_test

# Delete performance test data
DELETE FROM video_transcripts WHERE video_id LIKE 'perf_test_%';
DELETE FROM videos WHERE video_id LIKE 'perf_test_%';
```

Or drop and recreate the database:
```bash
dropdb chronovista_integration_test
createdb chronovista_integration_test
```

## Interpreting Results

### Expected Output

```
================================================================================
PERFORMANCE BASELINE RESULTS - Feature 007
================================================================================
Test Dataset: 10000 transcripts
Performance Threshold: 2.0s
================================================================================

Query Filter                              Time (s)      Results    SC         Status
--------------------------------------------------------------------------------
has_timestamps=True                          0.045s       7500     SC-005     ✓ PASS
has_timestamps=False                         0.032s       2500     SC-005     ✓ PASS
min_segment_count>=100                       0.067s       4320     SC-003     ✓ PASS
max_segment_count<=50                        0.041s       1280     SC-003     ✓ PASS
min_duration>=1800s                          0.053s       3456     SC-004     ✓ PASS
max_duration<=600s                           0.039s       2134     SC-004     ✓ PASS
source='youtube_transcript_api'              0.048s       3333     SC-006     ✓ PASS
source='youtube_data_api_v3'                 0.046s       3333     SC-006     ✓ PASS
source='manual_upload'                       0.044s       3334     SC-006     ✓ PASS
Combined (4 filters)                         0.089s        876     Combined   ✓ PASS

================================================================================
SUMMARY
================================================================================
All queries: ✓ PASSED
Threshold: 2.0s
Average time: 0.050s
Fastest query: 0.032s (has_timestamps=False)
Slowest query: 0.089s (Combined (4 filters))
================================================================================
```

### Performance Thresholds

- **Target**: <2.0 seconds per query (success criteria)
- **Typical**: 0.03-0.10 seconds (PostgreSQL with proper indexes)
- **Warning**: >0.5 seconds (may indicate missing indexes)
- **Failure**: >2.0 seconds (violates success criteria)

### Common Performance Issues

1. **Missing Database Indexes**
   - Check that indexes exist on `has_timestamps`, `segment_count`, `total_duration`, `source`
   - Migration `007_add_transcript_timestamp_preservation.py` should create these

2. **Large Result Sets**
   - Tests use `limit=10000` to avoid memory issues
   - Reduce limit if experiencing OOM errors

3. **Database Connection**
   - Use connection pooling for better performance
   - Check `pool_pre_ping=True` in database configuration

4. **SQLite Performance**
   - SQLite is NOT suitable for performance testing
   - Always use PostgreSQL for accurate measurements

## CI/CD Integration

### GitHub Actions Example

```yaml
name: Performance Tests

on:
  schedule:
    - cron: '0 2 * * 0'  # Weekly on Sunday at 2 AM
  workflow_dispatch:  # Manual trigger

jobs:
  performance:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: chronovista_integration_test
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_password
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          pip install -e ".[test]"

      - name: Run performance tests
        env:
          CHRONOVISTA_INTEGRATION_DB_URL: postgresql+asyncpg://test_user:test_password@localhost:5432/chronovista_integration_test
        run: |
          pytest tests/performance/ -v -m performance -s
```

### Local Development

Add to your shell profile for convenience:

```bash
# ~/.bashrc or ~/.zshrc
alias pytest-perf='pytest tests/performance/ -v -m performance -s'
alias pytest-no-perf='pytest -v -m "not performance"'
```

## Troubleshooting

### Database Not Available

```
SKIPPED [1] Integration database not available at postgresql+asyncpg://...
```

**Solution**: Ensure PostgreSQL is running and connection URL is correct.

```bash
# Check PostgreSQL is running
pg_isready -h localhost -p 5432

# Test connection
psql -h localhost -p 5432 -U user -d chronovista_integration_test
```

### Slow First Run

```
[T042] Creating 10000 transcript records with varied metadata...
```

**Expected**: First run takes 1-2 minutes to seed data. This is normal.

**Solution**: Subsequent runs will be much faster (5-15 seconds) because test data is reused.

### Performance Test Failures

```
AssertionError: Query took 2.347s, exceeds 2.0s threshold (SC-005)
```

**Causes**:
1. Database indexes missing or not created
2. Database under heavy load
3. Hardware limitations (slow disk I/O)
4. Using SQLite instead of PostgreSQL

**Solutions**:
1. Verify indexes exist: `\d video_transcripts` in psql
2. Run on dedicated test database
3. Use SSD storage
4. Always use PostgreSQL for performance tests

### Out of Memory

```
MemoryError: Unable to allocate ...
```

**Solution**: Reduce `TARGET_RECORD_COUNT` or use batched processing:

```python
# In test_transcript_query_performance.py
TARGET_RECORD_COUNT = 5000  # Reduce from 10000
```

## Development Notes

### Test Data Characteristics

The performance test dataset includes:

- **10,000 transcripts** across 1,000 videos
- **10 languages**: en, es, fr, de, ja, ko, pt, it, ru, zh
- **3 transcript types**: AUTO, MANUAL, TRANSLATED
- **3 sources**: youtube_transcript_api, youtube_data_api_v3, manual_upload
- **Timestamp distribution**: ~75% with timestamps, ~25% without
- **Segment counts**: 5-500 segments (for transcripts with timestamps)
- **Durations**: 30-7200 seconds (for transcripts with timestamps)

### Adding New Performance Tests

To add a new performance test:

1. Add test method to `TestTranscriptQueryPerformance` class
2. Use `performance_transcripts` fixture to ensure data exists
3. Measure time with `time.perf_counter()`
4. Assert against `PERFORMANCE_THRESHOLD_SECONDS`
5. Print results in consistent format

Example:

```python
async def test_new_filter_performance(
    self,
    integration_db_session,
    repository: VideoTranscriptRepository,
    performance_transcripts: int,
):
    """Test new filter performance."""
    async with integration_db_session() as session:
        print(f"\n[TEST] Testing new_filter with {performance_transcripts} records...")

        start_time = time.perf_counter()
        results = await repository.filter_by_metadata(
            session,
            new_filter="value",
            limit=10000,
        )
        elapsed = time.perf_counter() - start_time

        print(f"[SC-XXX] ✓ new_filter query: {elapsed:.3f}s, {len(results)} results")

        assert elapsed < self.PERFORMANCE_THRESHOLD_SECONDS
```

## References

- **Feature Spec**: `specs/007-transcript-timestamp-preservation/spec.md`
- **Repository**: `src/chronovista/repositories/video_transcript_repository.py`
- **Database Models**: `src/chronovista/db/models.py`
- **Migration**: `alembic/versions/007_add_transcript_timestamp_preservation.py`
