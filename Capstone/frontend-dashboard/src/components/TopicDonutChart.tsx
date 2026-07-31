import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { TopicSummaryItem } from "../types";
import { navigateToLogsWithFilter } from "../api";

interface TopicDonutChartProps {
  topics: TopicSummaryItem[];
}

const COLORS = [
  "#bc1823",
  "#0a0a0a",
  "#5a5852",
  "#97121b",
  "#8a8578",
  "#d6412a",
  "#3a3834",
  "#c9c3b3",
  "#e8a598",
];

export function TopicDonutChart({ topics }: TopicDonutChartProps) {
  const data = topics
    .filter((topic) => topic.interaction_count > 0)
    .map((topic) => ({
      name: topic.topic_name,
      value: topic.interaction_count,
      code: topic.topic_code,
    }));

  const total = data.reduce((sum, item) => sum + item.value, 0);

  if (data.length === 0) {
    return (
      <div className="flex h-72 items-center justify-center text-sm text-slate-400">
        No classified interactions yet.
      </div>
    );
  }

  return (
    <div className="relative">
      <ResponsiveContainer width="100%" height={300}>
        <PieChart>
          <Pie
            data={data}
            dataKey="value"
            nameKey="name"
            innerRadius={70}
            outerRadius={100}
            paddingAngle={2}
            strokeWidth={0}
            cursor="pointer"
            onClick={(entry) => {
              const point = entry as unknown as { code?: string; name?: string };
              if (point.code) navigateToLogsWithFilter("topic", point.code, point.name);
            }}
          >
            {data.map((_, index) => (
              <Cell key={index} fill={COLORS[index % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip
            contentStyle={{
              borderRadius: 0,
              border: "1px solid #0a0a0a",
              background: "#faf8f2",
              fontSize: 12,
              fontFamily: "JetBrains Mono, monospace",
            }}
          />
          <Legend
            layout="vertical"
            align="right"
            verticalAlign="middle"
            iconType="circle"
            wrapperStyle={{
              fontSize: 11,
              lineHeight: "20px",
              fontFamily: "JetBrains Mono, monospace",
              color: "#5a5852",
            }}
          />
        </PieChart>
      </ResponsiveContainer>
      <div className="pointer-events-none absolute left-[22%] top-1/2 -translate-x-1/2 -translate-y-1/2 text-center">
        <div className="text-2xl font-semibold text-[var(--ink)]">{total}</div>
        <div
          className="text-[10px] uppercase tracking-[0.14em] text-[var(--muted)]"
          style={{ fontFamily: '"JetBrains Mono", monospace' }}
        >
          Total
        </div>
      </div>
    </div>
  );
}
