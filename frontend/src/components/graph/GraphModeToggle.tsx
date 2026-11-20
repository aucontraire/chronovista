/**
 * GraphModeToggle — Connect / Explore mode switch (Feature 115, FR-010).
 *
 * A two-option radio group: native arrow-key behaviour, a single tab stop, and the
 * state is never carried by colour alone (the checked option is also bold + bordered).
 */

export type GraphMode = "connect" | "explore";

interface GraphModeToggleProps {
  mode: GraphMode;
  onChange: (mode: GraphMode) => void;
}

const OPTIONS: { value: GraphMode; label: string }[] = [
  { value: "connect", label: "Connect" },
  { value: "explore", label: "Explore" },
];

export function GraphModeToggle({ mode, onChange }: GraphModeToggleProps) {
  return (
    <fieldset className="flex items-center gap-2">
      <legend className="sr-only">Graph mode</legend>
      {OPTIONS.map(({ value, label }) => (
        <label
          key={value}
          className={`cursor-pointer rounded-md border px-3 py-1 text-sm focus-within:ring-2 focus-within:ring-indigo-600 ${
            mode === value
              ? "border-indigo-700 bg-indigo-50 font-semibold text-indigo-900"
              : "border-slate-300 text-slate-700"
          }`}
        >
          <input
            type="radio"
            name="graph-mode"
            value={value}
            checked={mode === value}
            onChange={() => onChange(value)}
            className="sr-only"
          />
          {label}
        </label>
      ))}
    </fieldset>
  );
}
