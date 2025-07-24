#!/bin/bash

# Setup script for ChronoVista integration test database
# This creates a separate database in the existing development container

set -e

echo "🏗️  Setting up ChronoVista integration test database..."

# Check if Docker is running
if ! docker info >/dev/null 2>&1; then
    echo "❌ Docker is not running!"
    echo ""
    echo "Please start Docker Desktop first:"
    echo "1. Open Docker Desktop application"
    echo "2. Wait for Docker to start (you'll see the whale icon in your menu bar)"
    echo "3. Run this script again"
    echo ""
    echo "Alternative: Start Docker from command line:"
    echo "   open -a Docker"
    exit 1
fi

# Check if development database container is running
if ! docker ps --format "{{.Names}}" | grep -q "chronovista-postgres-dev"; then
    echo "📦 Starting development database container..."
    docker compose -f docker-compose.dev.yml up postgres-dev -d
    
    # Wait for database to be ready
    echo "⏳ Waiting for database to be ready..."
    sleep 5
fi

# Create integration test database
echo "🗄️  Creating integration test database..."
docker exec chronovista-postgres-dev psql -U dev_user -d chronovista_dev -c "
    CREATE DATABASE chronovista_integration_test;
" 2>/dev/null || echo "   Database already exists (that's fine!)"

# Run database migrations to create tables
echo "📋 Running database migrations to create tables..."
export DATABASE_URL="postgresql+asyncpg://dev_user:dev_password@localhost:5434/chronovista_integration_test"
export CHRONOVISTA_INTEGRATION_DB_URL="postgresql+asyncpg://dev_user:dev_password@localhost:5434/chronovista_integration_test"

# Use alembic to create tables - override the URL in alembic.ini
poetry run alembic -x database_url="postgresql://dev_user:dev_password@localhost:5434/chronovista_integration_test" upgrade head

echo "✅ Integration test database setup complete!"
echo ""
echo "📋 Database Configuration:"
echo "   - Host: localhost"
echo "   - Port: 5434 (mapped from container's 5432)"
echo "   - User: dev_user"
echo "   - Database: chronovista_integration_test"
echo "   - URL: postgresql+asyncpg://dev_user:dev_password@localhost:5434/chronovista_integration_test"
echo ""
echo "🚀 You can now run integration tests:"
echo "   poetry run pytest tests/integration/api/ -v"
echo ""
echo "💡 Note: Tables created via Alembic migrations"
echo "   If you need to reset the database, drop and recreate it:"
echo "   docker exec chronovista-postgres-dev psql -U dev_user -d chronovista_dev -c \"DROP DATABASE IF EXISTS chronovista_integration_test;\""
echo "   Then run this script again."