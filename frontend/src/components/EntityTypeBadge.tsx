import {
  ENTITY_TYPE_FALLBACK_LABEL,
  ENTITY_TYPE_LABELS,
  entityTypeColors,
} from "../constants/entityTypes";

/** Badge sizes in use. `sm` matches the entities list, `md` the detail page. */
type EntityTypeBadgeSize = "sm" | "md";

const SIZE_CLASSES: Record<EntityTypeBadgeSize, string> = {
  sm: "px-2.5 py-0.5 text-xs",
  md: "px-3 py-1 text-sm",
};

interface EntityTypeBadgeProps {
  /** Raw entity_type value from the API. Unrecognised values fall back. */
  entityType: string | null | undefined;
  /** Visual size. Defaults to the compact list size. */
  size?: EntityTypeBadgeSize;
  /** Optional extra classes for layout at the call site (margins, etc.). */
  className?: string;
}

/**
 * Type badge for a named entity.
 *
 * Colour and label both come from `constants/entityTypes`, so every surface
 * renders the same entity identically (FR-025) and the palette has exactly one
 * definition point (FR-029). The label is always rendered as text, never
 * conveyed by colour alone, so the type survives greyscale, colour-blindness,
 * and screen readers (FR-027, SC-010).
 *
 * **Fallback preserves prior behaviour.** An unrecognised but non-empty type
 * displays the raw value rather than a generic word: the entities list has
 * always done that, and it tells a reader what the data actually says instead
 * of hiding it. Only a missing type falls back to a generic label, since there
 * is nothing to show (FR-028).
 */
export function EntityTypeBadge({
  entityType,
  size = "sm",
  className = "",
}: EntityTypeBadgeProps) {
  const key = entityType ?? "";
  const colorClasses = entityTypeColors(entityType);
  const label =
    ENTITY_TYPE_LABELS[key] ?? (key === "" ? ENTITY_TYPE_FALLBACK_LABEL : key);

  return (
    <span
      className={`inline-flex items-center rounded-full border font-medium ${SIZE_CLASSES[size]} ${colorClasses} ${className}`.trim()}
      aria-label={`Entity type: ${label}`}
    >
      {label}
    </span>
  );
}
