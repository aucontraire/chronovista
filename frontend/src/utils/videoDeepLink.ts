/**
 * In-app video deep-link (Feature 022 FR-001): `/videos/<id>` with optional `lang`, `seg`, `t`.
 *
 * One source of truth for the URL shape, shared by `SearchResult`, `EvidenceItem` and
 * `EntityDetailPage`. Feature 114 review (Finding 2) consolidated three hand-rolled copies here and
 * dropped the dead server-side `deep_link` field, so the format can no longer diverge across sites.
 */
export interface VideoDeepLinkParams {
  lang?: string;
  seg?: number;
  /** Seconds; floored to a whole number. */
  t?: number;
}

export function buildVideoDeepLink(
  videoId: string,
  params: VideoDeepLinkParams = {},
): string {
  const qs = new URLSearchParams();
  if (params.lang !== undefined) qs.set("lang", params.lang);
  if (params.seg !== undefined) qs.set("seg", String(params.seg));
  if (params.t !== undefined) qs.set("t", String(Math.floor(params.t)));
  const query = qs.toString();
  return query ? `/videos/${videoId}?${query}` : `/videos/${videoId}`;
}
