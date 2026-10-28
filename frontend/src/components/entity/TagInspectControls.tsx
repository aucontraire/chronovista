/**
 * Small controls shared by the two tag-footprint surfaces (Feature 097):
 * a link that opens the tag's videos in a new tab so a reviewer can spot-check
 * for a homonym, and an info disclosure stating what linking does.
 */

import { useEffect, useId, useRef, useState } from "react";

export const LINK_CONSEQUENCE =
  "Linking connects every video that has this tag to this entity.";

/** Videos page filtered by one canonical tag (HomePage reads `canonical_tag`). */
export function tagVideosHref(normalizedForm: string): string {
  return `/videos?canonical_tag=${encodeURIComponent(normalizedForm)}`;
}

export function TagInspectLink({ normalizedForm }: { normalizedForm: string }) {
  return (
    <a
      href={tagVideosHref(normalizedForm)}
      target="_blank"
      rel="noopener noreferrer"
      aria-label={`View videos tagged «${normalizedForm}» (opens in a new tab)`}
      className="font-medium text-indigo-700 underline hover:text-indigo-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 rounded-sm"
    >
      {normalizedForm}
    </a>
  );
}

export function LinkConsequenceInfo() {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const wrapperRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      if (!wrapperRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  return (
    <span
      ref={wrapperRef}
      className="inline-flex flex-wrap items-center gap-1"
      onKeyDown={(e) => {
        if (e.key === "Escape" && open) {
          e.stopPropagation();
          setOpen(false);
          buttonRef.current?.focus();
        }
      }}
    >
      <button
        ref={buttonRef}
        type="button"
        aria-label="What does linking a tag do?"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center justify-center w-6 h-6 rounded-full text-gray-500 hover:text-indigo-700 hover:bg-indigo-50 focus:outline-none focus:ring-2 focus:ring-indigo-500"
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="w-4 h-4"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.75"
        >
          <circle cx="12" cy="12" r="9" />
          <path strokeLinecap="round" d="M12 11v5" />
          <circle cx="12" cy="7.75" r="0.6" fill="currentColor" />
        </svg>
      </button>
      {open && (
        <span id={panelId} className="text-xs text-gray-600">
          {LINK_CONSEQUENCE}
        </span>
      )}
    </span>
  );
}
