/**
 * PlaylistMembershipList component - displays playlist chips showing which playlists contain a video.
 */

import { Link } from "react-router-dom";
import { PlaylistIcon } from "./icons/PlaylistIcon";
import type { VideoPlaylistMembership } from "../types/playlist";

/**
 * Props for PlaylistMembershipList component.
 */
export interface PlaylistMembershipListProps {
  /** Array of playlists containing the video */
  playlists: VideoPlaylistMembership[];
}

/**
 * PlaylistMembershipList displays a collection of playlist chips showing
 * which playlists contain the current video.
 *
 * Each chip shows:
 * - Playlist icon
 * - Playlist title (truncated at 200px)
 *
 * Chips are clickable links to the playlist detail page.
 *
 * @param props - Component props
 * @returns JSX element displaying playlist memberships
 */
export const PlaylistMembershipList = ({
  playlists,
}: PlaylistMembershipListProps) => {
  if (playlists.length === 0) {
    return null;
  }

  return (
    <div className="mt-6 pt-6 border-t border-gray-100">
      <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wider mb-3">
        In Playlists
      </h2>
      <div
        className="flex flex-wrap gap-2"
        role="list"
        aria-label="Playlists containing this video"
      >
        {playlists.map((playlist) => (
          <Link
            key={playlist.playlist_id}
            to={`/playlists/${playlist.playlist_id}`}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-blue-100 text-blue-800 rounded-full text-sm font-medium hover:bg-blue-200 hover:shadow-sm transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
            role="listitem"
          >
            <PlaylistIcon className="w-4 h-4" aria-hidden="true" />
            <span className="max-w-[200px] truncate">{playlist.title}</span>
          </Link>
        ))}
      </div>
    </div>
  );
};
