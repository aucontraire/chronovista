/**
 * HiddenFromEntitySection — lists videos hidden from an entity with a Restore
 * action (Feature 091). Renders nothing when there are none, since that is the
 * usual case.
 */

import { Link } from "react-router-dom";

import {
  useEntityExclusions,
  useRestoreEntityVideo,
} from "../../hooks/useEntityExclusions";

export interface HiddenFromEntitySectionProps {
  entityId: string;
  entityName: string;
}

export function HiddenFromEntitySection({
  entityId,
  entityName,
}: HiddenFromEntitySectionProps) {
  const { data } = useEntityExclusions(entityId);
  const restore = useRestoreEntityVideo(entityId);
  const exclusions = data?.data ?? [];

  if (exclusions.length === 0) return null;

  return (
    <section
      aria-labelledby="entity-hidden-videos-heading"
      className="mt-6"
      data-testid="hidden-from-entity"
    >
      <h3
        id="entity-hidden-videos-heading"
        className="text-sm font-semibold text-gray-700 mb-2"
      >
        Hidden from this entity ({exclusions.length})
      </h3>
      {restore.isError && (
        <p role="alert" className="text-xs text-red-600 mb-2">
          Could not restore the video. Try again.
        </p>
      )}
      <ul className="space-y-2">
        {exclusions.map((ex) => (
          <li
            key={ex.video_id}
            className="flex items-center justify-between gap-3 bg-slate-50 border border-slate-200 rounded-md px-3 py-2"
          >
            <Link
              to={`/videos/${ex.video_id}`}
              className="text-sm text-indigo-600 hover:text-indigo-800 underline truncate focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 rounded"
            >
              Video {ex.video_id}
            </Link>
            <button
              type="button"
              aria-label={`Restore video ${ex.video_id} to ${entityName}`}
              disabled={
                restore.isPending && restore.variables?.videoId === ex.video_id
              }
              onClick={() => restore.mutate({ videoId: ex.video_id })}
              className="text-sm px-2 py-1 rounded border border-slate-300 bg-white text-slate-700 hover:bg-slate-100 disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500"
            >
              Restore
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
