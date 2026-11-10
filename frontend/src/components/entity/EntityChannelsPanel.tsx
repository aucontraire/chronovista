/**
 * EntityChannelsPanel — "Operates" on the entity detail page.
 *
 * Lists the YouTube channels this entity operates (Wikidata-sourced). A
 * channel in the library links to its detail page; an external channel has no
 * page to link to, so it renders as a plain, labelled "external" item rather
 * than a broken link.
 */

import { Link } from "react-router-dom";

import { useEntityChannels } from "../../hooks/useEntityChannels";

interface EntityChannelsPanelProps {
  /** The subject entity. */
  entityId: string;
  className?: string;
}

export function EntityChannelsPanel({ entityId, className = "" }: EntityChannelsPanelProps) {
  const { channels, isLoading, isError } = useEntityChannels(entityId);

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
              {c.in_library ? (
                <Link
                  to={`/channels/${c.channel_id}`}
                  className="block rounded px-2 py-1.5 text-sm text-slate-800 hover:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-600"
                >
                  {c.title ?? c.channel_id}
                </Link>
              ) : (
                <span
                  className="flex items-center gap-2 px-2 py-1.5 text-sm text-slate-600"
                  data-testid="entity-channel-external"
                >
                  <span className="font-mono text-xs">{c.channel_id}</span>
                  <span className="rounded-full border border-slate-300 px-2 py-0.5 text-xs text-slate-600">
                    external
                  </span>
                </span>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
