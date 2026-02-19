# API Error Responses

> **Version**: 1.0.0
> **Last Updated**: 2026-02-05
> **RFC**: [RFC 7807 - Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc7807)

## Overview

The Chronovista API uses **RFC 7807 Problem Details** for all error responses, providing a standardized, machine-readable format that enables consistent error handling across clients.

### Key Benefits

- **Standardized Format**: All errors follow the same structure
- **Machine-Readable**: Clients can programmatically handle errors using the `code` field
- **Human-Readable**: The `detail` field provides actionable context
- **Request Correlation**: Every response includes an `X-Request-ID` header for debugging
- **Content Type**: All errors return `Content-Type: application/problem+json`

---

## Error Response Structure

All error responses conform to this structure:

```json
{
  "type": "https://api.chronovista.com/errors/{ERROR_CODE}",
  "title": "Short Error Summary",
  "status": 404,
  "detail": "Human-readable explanation specific to this occurrence",
  "instance": "/api/v1/path/to/resource",
  "code": "ERROR_CODE",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Field Reference

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | URI | Yes | Problem type identifier. Links to error documentation. |
| `title` | string | Yes | Short, human-readable summary of the problem type. |
| `status` | integer | Yes | HTTP status code (duplicated for logging convenience). |
| `detail` | string | Yes | Human-readable explanation specific to this occurrence. |
| `instance` | URI | Yes | URI reference of the request that caused the error. |
| `code` | string | Yes | Application-specific error code for programmatic handling. |
| `request_id` | string | Yes | Unique correlation ID (UUID v4 or client-provided). |
| `errors` | array | No | Field-level validation errors (only for 422 responses). |

---

## X-Request-ID Header

Every API response includes an `X-Request-ID` header for request correlation and debugging.

### Server-Generated ID

When no client ID is provided, the server generates a UUID v4:

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890

{"status": "healthy"}
```

### Client-Provided ID

Clients can provide their own correlation ID, which will be echoed back:

```bash
curl -i -H "X-Request-ID: my-trace-123" http://localhost:8765/api/v1/health
```

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-ID: my-trace-123

{"status": "healthy"}
```

### ID Requirements

- Maximum length: 128 characters
- Invalid or empty IDs are replaced with server-generated UUIDs
- IDs are included in both response headers and error response bodies

---

## Error Codes

The `code` field contains one of these application-specific error codes:

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `NOT_FOUND` | 404 | Resource does not exist |
| `BAD_REQUEST` | 400 | Malformed request syntax |
| `VALIDATION_ERROR` | 422 | Request parameters failed validation |
| `NOT_AUTHENTICATED` | 401 | Authentication required |
| `NOT_AUTHORIZED` | 403 | Insufficient permissions |
| `FORBIDDEN` | 403 | Access denied (legacy code) |
| `CONFLICT` | 409 | Resource state conflict |
| `MUTUALLY_EXCLUSIVE` | 400 | Incompatible parameters provided |
| `RATE_LIMITED` | 429 | Too many requests |
| `INTERNAL_ERROR` | 500 | Unexpected server error |
| `DATABASE_ERROR` | 500 | Database operation failed |
| `EXTERNAL_SERVICE_ERROR` | 502 | External service (YouTube API) unavailable |
| `SERVICE_UNAVAILABLE` | 503 | Service temporarily unavailable |

---

## Error Response Examples

### 404 Not Found

Resource does not exist in the database:

```bash
curl -s http://localhost:8765/api/v1/videos/nonexistent | jq
```

```json
{
  "type": "https://api.chronovista.com/errors/NOT_FOUND",
  "title": "Resource Not Found",
  "status": 404,
  "detail": "Video 'nonexistent' not found",
  "instance": "/api/v1/videos/nonexistent",
  "code": "NOT_FOUND",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### 422 Validation Error

Request parameters failed validation. Includes an `errors` array with field-level details:

```bash
curl -s "http://localhost:8765/api/v1/videos?limit=500" | jq
```

```json
{
  "type": "https://api.chronovista.com/errors/VALIDATION_ERROR",
  "title": "Validation Error",
  "status": 422,
  "detail": "Request validation failed",
  "instance": "/api/v1/videos",
  "code": "VALIDATION_ERROR",
  "request_id": "550e8400-e29b-41d4-a716-446655440000",
  "errors": [
    {
      "loc": ["query", "limit"],
      "msg": "ensure this value is less than or equal to 100",
      "type": "value_error.number.not_le"
    }
  ]
}
```

**Validation Error Fields:**

| Field | Type | Description |
|-------|------|-------------|
| `loc` | array | Location path to the error (e.g., `["query", "limit"]`) |
| `msg` | string | Human-readable error message |
| `type` | string | Pydantic error type identifier |

### 401 Authentication Required

OAuth token missing or invalid:

```bash
curl -s http://localhost:8765/api/v1/sync/videos -X POST | jq
```

```json
{
  "type": "https://api.chronovista.com/errors/NOT_AUTHENTICATED",
  "title": "Authentication Required",
  "status": 401,
  "detail": "Valid OAuth token required. Run: chronovista auth login",
  "instance": "/api/v1/sync/videos",
  "code": "NOT_AUTHENTICATED",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### 403 Not Authorized

User lacks required permissions:

```bash
curl -s http://localhost:8765/api/v1/admin/users | jq
```

```json
{
  "type": "https://api.chronovista.com/errors/NOT_AUTHORIZED",
  "title": "Access Denied",
  "status": 403,
  "detail": "Insufficient permissions for this operation",
  "instance": "/api/v1/admin/users",
  "code": "NOT_AUTHORIZED",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### 429 Rate Limited

API rate limit exceeded. Check the `Retry-After` header:

```bash
curl -si http://localhost:8765/api/v1/sync/videos -X POST
```

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/problem+json
X-Request-ID: 550e8400-e29b-41d4-a716-446655440000
Retry-After: 60

{
  "type": "https://api.chronovista.com/errors/RATE_LIMITED",
  "title": "Rate Limit Exceeded",
  "status": 429,
  "detail": "API rate limit exceeded. Please retry after 60 seconds.",
  "instance": "/api/v1/sync/videos",
  "code": "RATE_LIMITED",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### 500 Internal Server Error

Unexpected server error. Internal details are logged server-side:

```json
{
  "type": "https://api.chronovista.com/errors/INTERNAL_ERROR",
  "title": "Internal Server Error",
  "status": 500,
  "detail": "An unexpected error occurred. Please try again later.",
  "instance": "/api/v1/sync/videos",
  "code": "INTERNAL_ERROR",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### 409 Conflict (Recovery Endpoints)

Attempting to recover an entity that is currently available:

```bash
curl -s -X POST http://localhost:8765/api/v1/videos/dQw4w9WgXcQ/recover | jq
```

```json
{
  "type": "https://api.chronovista.com/errors/CONFLICT",
  "title": "Resource Conflict",
  "status": 409,
  "detail": "Cannot recover an available video",
  "instance": "/api/v1/videos/dQw4w9WgXcQ/recover",
  "code": "CONFLICT",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

The same applies for channel recovery (`POST /api/v1/channels/{channel_id}/recover`).

### 503 Service Unavailable (Recovery Endpoints)

The Wayback Machine CDX API is temporarily unavailable during a recovery request. Includes a `Retry-After` header:

```bash
curl -si -X POST http://localhost:8765/api/v1/videos/dQw4w9WgXcQ/recover
```

```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json
Retry-After: 60

{
  "detail": "Wayback Machine CDX API unavailable: Connection timeout"
}
```

### 502 External Service Error

External service (e.g., YouTube API) unavailable:

```json
{
  "type": "https://api.chronovista.com/errors/EXTERNAL_SERVICE_ERROR",
  "title": "External Service Error",
  "status": 502,
  "detail": "External service unavailable",
  "instance": "/api/v1/sync/videos",
  "code": "EXTERNAL_SERVICE_ERROR",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

---

## Client Integration

### Python (httpx)

```python
import httpx

async def fetch_video(video_id: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"http://localhost:8765/api/v1/videos/{video_id}",
            headers={"X-Request-ID": "my-trace-id"}
        )

        if response.status_code >= 400:
            content_type = response.headers.get("content-type", "")
            if "application/problem+json" in content_type:
                problem = response.json()
                print(f"Error: {problem['title']}")
                print(f"Detail: {problem['detail']}")
                print(f"Request ID: {problem['request_id']}")
                raise Exception(f"API Error: {problem['code']}")

        return response.json()
```

### JavaScript (fetch)

```javascript
async function fetchVideo(videoId) {
  const response = await fetch(
    `http://localhost:8765/api/v1/videos/${videoId}`,
    {
      headers: {
        'X-Request-ID': 'my-trace-id'
      }
    }
  );

  if (!response.ok) {
    const contentType = response.headers.get('content-type') || '';
    if (contentType.includes('application/problem+json')) {
      const problem = await response.json();
      console.error(`Error: ${problem.title}`);
      console.error(`Detail: ${problem.detail}`);
      console.error(`Request ID: ${problem.request_id}`);
      throw new Error(`API Error: ${problem.code}`);
    }
  }

  return response.json();
}
```

---

## Debugging with Request IDs

### Finding Logs

Server logs include `request_id` for correlation:

```bash
grep "550e8400-e29b-41d4-a716-446655440000" /var/log/chronovista/api.log
```

### Reporting Issues

When reporting API issues, include the `request_id` from the error response:

```
Issue: Video sync failed unexpectedly

Request ID: 550e8400-e29b-41d4-a716-446655440000
Endpoint: POST /api/v1/sync/videos
Time: 2026-02-05T14:30:00Z
Error Code: INTERNAL_ERROR
```

---

## Success Responses

Success responses (2xx) are unchanged. Only the `X-Request-ID` header is added:

```bash
curl -i http://localhost:8765/api/v1/videos?limit=1
```

```http
HTTP/1.1 200 OK
Content-Type: application/json
X-Request-ID: a1b2c3d4-e5f6-7890-abcd-ef1234567890

{
  "data": [...],
  "pagination": {
    "total": 1234,
    "limit": 1,
    "offset": 0
  }
}
```

---

## Related Documentation

- [RFC 7807 Migration Guide](./rfc7807-migration.md) - Migrating from legacy error format
