/**
 * EntityVideoExcludeButton — hides a wrongly associated video from an entity
 * (Feature 091). No confirmation step: the action is reversible from the
 * "Hidden from this entity" section, which is the undo.
 */

import { useExcludeEntityVideo } from "../../hooks/useEntityExclusions";

export interface EntityVideoExcludeButtonProps {
  entityId: string;
  entityName: string;
  videoId: string;
}

export function EntityVideoExcludeButton({
  entityId,
  entityName,
  videoId,
}: EntityVideoExcludeButtonProps) {
  const mutation = useExcludeEntityVideo(entityId);

  return (
    <div className="mt-1 flex items-center justify-end gap-2">
      {mutation.isError && (
        <span role="alert" className="text-xs text-red-600">
          Could not remove this video. Try again.
        </span>
      )}
      <button
        type="button"
        data-testid={`exclude-button-${videoId}`}
        aria-label={`Remove this video from ${entityName}`}
        disabled={mutation.isPending}
        onClick={() => mutation.mutate({ videoId })}
        className="text-xs text-slate-500 hover:text-amber-700 underline disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-1 rounded"
      >
        {mutation.isPending ? "Removing…" : "Not about this?"}
      </button>
    </div>
  );
}
