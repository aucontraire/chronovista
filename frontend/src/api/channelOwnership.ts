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
}

/** An entity that operates a channel. `entity_type` is not person-scoped. */
export interface ChannelOperatorItem {
  entity_id: string;
  entity_type: string;
  canonical_name: string;
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
