/**
 * AssociationBreakdown — inline per-source pill breakdown of an entity's
 * video associations (Feature 066, FR-004).
 *
 * Always renders all five sources, in a fixed display order, even when a
 * source's count is 0. Pills are decorative (aria-hidden); the container
 * carries a single summarizing aria-label so screen readers get one clean
 * announcement rather than five fragmented tokens.
 */

import type { AssociationSourceBreakdown } from "../api/entityMentions";

export interface AssociationBreakdownProps {
  bySource: AssociationSourceBreakdown;
  className?: string;
}

const PILL_BASE_CLASSES =
  "inline-flex items-center px-2 py-0.5 text-xs font-medium rounded";

/** Display order + label + color, per FR-004: tag, transcript, title, description, manual. */
const SOURCE_CONFIG: Array<{
  key: keyof AssociationSourceBreakdown;
  label: string;
  colorClasses: string;
}> = [
  { key: "tag", label: "TAG", colorClasses: "bg-teal-100 text-teal-700" },
  {
    key: "transcript",
    label: "TRANSCRIPT",
    colorClasses: "bg-indigo-100 text-indigo-700 border border-indigo-200",
  },
  { key: "title", label: "TITLE", colorClasses: "bg-amber-100 text-amber-700" },
  {
    key: "description",
    label: "DESCRIPTION",
    colorClasses: "bg-slate-200 text-slate-700",
  },
  {
    key: "manual",
    label: "MANUAL",
    colorClasses: "bg-emerald-100 text-emerald-700 border border-emerald-200",
  },
];

export function AssociationBreakdown({
  bySource,
  className,
}: AssociationBreakdownProps) {
  const ariaLabel = `Associations by source: ${SOURCE_CONFIG.map(
    ({ key, label }) => `${bySource[key]} ${label.toLowerCase()}`
  ).join(", ")}`;

  return (
    <div
      className={`inline-flex flex-wrap items-center gap-1.5${className ? ` ${className}` : ""}`}
      aria-label={ariaLabel}
    >
      {SOURCE_CONFIG.map(({ key, label, colorClasses }) => (
        <span
          key={key}
          className={`${PILL_BASE_CLASSES} ${colorClasses}`}
          aria-hidden="true"
        >
          {label} {bySource[key]}
        </span>
      ))}
    </div>
  );
}
