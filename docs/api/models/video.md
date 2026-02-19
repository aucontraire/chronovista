# Video Models

Video-related Pydantic models.

::: chronovista.models.video
    options:
      show_root_heading: true
      show_source: true
      members_order: source

## Recovery Fields (Feature 025)

The following fields are added to the video detail API response when metadata has been recovered from the Wayback Machine:

| Field | Type | Description |
|-------|------|-------------|
| `recovered_at` | `datetime` or `null` | Timestamp (UTC) when the video's metadata was recovered via the Wayback Machine. Null if not recovered. |
| `recovery_source` | `string` or `null` | Source used for metadata recovery (e.g., `wayback_machine`). Null if not recovered. |
| `alternative_url` | `string` or `null` | Alternative URL for unavailable content (e.g., mirror on another platform). Max 500 characters. |
| `availability_status` | `string` | Video availability status: `available`, `deleted`, `private`, or `unavailable`. |

## Video Recovery Response Schema

The `POST /api/v1/videos/{video_id}/recover` endpoint returns a `VideoRecoveryResponse` containing:

| Field | Type | Description |
|-------|------|-------------|
| `video_id` | `string` | YouTube video ID (11 characters). |
| `success` | `boolean` | Whether the recovery attempt succeeded. |
| `snapshot_used` | `string` or `null` | CDX timestamp of the Wayback Machine snapshot used. |
| `fields_recovered` | `list[string]` | Names of fields successfully recovered (e.g., `title`, `description`, `tags`). |
| `fields_skipped` | `list[string]` | Names of fields skipped during recovery. |
| `snapshots_available` | `integer` | Total number of CDX snapshots found for this video. |
| `snapshots_tried` | `integer` | Number of snapshots attempted before success or exhaustion. |
| `failure_reason` | `string` or `null` | Reason for failure, if `success` is `false`. |
| `duration_seconds` | `float` | Wall-clock time for the recovery operation. |
| `channel_recovery_candidates` | `list[string]` | Channel IDs discovered during recovery that may need their own recovery. |
| `channel_recovered` | `boolean` | Whether the associated channel's metadata was also recovered. |
| `channel_fields_recovered` | `list[string]` | Names of channel fields successfully recovered. |
| `channel_fields_skipped` | `list[string]` | Names of channel fields skipped during recovery. |
| `channel_failure_reason` | `string` or `null` | Reason for channel recovery failure, if applicable. |
