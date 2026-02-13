# Troubleshooting

Consolidated troubleshooting guide for common issues across all chronovista subsystems.

## Authentication

### "Access blocked: This app's request is invalid"

Your OAuth consent screen is not configured in Google Cloud Console.

**Fix:** Follow [YouTube API Setup - Step 3](getting-started/youtube-api-setup.md#step-3-configure-the-oauth-consent-screen).

### "Error 403: access_denied"

Your Google account is not listed as a test user.

**Fix:** In Google Cloud Console, go to **APIs & Services** > **OAuth consent screen** > **Test users** and add your email.

### "Error: redirect_uri_mismatch"

The redirect URI in your Google Cloud Console doesn't match the one chronovista uses.

**Fix:** Add `http://localhost:8080/auth/callback` (exactly, with `http://` not `https://`) to your OAuth client's authorized redirect URIs.

### "Invalid credentials" or "Client ID not found"

The `YOUTUBE_CLIENT_ID` or `YOUTUBE_CLIENT_SECRET` in your `.env` doesn't match your Google Cloud credentials.

**Fix:**
1. Go to Google Cloud Console > **Credentials**
2. Click your OAuth client ID
3. Copy the Client ID and Client Secret
4. Update `.env` with the correct values

### Token file not found

chronovista stores OAuth tokens in `./data/youtube_token.json` (relative to the project root, controlled by `DATA_DIR` in `.env`).

**Fix:** Run `chronovista auth login` to create a new token.

### Callback URL not being captured

The `chronovista auth login` flow requires you to manually copy the callback URL from your browser and paste it into the terminal.

**Fix:** After clicking "Allow" in the browser, copy the entire URL from your browser's address bar (starts with `http://localhost:8080/auth/callback?...`) and paste it at the `Callback URL:` prompt in your terminal.

## Database

### "Connection refused" on port 5434

The Docker development database is not running.

**Fix:**
```bash
# Check if Docker is running
docker ps

# Start the development database
make dev-db-up
```

### "Connection refused" on port 5432

You're connecting to a local PostgreSQL instance that isn't running, or you're using the wrong database URL.

**Fix:** If using the Docker development database, set `DEVELOPMENT_MODE=true` in `.env` to use port 5434 instead of 5432.

### Migration errors

**Fix:**
```bash
# Check current migration state
make dev-db-status

# Reset and re-apply all migrations
make dev-db-reset
make dev-migrate
```

### "database chronovista_integration_test does not exist"

The integration test database hasn't been created.

**Fix:**
```bash
make dev-full-setup
```

### Wrong database being used

`DEVELOPMENT_MODE` in `.env` controls which database URL is used:

| `DEVELOPMENT_MODE` | Database URL used | Typical port |
|---------------------|-------------------|-------------|
| `false` (default) | `DATABASE_URL` | 5432 |
| `true` | `DATABASE_DEV_URL` | 5434 |

**Fix:** Set `DEVELOPMENT_MODE=true` in `.env` when using the Docker development database.

## CLI

### "No module named chronovista"

The package isn't installed in your current environment.

**Fix:**
```bash
poetry install
poetry run chronovista --version
```

### "Poetry not found"

Poetry isn't in your PATH.

**Fix:**
```bash
export PATH="$HOME/.local/bin:$PATH"
# Add this line to ~/.zshrc or ~/.bashrc for permanence
```

### Commands hang or timeout

API rate limits may be exceeded, or network issues.

**Fix:**
```bash
# Check auth status
chronovista auth status

# Try a smaller sync
chronovista sync topics  # Fast, single API call
```

## Frontend

### Frontend shows "Network Error" or blank page

The backend API is not running.

**Fix:**
```bash
# Start the backend
make dev-backend

# Then start the frontend
make dev-frontend

# Or start both at once
make dev
```

### TypeScript errors after backend changes

The generated API client is out of date.

**Fix:**
```bash
# Ensure backend is running first
make dev-backend

# Regenerate the API client
make generate-api
```

### `npm install` fails

**Fix:**
```bash
# Make sure you're in the frontend directory
cd frontend

# Clear cache and reinstall
rm -rf node_modules package-lock.json
npm install
```

## Tests

### Backend tests fail with database errors

The development database isn't running or migrations aren't applied.

**Fix:**
```bash
make dev-db-up
make dev-migrate
```

### Integration tests fail with "not authenticated"

Integration tests require YouTube API authentication.

**Fix:**
```bash
poetry run chronovista auth login
make test-integration
```

### Coverage unexpectedly low

Async tests may be getting skipped instead of run. Check for `pytestmark = pytest.mark.asyncio` in test files.

**Fix:** Ensure test files with async tests include:
```python
pytestmark = pytest.mark.asyncio
```

### Frontend tests fail

**Fix:**
```bash
cd frontend
npm install  # Ensure dependencies are installed
npm test     # Run tests
```

## Transcripts

### "Could not retrieve transcript" errors

YouTube may have temporarily blocked your IP after too many rapid requests.

**Fix:** Wait 24 hours for the block to expire (for residential IPs). For future syncs, use smaller batches.

### Transcript language not available

Not all videos have transcripts in all languages.

**Fix:** Check available languages:
```bash
chronovista transcript languages VIDEO_ID
```

## Docker

### Docker Compose errors

**Fix:**
```bash
# Check Docker is running
docker info

# Verify compose file exists
ls docker-compose.dev.yml

# Try with explicit file
docker compose -f docker-compose.dev.yml up -d postgres-dev
```

### Port 5434 already in use

**Fix:**
```bash
# Find what's using the port
lsof -i :5434

# Stop existing containers
make dev-db-down
```

## See Also

- [Prerequisites](getting-started/prerequisites.md) - Required software
- [YouTube API Setup](getting-started/youtube-api-setup.md) - Google Cloud configuration
- [Installation](getting-started/installation.md) - Setup guide
- [Database Development](development/database.md) - Database workflow
