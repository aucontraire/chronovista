/**
 * TermsExplainer — collapsed-by-default glossary shared by the candidate list
 * and detail pages (Feature 097). Definitions live here once so the copy
 * cannot drift between pages; each page selects the terms it displays.
 */

import { useEffect, useId, useRef, useState, type ReactNode } from "react";

export const TERM_DEFINITIONS = {
  worth_review: {
    term: "Worth review",
    definition: "Plausible and present in your library; the set worth a human look.",
  },
  likely_eliminable: {
    term: "Likely eliminable",
    definition: "Present, but with weak signal; usually safe to reject.",
  },
  grounds_nowhere: {
    term: "No library presence",
    definition:
      "Does not appear in your library at all; probably not relevant to you.",
  },
  score: {
    term: "Score",
    definition:
      "A ranking signal only: how often the name appears, relative to how common it is, boosted when several of your entities point at it. It orders the queue; it is not a probability.",
  },
  corroboration: {
    term: "Corroboration",
    definition:
      "How many entities you already have independently point at this suggestion. More pointers mean stronger evidence.",
  },
  salience: {
    term: "Salience",
    definition:
      "How many of your videos mention the name in their title or description.",
  },
  single_token: {
    term: "Single-token name",
    definition: "A one-word name. These are noisier, so they are always reviewed.",
  },
  possible_duplicate: {
    term: "Possible duplicate",
    definition: "The name and type collide with an entity you may already have.",
  },
  dangling_edges: {
    term: "Dangling edges",
    definition:
      "Relationship links from entities you already have that would connect to this one if you add it — how many gaps in your graph it fills.",
  },
  token_count: {
    term: "Token count",
    definition:
      "The number of words in the name. One-word names are noisier and are always reviewed.",
  },
} as const;

export type TermKey = keyof typeof TERM_DEFINITIONS;

/**
 * User-facing label for a triage bucket. Display only: the API value
 * (e.g. `grounds_nowhere`) is what filters and query keys use.
 */
export function triageLabel(value: string): string {
  return value in TERM_DEFINITIONS
    ? TERM_DEFINITIONS[value as TermKey].term
    : value;
}

interface TermsExplainerProps {
  /** Heading element rendered beside the info button. */
  heading: ReactNode;
  /** Terms this page actually displays, in display order. */
  terms: readonly TermKey[];
}

export function TermsExplainer({ heading, terms }: TermsExplainerProps) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      if (!wrapperRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  return (
    <div
      ref={wrapperRef}
      className="mb-6"
      onKeyDown={(e) => {
        if (e.key === "Escape" && open) {
          e.stopPropagation();
          setOpen(false);
          buttonRef.current?.focus();
        }
      }}
    >
      <div className="flex items-center gap-2">
        {heading}
        <button
          ref={buttonRef}
          type="button"
          aria-label="What do these terms mean?"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((o) => !o)}
          className="inline-flex items-center justify-center w-8 h-8 rounded-full text-gray-500 hover:text-indigo-700 hover:bg-indigo-50 focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <svg
            aria-hidden="true"
            viewBox="0 0 24 24"
            className="w-5 h-5"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.75"
          >
            <circle cx="12" cy="12" r="9" />
            <path strokeLinecap="round" d="M12 11v5" />
            <circle cx="12" cy="7.75" r="0.6" fill="currentColor" />
          </svg>
        </button>
      </div>
      {open && (
        <section
          id={panelId}
          aria-label="Candidate review terms"
          className="mt-3 max-w-3xl bg-white rounded-xl border border-gray-200 shadow-sm p-4"
        >
          <p className="text-sm text-gray-600 mb-3">
            Triage labels are advisory. They pre-sort the queue but never
            approve or reject anything for you.
          </p>
          <dl className="grid grid-cols-1 sm:grid-cols-[11rem_1fr] gap-x-4 gap-y-2 text-sm">
            {terms.map((key) => (
              <div key={key} className="contents">
                <dt className="font-medium text-gray-900">
                  {TERM_DEFINITIONS[key].term}
                </dt>
                <dd className="text-gray-600 mb-2 sm:mb-0">
                  {TERM_DEFINITIONS[key].definition}
                </dd>
              </div>
            ))}
          </dl>
        </section>
      )}
    </div>
  );
}
