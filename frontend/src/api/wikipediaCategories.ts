/**
 * Wikipedia category API client (Feature 086).
 *
 * Hand-written; mirrors the fetch conventions of entityMentions.ts.
 */

import { apiFetch } from "./config";
import type { EntityPaginationMeta } from "./entityMentions";

/** Category identity returned by GET /wikipedia-categories/{id}. */
export interface CategoryDetail {
  id: string;
  name: string;
  global_size: number | null;
  /** True when the category is a broad grouping rather than a specific one. */
  is_broad: boolean;
  /** Active library entities in this category. */
  member_count: number;
  /** Public Wikipedia page for this category. */
  wikipedia_url: string;
}

/** A library entity that belongs to a category. */
export interface CategoryEntity {
  entity_id: string;
  entity_type: string;
  canonical_name: string;
}

export interface CategoryEntitiesResponse {
  data: CategoryEntity[];
  pagination: EntityPaginationMeta;
}

export interface FetchCategoryEntitiesParams {
  limit: number;
  offset: number;
}

/**
 * Fetch a category's identity. Rejects with a 404 ApiError when the id is
 * malformed or unknown.
 */
export async function fetchCategoryDetail(
  categoryId: string,
  signal?: AbortSignal
): Promise<CategoryDetail> {
  const res = await apiFetch<{ data: CategoryDetail }>(
    `/wikipedia-categories/${encodeURIComponent(categoryId)}`,
    signal ? { externalSignal: signal } : {}
  );
  return res.data;
}

/** Fetch one page of the active library entities in a category. */
export async function fetchCategoryEntities(
  categoryId: string,
  { limit, offset }: FetchCategoryEntitiesParams,
  signal?: AbortSignal
): Promise<CategoryEntitiesResponse> {
  const qs = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return apiFetch<CategoryEntitiesResponse>(
    `/wikipedia-categories/${encodeURIComponent(categoryId)}/entities?${qs.toString()}`,
    signal ? { externalSignal: signal } : {}
  );
}
