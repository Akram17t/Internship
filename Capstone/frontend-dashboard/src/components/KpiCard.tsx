interface KpiCardDelta {
  /** Percent change vs. the equal-length prior period; null when not computable (e.g. no prior data). */
  value: number | null;
  /** Which direction counts as an improvement. Defaults to "up". */
  goodDirection?: "up" | "down";
}

interface KpiCardProps {
  label: string;
  value: string;
  subtext?: string;
  /** Material Symbols Outlined ligature name, e.g. "forum". */
  icon: string;
  delta?: KpiCardDelta;
}

function DeltaChip({ delta }: { delta: KpiCardDelta }) {
  if (delta.value === null || !Number.isFinite(delta.value)) {
    return <span className="font-mono text-[10px] text-[var(--muted)]">No prior-period data</span>;
  }

  const rounded = Math.round(delta.value * 10) / 10;
  const isFlat = Math.abs(rounded) < 0.5;
  const direction: "up" | "down" = rounded >= 0 ? "up" : "down";
  const goodDirection = delta.goodDirection ?? "up";
  const isGood = direction === goodDirection;
  const colorClass = isFlat || isGood ? "text-[var(--muted)]" : "text-[var(--red)]";
  const arrow = isFlat ? "→" : direction === "up" ? "▲" : "▼";

  return (
    <span className={`font-mono inline-flex items-center gap-1 text-[10px] font-medium ${colorClass}`}>
      <span aria-hidden="true">{arrow}</span>
      {Math.abs(rounded)}% vs prior period
    </span>
  );
}

// One cell of the shared .logs-summary-grid-style strip (see KpiCardRow in
// App.tsx): no border/shadow of its own, big thin-weight value, red
// Material Symbol -- matches the KPI cards already used on the Logs screen.
export function KpiCard({ label, value, subtext, icon, delta }: KpiCardProps) {
  return (
    <div className="group relative overflow-hidden px-6 py-[22px] transition-[background-color,transform] duration-200 hover:-translate-y-[3px] hover:bg-[var(--paper-deep)]">
      <div className="flex items-center justify-between gap-4">
        <span className="text-[15px] text-[var(--ink)]">{label}</span>
        <span
          className="material-symbols-outlined shrink-0 text-[var(--red)]"
          style={{ fontSize: 20 }}
          aria-hidden="true"
        >
          {icon}
        </span>
      </div>
      <strong
        className="mt-6 block truncate text-[42px] font-normal leading-none text-[var(--ink)]"
        title={value}
      >
        {value}
      </strong>
      {subtext ? (
        <small className="mt-3 block truncate text-[12px] font-normal text-[var(--muted)]">
          {subtext}
        </small>
      ) : null}
      {delta ? <div className="mt-2">{<DeltaChip delta={delta} />}</div> : null}
      <span
        className="pointer-events-none absolute inset-x-0 bottom-0 h-1 origin-left scale-x-0 bg-[var(--red)] transition-transform duration-200 group-hover:scale-x-100"
        aria-hidden="true"
      />
    </div>
  );
}
