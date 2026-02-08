/**
 * Hook exports for Chronovista frontend.
 */

export { useChannelDetail } from "./useChannelDetail";
export { useChannels } from "./useChannels";
export { useDebounce } from "./useDebounce";
export { useChannelVideos } from "./useChannelVideos";
export { usePrefersReducedMotion } from "./usePrefersReducedMotion";
export { useTranscript } from "./useTranscript";
export { useTranscriptLanguages } from "./useTranscriptLanguages";
export {
  useTranscriptSegments,
  segmentsQueryKey,
} from "./useTranscriptSegments";
export type { UseTranscriptSegmentsResult } from "./useTranscriptSegments";
export { useVideoDetail } from "./useVideoDetail";
export { useVideos } from "./useVideos";
export {
  useSearchSegments,
  type UseSearchSegmentsOptions,
  type UseSearchSegmentsResult,
} from "./useSearchSegments";
