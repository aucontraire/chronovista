/**
 * ChannelOperatorsPanel — "Operated by" on the channel detail page.
 *
 * Lists the entities that operate this channel (Wikidata-sourced). Ownership
 * is not person-scoped, so each row carries an entity-type badge.
 */

import { Link } from "react-router-dom";

import { useChannelOperators } from "../../hooks/useChannelOperators";
import { EntityTypeBadge } from "../EntityTypeBadge";
import { colorTokens, cardPatterns } from "../../styles";

export interface ChannelOperatorsPanelProps {
  /** YouTube channel ID whose operators should be displayed. */
  channelId: string;
}

export function ChannelOperatorsPanel({ channelId }: ChannelOperatorsPanelProps) {
  const { data, isLoading, isError, error, refetch } = useChannelOperators(channelId);

  return (
    <section className={`${cardPatterns.base} p-6 mb-8`} aria-labelledby="channel-operators-heading">
      <h2
        id="channel-operators-heading"
        className={`text-2xl font-bold text-${colorTokens.text.primary} mb-4`}
      >
        Operated by
      </h2>

      {isLoading && (
        <div role="status" aria-busy="true">
          <div aria-hidden="true" className="h-6 bg-gray-200 rounded-full w-48 animate-pulse" />
          <span className="sr-only">Loading operators…</span>
        </div>
      )}

      {!isLoading && isError && (
        <div
          className={`bg-${colorTokens.status.error.bg} border border-${colorTokens.status.error.border} rounded-lg p-6 text-center`}
          role="alert"
        >
          <p className={`text-${colorTokens.status.error.text} font-medium mb-4`}>
            Could not load operators: {error?.message ?? "An error occurred"}
          </p>
          <button
            type="button"
            onClick={refetch}
            className="inline-flex items-center px-4 py-2 bg-red-600 text-white font-medium rounded-md hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 transition-colors"
          >
            Retry
          </button>
        </div>
      )}

      {!isLoading && !isError && data && data.items.length === 0 && (
        <p role="status" className={`text-${colorTokens.text.secondary}`}>
          No operating entities are recorded for this channel.
        </p>
      )}

      {!isLoading && !isError && data && data.items.length > 0 && (
        <ul role="list" aria-label="Entities that operate this channel">
          {data.items.map((op) => (
            <li
              key={op.entity_id}
              role="listitem"
              className={`flex flex-wrap items-center gap-3 py-3 border-b border-${colorTokens.border} last:border-b-0`}
            >
              <Link
                to={`/entities/${op.entity_id}`}
                className="min-w-0 truncate text-blue-600 hover:text-blue-700 hover:underline focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-1 rounded"
              >
                {op.canonical_name}
              </Link>
              <EntityTypeBadge entityType={op.entity_type} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
