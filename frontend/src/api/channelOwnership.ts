/**
 * Hand-written client for channel-ownership ("operates" / "operated by") reads.
 *
 * Hand-written, not orval-generated: `orval.config.ts` cleans its target dir,
 * and the `src/api/*` modules are maintained by hand.
 */

import { apiFetch } from "./config";

/** A YouTube channel an entity operates (Wikidata-sourced). */
export interface EntityChannelLink {
  channel_id: string;
  /** Null when the channel is external (not in the library). */
  title: string | null;
  in_library: boolean;
  /** Where the assertion came from: Wikidata sync or added by hand. */
  provenance: "wikidata" | "manual";
}

/** An entity that operates a channel. `entity_type` is not person-scoped. */
export interface ChannelOperatorItem {
  entity_id: string;
  entity_type: string;
  canonical_name: string;
  /** Where the assertion came from: Wikidata sync or added by hand. */
  provenance: "wikidata" | "manual";
}

export interface ChannelOperatorsResponse {
  channel_id: string;
  total_entities: number;
  items: ChannelOperatorItem[];
}

/**
 * Fetch the channels an entity operates.
 *
 * @param entityId - UUID of the entity
 * @param signal - Abort signal
 */
export async function fetchEntityChannels(
  entityId: string,
  signal?: AbortSignal
): Promise<EntityChannelLink[]> {
  const res = await apiFetch<{ data: EntityChannelLink[] }>(
    `/entities/${entityId}/channels`,
    signal ? { externalSignal: signal } : {}
  );
  return res.data;
}

/**
 * Fetch the entities that operate a channel.
 *
 * @param channelId - YouTube channel ID
 * @param signal - Abort signal
 */
export async function fetchChannelOperators(
  channelId: string,
  signal?: AbortSignal
): Promise<ChannelOperatorsResponse> {
  return apiFetch<ChannelOperatorsResponse>(
    `/channels/${channelId}/operators`,
    signal ? { externalSignal: signal } : {}
  );
}

/**
 * Assert by hand that an entity operates a channel.
 *
 * Rejections arrive as ApiError with `status` (409 redundant, 422 unparseable
 * ref, 404 unknown entity) and the server's reason in `detail`.
 *
 * @param entityId - UUID of the entity
 * @param channelRef - Raw UC... channel ID or youtube.com/channel/UC... URL
 */
export async function addEntityChannel(
  entityId: string,
  channelRef: string
): Promise<EntityChannelLink> {
  return apiFetch<EntityChannelLink>(`/entities/${entityId}/channels`, {
    method: "POST",
    body: JSON.stringify({ channel_ref: channelRef }),
  });
}

/**
 * Assert by hand that an entity operates a channel (channel-side).
 *
 * Rejections arrive as ApiError: 404 unknown entity, 409 redundant (reason in
 * `detail`).
 */
export async function assignChannelOperator(
  channelId: string,
  entityId: string
): Promise<ChannelOperatorItem> {
  return apiFetch<ChannelOperatorItem>(`/channels/${channelId}/operators`, {
    method: "POST",
    body: JSON.stringify({ entity_id: entityId }),
  });
}

/** Remove a manual link (entity-side). 404 if the link is imported or absent. */
export async function removeEntityChannel(
  entityId: string,
  channelId: string
): Promise<void> {
  await apiFetch<void>(`/entities/${entityId}/channels/${channelId}`, {
    method: "DELETE",
  });
}

/** Remove a manual link (channel-side). 404 if the link is imported or absent. */
export async function removeChannelOperator(
  channelId: string,
  entityId: string
): Promise<void> {
  await apiFetch<void>(`/channels/${channelId}/operators/${entityId}`, {
    method: "DELETE",
  });
}
