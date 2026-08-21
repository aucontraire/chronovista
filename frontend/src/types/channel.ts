/**
 * Channel data types for the Chronovista frontend.
 * These types match the backend API response schemas from channels.py.
 */

import type { PaginationInfo } from "./video";

/**
 * Channel item as returned by the list API endpoint.
 * Provides minimal channel information for efficient list rendering.
 */
export interface ChannelListItem {
  /** YouTube channel ID (24 characters) */
  channel_id: string;
  /** Channel title */
  title: string;
  /** Channel description (may be null) */
  description: string | null;
  /** Number of subscribers (may be null if not available) */
  subscriber_count: number | null;
  /** Number of videos on the channel (may be null if not available) */
  video_count: number | null;
  /** URL to channel thumbnail image (may be null) */
  thumbnail_url: string | null;
  /** Custom channel URL (e.g., @username, currently always null) */
  custom_url: string | null;
  /** Content availability status */
  availability_status: string;
  /** Whether the user is subscribed to this channel */
  is_subscribed: boolean;
  /** ISO 8601 datetime when channel was recovered (null if not recovered) */
  recovered_at: string | null;
  /** Source of recovery data (e.g., "wayback_machine", null if not recovered) */
  recovery_source: string | null;
}

/**
 * Full channel details for single resource response.
 * Extends ChannelListItem with additional metadata fields.
 */
export interface ChannelDetail extends ChannelListItem {
  /** Default language code for the channel (BCP-47, may be null) */
  default_language: string | null;
  /** Country code (ISO 3166-1 alpha-2, may be null) */
  country: string | null;
  /** ISO 8601 datetime string of record creation */
  created_at: string;
  /** ISO 8601 datetime string of last update */
  updated_at: string;
  /** Content availability status */
  availability_status: string;
  /** ISO 8601 datetime when channel was recovered (null if not recovered) */
  recovered_at: string | null;
  /** Source of recovery data (e.g., "wayback_machine", null if not recovered) */
  recovery_source: string | null;
}

/**
 * Response from the channels list API endpoint.
 */
export interface ChannelListResponse {
  /** Array of channel items */
  data: ChannelListItem[];
  /** Pagination metadata */
  pagination: PaginationInfo;
}

/**
 * Response from the channel detail API endpoint.
 */
export interface ChannelDetailResponse {
  /** Channel detail data */
  data: ChannelDetail;
}

/**
 * A single entity's ranking within a channel, as returned by
 * `GET /channels/{channel_id}/entities` (Feature 070).
 */
export interface ChannelEntityRanking {
  /** Entity UUID (string form) */
  entity_id: string;
  /** Entity's canonical display name */
  display_name: string;
  /** Raw entity_type value (e.g. "person", "place") */
  entity_type: string;
  /** Number of this channel's videos the entity appears in */
  channel_video_count: number;
  /** Number of videos across the whole corpus the entity appears in */
  corpus_video_count: number;
  /** Distinctiveness share, a float in (0, 1] */
  share: number;
  /**
   * Whether this entity is in the share-ranked group (true) or the
   * "also appears" group of single-video entities (false). The API already
   * orders `items` accordingly — ranked group first, then unranked.
   */
  is_ranked: boolean;
}

/**
 * Response from the channel entities ranking API endpoint.
 */
export interface ChannelEntitiesResponse {
  /** Channel ID the ranking belongs to */
  channel_id: string;
  /** Total number of entities associated with the channel */
  total_entities: number;
  /** Ranked entities, server-ordered: is_ranked group first, then unranked */
  items: ChannelEntityRanking[];
}
