/**
 * ChannelOperatorsPanel — "Operated by" on the channel detail page.
 *
 * Lists the entities that operate this channel, each with a provenance badge
 * (Wikidata or added by hand). Ownership is not person-scoped, so each row
 * carries an entity-type badge. Manual links can be removed; a small form
 * assigns an owner by entity ID (no entity search component exists to reuse).
 */

import { useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";

import { useChannelOperators } from "../../hooks/useChannelOperators";
import {
  useAssignChannelOperator,
  useRemoveChannelOperator,
} from "../../hooks/useChannelOperatorMutations";
import { EntityTypeBadge } from "../EntityTypeBadge";
import { colorTokens, cardPatterns } from "../../styles";

export interface ChannelOperatorsPanelProps {
  /** YouTube channel ID whose operators should be displayed. */
  channelId: string;
}

const PROVENANCE_LABEL = { wikidata: "per Wikidata", manual: "you added" } as const;

function describeAssignError(error: unknown): string {
  const e = error as { status?: number; detail?: string } | null;
  if (e?.status === 404) return "That entity doesn't exist — create it first.";
  if (e?.status === 409) return e.detail ?? "This entity is already recorded for this channel.";
  return "Couldn't assign the owner. Please try again.";
}

export function ChannelOperatorsPanel({ channelId }: ChannelOperatorsPanelProps) {
  const { data, isLoading, isError, error, refetch } = useChannelOperators(channelId);
  const assign = useAssignChannelOperator(channelId);
  const remove = useRemoveChannelOperator(channelId);
  const [entityId, setEntityId] = useState("");

  const handleSubmit = (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    const id = entityId.trim();
    if (!id) return;
    assign.mutate(id, { onSuccess: () => setEntityId("") });
  };

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
              <span
                className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-700"
                data-testid="channel-operator-provenance"
              >
                {PROVENANCE_LABEL[op.provenance]}
              </span>
              {op.provenance === "manual" && (
                <button
                  type="button"
                  onClick={() => remove.mutate(op.entity_id)}
                  disabled={remove.isPending}
                  aria-label={`Remove ${op.canonical_name} as an operator of this channel`}
                  className="ml-auto rounded border border-slate-300 px-2 py-0.5 text-sm text-slate-700 hover:bg-slate-50 disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500"
                >
                  Remove
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      {remove.isError && (
        <p role="alert" className="mt-2 text-sm text-red-700" data-testid="channel-operator-remove-error">
          Couldn&apos;t remove the operator. Please try again.
        </p>
      )}

      <form onSubmit={handleSubmit} className="mt-4 flex flex-col gap-2" noValidate>
        <label htmlFor="channel-operator-entity-id" className="text-sm font-medium text-slate-700">
          Assign an owner (entity ID)
        </label>
        <div className="flex gap-2">
          <input
            id="channel-operator-entity-id"
            type="text"
            value={entityId}
            onChange={(e) => {
              setEntityId(e.target.value);
              if (assign.isError) assign.reset();
            }}
            aria-invalid={assign.isError}
            aria-describedby={assign.isError ? "channel-operator-assign-error" : undefined}
            className="min-w-0 flex-1 rounded border border-slate-300 px-2 py-1 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-blue-600"
          />
          <button
            type="submit"
            disabled={assign.isPending || entityId.trim() === ""}
            className="rounded bg-blue-600 px-3 py-1 text-sm text-white disabled:opacity-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600"
          >
            {assign.isPending ? "Assigning…" : "Assign"}
          </button>
        </div>
        {assign.isError && (
          <p
            id="channel-operator-assign-error"
            role="alert"
            className="text-sm text-red-700"
            data-testid="channel-operator-assign-error"
          >
            {describeAssignError(assign.error)}
          </p>
        )}
      </form>
    </section>
  );
}
