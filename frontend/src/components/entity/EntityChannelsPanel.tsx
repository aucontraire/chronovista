/**
 * EntityChannelsPanel — "Operates" on the entity detail page.
 *
 * Lists the YouTube channels this entity operates, each with a provenance
 * badge (Wikidata or added by hand). A channel in the library links to its
 * detail page; an external channel links out to YouTube and is marked "not in
 * library". A small form lets the user add a channel by ID or URL.
 */

import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";

import {
  useAddEntityChannel,
  useRemoveEntityChannel,
} from "../../hooks/useEntityChannelMutations";
import { useEntityChannels } from "../../hooks/useEntityChannels";

interface EntityChannelsPanelProps {
  /** The subject entity. */
  entityId: string;
  className?: string;
}

const INVALID_REF_MESSAGE = "Enter a channel ID (UC…) or a youtube.com/channel/… URL";

function describeAddError(error: unknown): string {
  const e = error as { status?: number; detail?: string } | null;
  if (e?.status === 422) return INVALID_REF_MESSAGE;
  if (e?.status === 409) return e.detail ?? "This channel is already recorded for this entity.";
  if (e?.status === 404) return "This entity no longer exists.";
  return "Couldn't add the channel. Please try again.";
}

const PROVENANCE_LABEL = { wikidata: "per Wikidata", manual: "you added" } as const;

export function EntityChannelsPanel({ entityId, className = "" }: EntityChannelsPanelProps) {
  const { channels, isLoading, isError } = useEntityChannels(entityId);
  const addChannel = useAddEntityChannel(entityId);
  const removeChannel = useRemoveEntityChannel(entityId);
  const [channelRef, setChannelRef] = useState("");

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const ref = channelRef.trim();
    if (!ref) return;
    addChannel.mutate(ref, { onSuccess: () => setChannelRef("") });
  };

  return (
    <section
      className={`rounded-lg border border-slate-200 bg-white p-4 ${className}`.trim()}
      aria-labelledby="entity-channels-heading"
      data-testid="entity-channels-panel"
    >
      <h2 id="entity-channels-heading" className="mb-3 text-sm font-semibold text-slate-800">
        Operates
      </h2>

      {isLoading && (
        <p role="status" className="text-sm text-slate-500" data-testid="entity-channels-loading">
          Finding channels this entity operates…
        </p>
      )}

      {!isLoading && isError && (
        <p role="alert" className="text-sm text-amber-800" data-testid="entity-channels-error">
          Couldn&apos;t load channels. The rest of this page is unaffected.
        </p>
      )}

      {!isLoading && !isError && channels.length === 0 && (
        <p role="status" className="text-sm text-slate-600" data-testid="entity-channels-empty">
          No channels are recorded for this entity.
        </p>
      )}

      {!isLoading && !isError && channels.length > 0 && (
        <ul className="flex flex-col gap-1" aria-label="Channels operated by this entity">
          {channels.map((c) => (
            <li key={c.channel_id}>
              <div className="flex flex-wrap items-center gap-2 px-2 py-1.5 text-sm">
                {c.in_library ? (
                  <Link
                    to={`/channels/${c.channel_id}`}
                    className="text-slate-800 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600"
                  >
                    {c.title ?? c.channel_id}
                  </Link>
                ) : (
                  <>
                    <a
                      href={`https://www.youtube.com/channel/${c.channel_id}`}
                      target="_blank"
                      rel="noreferrer"
                      className="font-mono text-xs text-indigo-700 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600"
                    >
                      {c.channel_id}
                      <span className="sr-only"> (opens YouTube in a new tab)</span>
                    </a>
                    <span className="rounded-full border border-slate-300 px-2 py-0.5 text-xs text-slate-600">
                      not in library
                    </span>
                  </>
                )}
                <span
                  className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700"
                  data-testid="entity-channel-provenance"
                >
                  {PROVENANCE_LABEL[c.provenance]}
                </span>
                {c.provenance === "manual" && (
                  <button
                    type="button"
                    onClick={() => removeChannel.mutate(c.channel_id)}
                    disabled={removeChannel.isPending}
                    aria-label={`Remove ${c.title ?? c.channel_id} from this entity's channels`}
                    className="ml-auto rounded border border-slate-300 px-2 py-0.5 text-xs text-slate-700 hover:bg-slate-50 disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600"
                  >
                    Remove
                  </button>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}

      {removeChannel.isError && (
        <p role="alert" className="mt-2 text-sm text-red-700" data-testid="entity-channel-remove-error">
          Couldn&apos;t remove the channel. Please try again.
        </p>
      )}

      <form onSubmit={handleSubmit} className="mt-3 flex flex-col gap-2" noValidate>
        <label htmlFor="entity-channel-ref" className="text-xs font-medium text-slate-700">
          Add a channel (ID or youtube.com/channel/… URL)
        </label>
        <div className="flex gap-2">
          <input
            id="entity-channel-ref"
            type="text"
            value={channelRef}
            onChange={(e) => {
              setChannelRef(e.target.value);
              if (addChannel.isError) addChannel.reset();
            }}
            aria-invalid={addChannel.isError}
            aria-describedby={addChannel.isError ? "entity-channel-add-error" : undefined}
            className="min-w-0 flex-1 rounded border border-slate-300 px-2 py-1 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600"
          />
          <button
            type="submit"
            disabled={addChannel.isPending || channelRef.trim() === ""}
            className="rounded bg-indigo-600 px-3 py-1 text-sm text-white disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-indigo-600"
          >
            {addChannel.isPending ? "Adding channel…" : "Add channel"}
          </button>
        </div>
        {addChannel.isError && (
          <p
            id="entity-channel-add-error"
            role="alert"
            className="text-sm text-red-700"
            data-testid="entity-channel-add-error"
          >
            {describeAddError(addChannel.error)}
          </p>
        )}
      </form>
    </section>
  );
}
