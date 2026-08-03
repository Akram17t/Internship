import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { DateRange, TrendPoint } from "../types";
import { eachDayOfRange } from "../lib/dateRange";

interface TrendChartProps {
  points: TrendPoint[];
  dateRange: DateRange;
}

// One series, one colour. Negative feedback has its own KPI tile and is not
// plotted here: at 1-2 events against daily volumes in the teens it added a
// segment too small to read while making the chart look like it carried two
// stories. Contrast against the #faf8f2 card surface clears 3:1.
const BAR_FILL = "#8a8578";
const AXIS_TEXT = "#5a5852";
const GRID = "#e1e0d9";

interface TrendDatum {
  date: string;
  label: string;
  total: number;
}

function formatDateLabel(value: string): string {
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

// Draw every Nth tick so labels never collide -- a 90-day range would otherwise
// try to fit 90 dates across ~600px.
function tickInterval(count: number): number {
  if (count <= 14) return 0;
  return Math.ceil(count / 12) - 1;
}

function TrendTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: TrendDatum }>;
}) {
  if (!active || !payload?.length) return null;
  const point = payload[0].payload;
  return (
    <div className="border border-[var(--ink)] bg-[var(--paper-light)] px-3 py-2">
      <div className="font-mono text-[11px] font-semibold text-[var(--ink)]">{point.label}</div>
      <div className="mt-1.5 flex items-center gap-2 text-[12px]">
        <span className="text-[var(--muted)]">Questions asked</span>
        <span className="font-mono ml-auto pl-4 text-[var(--ink)]">{point.total}</span>
      </div>
    </div>
  );
}

export function TrendChart({ points, dateRange }: TrendChartProps) {
  const data = useMemo<TrendDatum[]>(() => {
    const byDate = new Map(points.map((point) => [point.date, point]));
    const filled = eachDayOfRange(dateRange).map((date) => ({
      date,
      label: formatDateLabel(date),
      total: byDate.get(date)?.interaction_count ?? 0,
    }));

    // Trim only the leading and trailing runs of empty days. A selected window
    // routinely starts before the warehouse has any rows at all (a 30-day range
    // over two weeks of data), and plotting that lead-in spends half the axis on
    // days that could not have had traffic. Interior zeros are kept -- those are
    // real quiet days and dropping them would break the time axis.
    const firstActive = filled.findIndex((point) => point.total > 0);
    if (firstActive === -1) return filled;
    let lastActive = filled.length - 1;
    while (lastActive > firstActive && filled[lastActive].total === 0) lastActive -= 1;
    return filled.slice(firstActive, lastActive + 1);
  }, [points, dateRange]);

  const hasData = data.some((point) => point.total > 0);

  if (!hasData) {
    return (
      <div className="flex h-full min-h-[260px] items-center justify-center text-sm text-[var(--muted)]">
        No interaction data yet.
      </div>
    );
  }

  // No legend: a single series needs none, the card title already names it.
  return (
    <div className="h-full min-h-[260px]">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart
          data={data}
          margin={{ top: 8, right: 4, bottom: 0, left: 0 }}
          // 2px of surface between neighbours, so the columns keep presence
          // instead of thinning to slivers once a 30-day range is plotted.
          barCategoryGap={2}
        >
          <CartesianGrid vertical={false} stroke={GRID} strokeWidth={1} />
          <XAxis
            dataKey="label"
            interval={tickInterval(data.length)}
            tick={{ fontSize: 11, fill: AXIS_TEXT, fontFamily: "JetBrains Mono, monospace" }}
            axisLine={{ stroke: GRID }}
            tickLine={false}
            tickMargin={8}
            minTickGap={4}
          />
          <YAxis
            allowDecimals={false}
            tick={{ fontSize: 11, fill: AXIS_TEXT, fontFamily: "JetBrains Mono, monospace" }}
            axisLine={false}
            tickLine={false}
            width={32}
          />
          <Tooltip content={<TrendTooltip />} cursor={{ fill: "rgba(10,10,10,0.04)" }} />
          <Bar
            dataKey="total"
            fill={BAR_FILL}
            radius={[4, 4, 0, 0]}
            maxBarSize={24}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
