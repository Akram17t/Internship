import type { DateRange } from "../types";

export function toInputValue(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function presetRange(days: number): DateRange {
  const end = new Date();
  const start = new Date();
  start.setDate(end.getDate() - (days - 1));
  return { start: toInputValue(start), end: toInputValue(end) };
}

/**
 * Every calendar day in `range`, inclusive, as YYYY-MM-DD.
 *
 * The trend endpoint only returns days that actually have interactions, so a
 * 30-day window with activity on 9 days used to plot 9 columns spread across
 * the full width -- the gaps between dates silently disappeared and the x-axis
 * stopped being a real time axis. Charts fill against this list instead.
 */
export function eachDayOfRange(range: DateRange): string[] {
  const start = new Date(`${range.start}T00:00:00`);
  const end = new Date(`${range.end}T00:00:00`);
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || end < start) {
    return [];
  }
  const days: string[] = [];
  const cursor = new Date(start);
  while (cursor <= end) {
    days.push(toInputValue(cursor));
    cursor.setDate(cursor.getDate() + 1);
  }
  return days;
}

// Equal-length window immediately preceding `range`, used to compute the
// KPI strip's vs.-prior-period deltas (e.g. the 30 days before a 30-day range).
export function previousRangeFor(range: DateRange): DateRange {
  const start = new Date(`${range.start}T00:00:00`);
  const end = new Date(`${range.end}T00:00:00`);
  const lengthDays = Math.round((end.getTime() - start.getTime()) / 86_400_000) + 1;
  const previousEnd = new Date(start);
  previousEnd.setDate(previousEnd.getDate() - 1);
  const previousStart = new Date(previousEnd);
  previousStart.setDate(previousStart.getDate() - (lengthDays - 1));
  return { start: toInputValue(previousStart), end: toInputValue(previousEnd) };
}
