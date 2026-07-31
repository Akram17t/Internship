import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { TopicSummaryItem } from "../types";
import { navigateToLogsWithFilter } from "../api";

interface TopicBarChartProps {
  topics: TopicSummaryItem[];
}

export function TopicBarChart({ topics }: TopicBarChartProps) {
  const data = topics
    .slice()
    .sort((a, b) => b.interaction_count - a.interaction_count)
    .slice(0, 8)
    .map((topic) => ({
      name: topic.topic_name,
      count: topic.interaction_count,
      code: topic.topic_code,
      isUnclassified: topic.topic_code === "unclassified",
    }));

  if (data.length === 0) {
    return (
      <div className="flex h-72 items-center justify-center text-sm text-slate-400">
        No classified interactions yet.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data} layout="vertical" margin={{ top: 8, right: 24, bottom: 0, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#ded9cc" />
        <XAxis
          type="number"
          tick={{ fontSize: 11, fill: "#5a5852", fontFamily: "JetBrains Mono, monospace" }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          type="category"
          dataKey="name"
          width={160}
          tick={{ fontSize: 11, fill: "#0a0a0a", fontFamily: "JetBrains Mono, monospace" }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          contentStyle={{
            borderRadius: 0,
            border: "1px solid #0a0a0a",
            background: "#faf8f2",
            fontSize: 12,
            fontFamily: "JetBrains Mono, monospace",
          }}
        />
        <Bar
          dataKey="count"
          name="Interactions"
          radius={[0, 0, 0, 0]}
          barSize={18}
          cursor="pointer"
          onClick={(entry) => {
            const point = entry as unknown as { code?: string; name?: string };
            if (point.code) navigateToLogsWithFilter("topic", point.code, point.name);
          }}
        >
          {data.map((entry, index) => (
            <Cell key={index} fill={entry.isUnclassified ? "#8a8578" : "#bc1823"} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
