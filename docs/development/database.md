# Database Development

Database development workflow and best practices.

## Development Database

chronovista uses Docker for local database development.

### Quick Commands

```bash
# Start database
make dev-db-up

# Check status
make dev-db-status

# View logs
make dev-db-logs

# Database shell
make dev-db-shell

# Reset database
make dev-db-reset
```

### Connection Details

| Setting | Value |
|---------|-------|
| Host | localhost |
| Port | 5434 |
| Database | chronovista_dev |
| Username | dev_user |
| Password | dev_password |

Connection string:
```
postgresql://dev_user:dev_password@localhost:5434/chronovista_dev
```

## Migrations

### Alembic Configuration

The project has **two** Alembic configuration files:

| Config File | Used by | Target Database |
|-------------|---------|-----------------|
| `alembic.ini` | `make db-upgrade`, `make db-revision` | Production/local (`DATABASE_URL`, port 5432) |
| `alembic-dev.ini` | `make dev-migrate`, `make dev-revision` | Docker dev (`DATABASE_DEV_URL`, port 5434) |

!!! warning "Use the correct config"
    When working with the Docker development database, always use `make dev-migrate` and `make dev-revision` (which use `alembic-dev.ini`). Using `make db-upgrade` would target the production database URL instead.

### Running Migrations

```bash
# Apply all migrations
make dev-migrate

# Rollback one migration
poetry run alembic downgrade -1

# Reset to beginning
poetry run alembic downgrade base
```

### Creating Migrations

```bash
# Auto-generate from model changes
make dev-revision

# Manual migration
poetry run alembic revision -m "description"
```

### Migration Best Practices

1. **Always review auto-generated migrations**
2. **Test both upgrade and downgrade**
3. **Keep migrations atomic**
4. **Include data migrations when needed**

## Three-Phase Development

### Phase 1: Model Prototyping

Use in-memory database for rapid iteration:

```python
# During prototyping
engine = create_async_engine("sqlite+aiosqlite:///:memory:")
async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)
```

Benefits:
- No migration pollution
- Instant resets
- Fast iteration

### Phase 2: Development Migrations

Create and test migrations:

```bash
# Create migration
make dev-revision

# Test upgrade
make dev-migrate

# Test downgrade
poetry run alembic downgrade -1
```

### Phase 3: Production Migrations

Apply tested migrations to production:

```bash
poetry run alembic upgrade head
```

## Schema Management

### SQLAlchemy Models

```python
from sqlalchemy import Column, String, Integer, ForeignKey
from sqlalchemy.orm import relationship

class Video(Base):
    __tablename__ = "videos"

    video_id = Column(String(20), primary_key=True)
    channel_id = Column(String(24), ForeignKey("channels.channel_id"))
    title = Column(String, nullable=False)
    duration = Column(Integer, nullable=False)

    channel = relationship("Channel", back_populates="videos")
```

### Pydantic Models

```python
from pydantic import BaseModel

class Video(BaseModel):
    video_id: str
    channel_id: str
    title: str
    duration: int

    class Config:
        from_attributes = True
```

## pgAdmin

Visual database management:

```bash
# Start pgAdmin
make dev-db-admin

# Access at
# URL: http://localhost:8081
# Email: dev@example.com
# Password: dev_password
```

## Integration Test Database

Separate database for integration tests:

```bash
# Setup integration database
make dev-full-setup

# Reset integration database
make test-integration-reset
```

Connection:
```
postgresql://dev_user:dev_password@localhost:5434/chronovista_integration_test
```

## Troubleshooting

### Connection Refused

```bash
# Check Docker is running
docker ps

# Start database
make dev-db-up
```

### Port Conflict

Default port is 5434 to avoid conflicts. If still conflicting:

```bash
# Find what's using the port
lsof -i :5434

# Change port in docker-compose.dev.yml
```

### Migration Conflicts

```bash
# Reset development database
make dev-db-reset

# Re-run migrations
make dev-migrate
```

### Stale Schema

```bash
# Full reset
make dev-full-reset
```

## Best Practices

1. **Never modify production migrations**
2. **Test migrations on fresh database**
3. **Use transactions in migrations**
4. **Keep development database expendable**
5. **Use factories for test data**

## See Also

- [Setup](setup.md) - Development environment
- [Testing](testing.md) - Database testing
- [Data Model](../architecture/data-model.md) - Schema design
