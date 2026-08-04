import {
  ENTITY_TYPE_FALLBACK_LABEL,
  ENTITY_TYPE_LABELS,
  entityTypeColors,
} from "../constants/entityTypes";

interface EntityNameProps {
  /** Canonical display name — this is what the pill contains. */
  name: string;
  /** Raw entity_type value; supplies the pill's colour. */
  entityType: string | null | undefined;
  /**
   * When given, renders a dismiss control INSIDE the pill.
   *
   * Inside rather than beside: a pill wrapped in a second bordered box with the
   * × outside it reads as two elements for one thing. The selected-tag pills
   * put their dismiss inside, and matching them keeps the filter panel coherent.
   */
  onRemove?: (() => void) | undefined;
  /**
   * Mention tally, rendered as `(N)` inside the pill.
   *
   * Matches the video detail page's entity chips, which have always shown the
   * count this way. Keeping one convention means a reader who learns it in one
   * place reads it everywhere.
   */
  count?: number | undefined;
  /** Optional extra classes for layout at the call site. */
  className?: string;
}

/**
 * An entity's NAME in a type-coloured pill — the shorthand treatment.
 *
 * The project uses one pill shape with two possible contents, and which one
 * appears depends on whether the surface is *teaching* the convention or
 * *applying* it:
 *
 * - **Legend surfaces** — the entities list, the entity detail header — put the
 *   TYPE in the pill ("Person", "Technical Term") via `EntityTypeBadge`. That
 *   is where a reader learns indigo means person and emerald means place.
 * - **Every other surface** — appears-with, result rows, the filter picker —
 *   puts the NAME in the pill, in the same colour. Repeating the type label
 *   beside every name is noise once the convention is known; the colour
 *   carries it, and the legend pages are where it was learned.
 *
 * The type is still announced to screen readers as visually-hidden text, so it
 * is never lost to assistive technology. It IS lost in greyscale on these
 * surfaces — the deliberate trade recorded in FR-027a.
 */
export function EntityName({
  name,
  entityType,
  onRemove,
  count,
  className = "",
}: EntityNameProps) {
  const key = entityType ?? "";
  const colorClasses = entityTypeColors(entityType);
  const typeLabel =
    ENTITY_TYPE_LABELS[key] ?? (key === "" ? ENTITY_TYPE_FALLBACK_LABEL : key);

  const spacing = onRemove ? "gap-1.5 ps-3 pe-1.5 py-1" : "px-2.5 py-0.5";

  return (
    <span
      className={`inline-flex items-center rounded-full border text-xs font-medium ${spacing} ${colorClasses} ${className}`.trim()}
    >
      <span className="sr-only">{typeLabel}: </span>
      {name}
      {count !== undefined && (
        <>
          {/* Spoken in full, shown in shorthand: a screen reader saying
              "open paren three close paren" helps nobody. */}
          <span className="sr-only">
            , {count} mention{count === 1 ? "" : "s"}
          </span>
          <span className="ms-1 font-normal opacity-70" aria-hidden="true">
            ({count})
          </span>
        </>
      )}
      {onRemove && (
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remove ${name}`}
          className="inline-flex h-4 w-4 items-center justify-center rounded-full hover:bg-black/10 focus:outline-none focus:ring-2 focus:ring-offset-1 focus:ring-current"
        >
          <svg
            className="h-3 w-3"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M6 18L18 6M6 6l12 12"
            />
          </svg>
        </button>
      )}
    </span>
  );
}
