import {
  Bar,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { TrendPoint } from "../types";

interface TrendChartProps {
  points: TrendPoint[];
}

function formatDateLabel(value: string): string {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export function TrendChart({ points }: TrendChartProps) {
  const data = points.map((point) => ({
    ...point,
    label: formatDateLabel(point.date),
  }));

  if (data.length === 0) {
    return (
      <div className="flex h-72 items-center justify-center text-sm text-slate-400">
        No interaction data yet.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <ComposedChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: -16 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#ded9cc" />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 11, fill: "#5a5852", fontFamily: "JetBrains Mono, monospace" }}
          axisLine={{ stroke: "#0a0a0a" }}
          tickLine={false}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "#5a5852", fontFamily: "JetBrains Mono, monospace" }}
          axisLine={false}
          tickLine={false}
          width={32}
        />
        <Tooltip
          contentStyle={{
            borderRadius: 0,
            border: "1px solid #0a0a0a",
            background: "#faf8f2",
            fontSize: 12,
            fontFamily: "JetBrains Mono, monospace",
          }}
          labelStyle={{ fontWeight: 600, color: "#0a0a0a" }}
        />
        <Bar
          dataKey="interaction_count"
          name="Questions asked"
          fill="#ebe7dd"
          stroke="#0a0a0a"
          strokeWidth={1}
          radius={[0, 0, 0, 0]}
          barSize={22}
        />
        <Line
          type="monotone"
          dataKey="negative_feedback_count"
          name="Negative feedback"
          stroke="#bc1823"
          strokeWidth={2}
          dot={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
