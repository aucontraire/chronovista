/**
 * MaximizeOverlay — in-app maximize for the graph (Feature 115, US5: FR-017/018/019/025).
 *
 * The wrapper element is ALWAYS rendered in the same tree position and `children` (the graph)
 * is never re-parented: maximizing only swaps the wrapper's classes to `fixed inset-0 z-50`.
 * The Cytoscape instance inside is therefore the same one before, during and after, so the
 * layout survives. When maximized, a same-height placeholder keeps the page from jumping.
 *
 * Modal semantics (FR-025): `role="dialog"` + `aria-modal` + label; focus moves in on open and
 * returns to `returnFocusRef` on exit; everything outside the dialog's ancestor chain is made
 * `inert`; body scroll is locked. Escape exits, but only if no inner popover consumed it first:
 * a popover that handles Escape must call `event.preventDefault()` (this handler runs on the
 * bubble phase and skips defaulted events).
 */

import { useEffect, useRef } from "react";
import type { KeyboardEvent, ReactNode, RefObject } from "react";

interface MaximizeOverlayProps {
  maximized: boolean;
  onExit: () => void;
  /** Accessible name of the dialog. */
  label: string;
  /** The graph. Rendered in both states, in the same position. */
  children: ReactNode;
  /** Floating controls; rendered only while maximized. */
  toolbar: ReactNode;
  /** Where focus goes on exit (normally the maximize button). */
  returnFocusRef: RefObject<HTMLElement | null>;
}

/** Marks every sibling along the path to <body> inert; returns the undo function. */
function makeOutsideInert(el: HTMLElement): () => void {
  const marked: Element[] = [];
  for (let node: HTMLElement = el; node.parentElement; node = node.parentElement) {
    for (const sibling of Array.from(node.parentElement.children)) {
      if (sibling !== node && !sibling.hasAttribute("inert")) {
        sibling.setAttribute("inert", "");
        marked.push(sibling);
      }
    }
    if (node.parentElement === document.body) break;
  }
  return () => marked.forEach((s) => s.removeAttribute("inert"));
}

export function MaximizeOverlay({
  maximized,
  onExit,
  label,
  children,
  toolbar,
  returnFocusRef,
}: MaximizeOverlayProps) {
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const wrapper = wrapperRef.current;
    if (!maximized || !wrapper) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const restoreInert = makeOutsideInert(wrapper);
    wrapper.focus();
    return () => {
      document.body.style.overflow = previousOverflow;
      restoreInert();
      returnFocusRef.current?.focus();
    };
  }, [maximized, returnFocusRef]);

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape" && !event.defaultPrevented) {
      event.preventDefault();
      onExit();
    }
  }

  return (
    <>
      <div
        ref={wrapperRef}
        {...(maximized
          ? {
              role: "dialog",
              "aria-modal": true,
              "aria-label": label,
              tabIndex: -1,
              onKeyDown: handleKeyDown,
            }
          : {})}
        className={maximized ? "fixed inset-0 z-50 bg-white p-2 focus:outline-none" : "relative"}
      >
        {children}
        {maximized && toolbar}
      </div>
      {maximized && <div aria-hidden="true" className="h-[28rem]" data-testid="maximize-placeholder" />}
    </>
  );
}
