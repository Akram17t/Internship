import type { ReactNode } from "react";

interface KpiCardProps {
  label: string;
  value: string;
  subtext?: string;
  icon: ReactNode;
  accent?: "red" | "ink" | "muted";
}

const accentStyles: Record<Required<KpiCardProps>["accent"], string> = {
  red: "bg-[var(--red)]/10 text-[var(--red)]",
  ink: "bg-[var(--ink)]/5 text-[var(--ink)]",
  muted: "bg-[var(--muted)]/10 text-[var(--muted)]",
};

export function KpiCard({ label, value, subtext, icon, accent = "ink" }: KpiCardProps) {
  return (
    <div className="rounded-none border border-[var(--ink)] bg-[var(--paper-light)] p-5">
      <div className="flex items-start justify-between">
        <span
          className="text-[10px] font-medium uppercase tracking-[0.14em] text-[var(--muted)]"
          style={{ fontFamily: '"JetBrains Mono", monospace' }}
        >
          {label}
        </span>
        <div className={`flex h-8 w-8 items-center justify-center ${accentStyles[accent]}`}>
          {icon}
        </div>
      </div>
      <div className="mt-3 text-3xl font-semibold tracking-tight text-[var(--ink)]">{value}</div>
      {subtext ? (
        <p
          className="mt-1 text-[11px] text-[var(--muted)]"
          style={{ fontFamily: '"JetBrains Mono", monospace' }}
        >
          {subtext}
        </p>
      ) : null}
    </div>
  );
}
