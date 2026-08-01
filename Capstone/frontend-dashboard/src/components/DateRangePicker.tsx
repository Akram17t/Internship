import { useMemo } from "react";
import type { DateRange } from "../types";
import { presetRange } from "../lib/dateRange";

interface DateRangePickerProps {
  value: DateRange;
  onChange: (range: DateRange) => void;
}

const PRESETS = [
  { label: "7D", days: 7 },
  { label: "30D", days: 30 },
  { label: "90D", days: 90 },
];

// Styled for the dark .logs-list-toolbar-style bar it lives in (see the
// Overview toolbar in App.tsx) -- translucent white fields on ink, matching
// .logs-screen .logs-date-field / .logs-search-field in styles.css exactly.
export function DateRangePicker({ value, onChange }: DateRangePickerProps) {
  const activePresetDays = useMemo(() => {
    const match = PRESETS.find((preset) => {
      const range = presetRange(preset.days);
      return range.start === value.start && range.end === value.end;
    });
    return match?.days;
  }, [value]);

  // items-end throughout: the Start/End fields stack a caption above their
  // input, so a centred row left the presets and the inputs on three different
  // baselines. Bottom-aligning gives every control one shared edge, and the h-11
  // on the presets matches the inputs and the refresh button beside them.
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="flex items-end gap-1.5">
        {PRESETS.map((preset) => {
          const isActive = activePresetDays === preset.days;
          return (
            <button
              key={preset.days}
              type="button"
              onClick={() => onChange(presetRange(preset.days))}
              aria-pressed={isActive}
              className={`font-mono h-11 rounded-full border px-4 text-[11px] font-medium uppercase tracking-[0.06em] transition ${
                isActive
                  ? "border-[var(--red)] bg-[var(--red)] text-white"
                  : "border-[rgba(250,248,242,0.32)] bg-transparent text-[rgba(250,248,242,0.75)] hover:bg-[rgba(250,248,242,0.1)]"
              }`}
            >
              {preset.label}
            </button>
          );
        })}
      </div>
      <label className="font-mono grid gap-1.5 text-[9px] uppercase tracking-[0.12em] text-[rgba(250,248,242,0.56)]">
        Start
        <input
          type="date"
          value={value.start}
          max={value.end || undefined}
          onChange={(event) => onChange({ ...value, start: event.target.value })}
          style={{ colorScheme: "dark" }}
          className="h-11 w-[142px] border border-[rgba(250,248,242,0.32)] bg-[rgba(250,248,242,0.06)] px-2.5 text-[12px] font-normal text-[var(--paper-light)] outline-none transition focus:border-[var(--red)] focus:bg-[rgba(250,248,242,0.1)]"
        />
      </label>
      <label className="font-mono grid gap-1.5 text-[9px] uppercase tracking-[0.12em] text-[rgba(250,248,242,0.56)]">
        End
        <input
          type="date"
          value={value.end}
          min={value.start || undefined}
          onChange={(event) => onChange({ ...value, end: event.target.value })}
          style={{ colorScheme: "dark" }}
          className="h-11 w-[142px] border border-[rgba(250,248,242,0.32)] bg-[rgba(250,248,242,0.06)] px-2.5 text-[12px] font-normal text-[var(--paper-light)] outline-none transition focus:border-[var(--red)] focus:bg-[rgba(250,248,242,0.1)]"
        />
      </label>
    </div>
  );
}
