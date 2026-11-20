/**
 * ToggleRow — one labelled checkbox row, shared by the edge-layer, node-type and
 * relationship-type filter lists so they behave and look the same (native, keyboard-operable).
 */

import type { ReactNode } from "react";

interface ToggleRowProps {
  checked: boolean;
  onChange: () => void;
  disabled?: boolean;
  /** Extra classes for the label (text size/colour are the shared default). */
  className?: string;
  children: ReactNode;
}

export function ToggleRow({ checked, onChange, disabled = false, className = "", children }: ToggleRowProps) {
  return (
    <label className={`flex items-center gap-2 text-slate-700 ${className}`.trim()}>
      <input
        type="checkbox"
        checked={checked}
        onChange={onChange}
        disabled={disabled}
        className="h-4 w-4"
      />
      {children}
    </label>
  );
}
