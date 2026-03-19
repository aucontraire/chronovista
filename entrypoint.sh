#!/bin/bash
set -e

echo "=== Chronovista Startup ==="

# Wait for database (safety net beyond depends_on healthcheck)
echo "Verifying database connection..."
until pg_isready -h postgres -p 5432 -U "${DB_USER:-chronovista}" -d chronovista -q; do
  echo "  Database not ready, waiting..."
  sleep 2
done
echo "  Database is ready."

# Run Alembic migrations
echo "Applying database migrations..."
cd /app
alembic -c alembic.ini upgrade head
echo "  Migrations complete."

# Start the application
echo "Starting Chronovista on port 8765..."
exec uvicorn chronovista.api.main:app \
  --host 0.0.0.0 \
  --port 8765 \
  --workers 1 \
  --log-level info
