# RFC 7807 Migration Guide

> **Version**: 1.0.0
> **Last Updated**: 2026-02-05
> **Breaking Change**: Yes

## Summary

This guide documents the migration from the legacy error response format to the RFC 7807 Problem Details standard. This is a **breaking change** that affects all API clients.

### What Changed

| Aspect | Before | After |
|--------|--------|-------|
| Content-Type | `application/json` | `application/problem+json` |
| Response Structure | Custom nested format | RFC 7807 flat structure |
| Request Correlation | None | `X-Request-ID` header |
| Error Codes | Nested in `error.code` | Top-level `code` field |

---

## Before/After Examples

### 404 Not Found

**Before (Legacy Format):**

```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Video 'xyz' not found",
    "details": {
      "resource_type": "Video",
      "identifier": "xyz"
    }
  }
}
```

**After (RFC 7807 Format):**

```http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json
X-Request-ID: 550e8400-e29b-41d4-a716-446655440000

{
  "type": "https://api.chronovista.com/errors/NOT_FOUND",
  "title": "Resource Not Found",
  "status": 404,
  "detail": "Video 'xyz' not found",
  "instance": "/api/v1/videos/xyz",
  "code": "NOT_FOUND",
  "request_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

### 422 Validation Error

**Before (Legacy Format):**

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Validation failed",
    "details": {
      "fields": {
        "limit": "must be less than or equal to 100"
      }
    }
  }
}
```

**After (RFC 7807 Format):**

```http
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/problem+json
X-Request-ID: 550e8400-e29b-41d4-a716-446655440000

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

### 500 Internal Server Error

**Before (Legacy Format):**

```json
{
  "error": {
    "code": "INTERNAL_ERROR",
    "message": "An unexpected error occurred"
  }
}
```

**After (RFC 7807 Format):**

```http
HTTP/1.1 500 Internal Server Error
Content-Type: application/problem+json
X-Request-ID: 550e8400-e29b-41d4-a716-446655440000

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

---

## Client Migration

### Python (httpx)

**Before:**

```python
async def fetch_video(video_id: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://localhost:8765/api/v1/videos/{video_id}")

        if response.status_code >= 400:
            error = response.json()
            raise Exception(f"Error: {error['error']['message']}")

        return response.json()
```

**After:**

```python
async def fetch_video(video_id: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"http://localhost:8765/api/v1/videos/{video_id}",
            headers={"X-Request-ID": "my-correlation-id"}  # Optional
        )

        if response.status_code >= 400:
            content_type = response.headers.get("content-type", "")
            if "application/problem+json" in content_type:
                problem = response.json()
                # Use structured fields
                error_code = problem["code"]
                detail = problem["detail"]
                request_id = problem["request_id"]

                # Log request_id for debugging
                logger.error(f"API Error [{request_id}]: {error_code} - {detail}")

                raise APIError(
                    code=error_code,
                    detail=detail,
                    request_id=request_id
                )

        return response.json()
```

### JavaScript (fetch)

**Before:**

```javascript
async function fetchVideo(videoId) {
  const response = await fetch(`http://localhost:8765/api/v1/videos/${videoId}`);

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error.message);
  }

  return response.json();
}
```

**After:**

```javascript
async function fetchVideo(videoId) {
  const response = await fetch(
    `http://localhost:8765/api/v1/videos/${videoId}`,
    {
      headers: {
        'X-Request-ID': 'my-correlation-id'  // Optional
      }
    }
  );

  if (!response.ok) {
    const contentType = response.headers.get('content-type') || '';

    if (contentType.includes('application/problem+json')) {
      const problem = await response.json();

      // Use structured fields
      const { code, detail, request_id } = problem;

      // Log request_id for debugging
      console.error(`API Error [${request_id}]: ${code} - ${detail}`);

      throw new APIError({
        code,
        detail,
        requestId: request_id
      });
    }
  }

  return response.json();
}
```

### TypeScript Type Definition

```typescript
interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance: string;
  code: string;
  request_id: string;
  errors?: FieldError[];  // Only for 422 responses
}

interface FieldError {
  loc: (string | number)[];
  msg: string;
  type: string;
}
```

---

## Key Migration Steps

### 1. Update Content-Type Check

```python
# Before
if response.headers.get("content-type") == "application/json":

# After
content_type = response.headers.get("content-type", "")
if "application/problem+json" in content_type:
```

### 2. Update Error Parsing

```python
# Before
error_code = response.json()["error"]["code"]
error_message = response.json()["error"]["message"]

# After
problem = response.json()
error_code = problem["code"]
error_detail = problem["detail"]
request_id = problem["request_id"]
```

### 3. Add Request ID Correlation (Optional but Recommended)

```python
# Add to all requests for debugging
headers = {"X-Request-ID": str(uuid.uuid4())}
response = await client.get(url, headers=headers)

# Request ID is echoed in response header and error body
request_id = response.headers.get("X-Request-ID")
```

### 4. Handle Validation Errors

```python
# 422 responses include field-level errors
if problem["code"] == "VALIDATION_ERROR":
    for error in problem.get("errors", []):
        field_path = ".".join(str(p) for p in error["loc"])
        print(f"Field '{field_path}': {error['msg']}")
```

---

## Field Mapping Reference

| Legacy Field | RFC 7807 Field | Notes |
|--------------|----------------|-------|
| `error.code` | `code` | Unchanged values |
| `error.message` | `detail` | More descriptive |
| `error.details` | Varies | Context-specific |
| (none) | `type` | New: URI reference |
| (none) | `title` | New: Human-readable |
| (none) | `status` | New: HTTP status |
| (none) | `instance` | New: Request path |
| (none) | `request_id` | New: Correlation ID |

---

## Version Information

| Version | Date | Changes |
|---------|------|---------|
| 0.16.0 | 2026-02-05 | RFC 7807 error format introduced |
| 0.15.0 | 2026-02-05 | Legacy format (deprecated) |

---

## Frequently Asked Questions

### Q: Is this a breaking change?

**A:** Yes. Clients that parse the `error.code` or `error.message` fields from JSON responses will need to update their parsing logic.

### Q: What if I need backward compatibility?

**A:** Consider implementing a migration layer in your client that handles both formats during the transition period:

```python
def parse_error(response: httpx.Response) -> dict:
    data = response.json()

    # RFC 7807 format (new)
    if "type" in data and "code" in data:
        return {
            "code": data["code"],
            "message": data["detail"],
            "request_id": data["request_id"]
        }

    # Legacy format (deprecated)
    if "error" in data:
        return {
            "code": data["error"]["code"],
            "message": data["error"]["message"],
            "request_id": None
        }

    raise ValueError("Unknown error format")
```

### Q: Why was this change made?

**A:** RFC 7807 provides:

1. **Industry Standard**: Interoperability with other RFC 7807-compliant APIs
2. **Consistent Structure**: Predictable field names across all error types
3. **Request Correlation**: Built-in support for distributed tracing
4. **Documentation Links**: The `type` URI can link to detailed error documentation

### Q: How do I report issues with the new format?

**A:** Include the `request_id` from the error response. This enables server-side log correlation:

```
Issue: Unexpected error during video sync

Request ID: 550e8400-e29b-41d4-a716-446655440000
Endpoint: POST /api/v1/sync/videos
Error Code: INTERNAL_ERROR
```

### Q: What about the X-Request-ID header?

**A:** The `X-Request-ID` header is now included in **all** responses (success and error). You can:

1. Let the server generate a UUID (default)
2. Provide your own correlation ID in the request header

Both the request and response will contain the same ID for correlation.

---

## Related Documentation

- [API Error Responses](./error-responses.md) - Complete RFC 7807 reference
