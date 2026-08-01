import type { ReactNode } from "react";

interface CardProps {
  title?: string;
  subtitle?: string;
  right?: ReactNode;
  className?: string;
  children: ReactNode;
}

// Flat 1px border, no drop shadow -- matches the content-panel convention
// used across the admin app (e.g. .logs-activity-panel in styles.css).
// Shadows there are reserved for floating/overlay elements (filter forms,
// modals), not regular section panels.
export function Card({ title, subtitle, right, className = "", children }: CardProps) {
  // A flex column with a flex-1 body, so a child that asks for h-full (the
  // charts) grows to fill the card instead of leaving dead space under a
  // fixed-height plot when the grid row stretches this card to match a taller
  // sibling.
  return (
    <div
      className={`flex flex-col border border-[var(--ink)] bg-[var(--paper-light)] ${className}`}
    >
      {title || right ? (
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 border-b border-[var(--line-soft)] px-5 py-4">
          <div className="min-w-0">
            {title ? (
              <h2 className="text-[15px] font-medium text-[var(--ink)]">{title}</h2>
            ) : null}
            {subtitle ? (
              <p className="mt-0.5 font-mono text-[11px] text-[var(--muted)]">{subtitle}</p>
            ) : null}
          </div>
          {right ? <div className="shrink-0">{right}</div> : null}
        </div>
      ) : null}
      <div className="min-h-0 flex-1 p-5">{children}</div>
    </div>
  );
}
