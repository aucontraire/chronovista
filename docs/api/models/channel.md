# Channel Models

Channel-related Pydantic models.

::: chronovista.models.channel
    options:
      show_root_heading: true
      show_source: true
      members_order: source

## Recovery Fields (Feature 025)

The following fields are added to the channel detail API response when metadata has been recovered from the Wayback Machine:

| Field | Type | Description |
|-------|------|-------------|
| `recovered_at` | `datetime` or `null` | Timestamp (UTC) when the channel's metadata was recovered via the Wayback Machine. Null if not recovered. |
| `recovery_source` | `string` or `null` | Source used for metadata recovery (e.g., `wayback_machine`). Null if not recovered. |
| `availability_status` | `string` | Channel availability status: `available`, `deleted`, `terminated`, or `suspended`. |

## Channel Recovery Response Schema

The `POST /api/v1/channels/{channel_id}/recover` endpoint returns a `ChannelRecoveryResponse` containing:

| Field | Type | Description |
|-------|------|-------------|
| `channel_id` | `string` | YouTube channel ID (24 characters, starts with UC). |
| `success` | `boolean` | Whether the recovery attempt succeeded. |
| `snapshot_used` | `string` or `null` | CDX timestamp of the Wayback Machine snapshot used. |
| `fields_recovered` | `list[string]` | Names of fields successfully recovered (e.g., `title`, `description`). |
| `fields_skipped` | `list[string]` | Names of fields skipped during recovery. |
| `snapshots_available` | `integer` | Total number of CDX snapshots found for this channel. |
| `snapshots_tried` | `integer` | Number of snapshots attempted before success or exhaustion. |
| `failure_reason` | `string` or `null` | Reason for failure, if `success` is `false`. |
| `duration_seconds` | `float` | Wall-clock time for the recovery operation. |
