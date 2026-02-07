/**
 * VideoGrid component displays videos in a responsive grid layout.
 * Reusable grid component that accepts an array of videos.
 */

import { VideoCard } from "./VideoCard";
import type { VideoListItem } from "../types/video";

interface VideoGridProps {
  /** Array of videos to display */
  videos: VideoListItem[];
}

/**
 * VideoGrid renders videos in a responsive 3-column grid.
 * Uses the VideoCard component for each video.
 *
 * @example
 * ```tsx
 * <VideoGrid videos={channelVideos} />
 * ```
 */
export function VideoGrid({ videos }: VideoGridProps) {
  return (
    <div
      className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
      role="list"
      aria-label="Video list"
    >
      {videos.map((video) => (
        <div key={video.video_id} role="listitem">
          <VideoCard video={video} />
        </div>
      ))}
    </div>
  );
}
