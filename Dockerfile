# ==============================================================================
# Stage 1: dependency-builder — Export Poetry dependencies to requirements.txt
# ==============================================================================
FROM python:3.11-slim AS dependency-builder

RUN pip install --no-cache-dir poetry==1.8.5

WORKDIR /build

COPY pyproject.toml poetry.lock ./

# Export base dependencies (excluding dev, docs, recovery groups)
RUN poetry export -f requirements.txt --without dev,docs,recovery --output requirements.txt

# Optionally include NLP dependencies
ARG INCLUDE_NLP=false
RUN if [ "$INCLUDE_NLP" = "true" ]; then \
      poetry export -f requirements.txt --without dev,docs,recovery --with nlp --output requirements.txt; \
    fi

# ==============================================================================
# Stage 2: frontend-builder — Build Vite/React frontend
# ==============================================================================
FROM node:20-alpine AS frontend-builder

WORKDIR /app/frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

# Same-origin API in production — use relative path prefix only
ENV VITE_API_BASE_URL="/api/v1"

RUN npm run build

# ==============================================================================
# Stage 3: runtime — Final production image
# ==============================================================================
FROM python:3.11-slim AS runtime

# Install postgresql-client for pg_isready in entrypoint
RUN apt-get update && \
    apt-get install -y --no-install-recommends postgresql-client && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY --from=dependency-builder /build/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir psycopg2-binary

# Copy application source and project metadata for installation
COPY src/ ./src/
COPY pyproject.toml README.md ./
ENV PYTHONPATH="/app/src"

# Install the chronovista package (registers CLI entry point)
RUN pip install --no-cache-dir --no-deps -e .

# Copy Alembic configuration and migrations
COPY alembic.ini ./alembic.ini
COPY src/chronovista/db/migrations/ ./src/chronovista/db/migrations/

# Copy built frontend static assets
COPY --from=frontend-builder /app/frontend/dist ./static/

# Copy and prepare entrypoint
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh

EXPOSE 8765

ENTRYPOINT ["/app/entrypoint.sh"]
