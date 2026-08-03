import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { DateRange, TopicSummaryItem } from "../types";
import { navigateToLogsWithFilter } from "../api";

interface TopicDonutChartProps {
  topics: TopicSummaryItem[];
  dateRange?: DateRange;
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

export function TopicDonutChart({ topics, dateRange }: TopicDonutChartProps) {
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
      <div className="flex h-72 items-center justify-center text-sm text-[var(--muted)]">
        No classified interactions yet.
      </div>
    );
  }

  function handleSliceClick(entry: unknown) {
    const point = entry as {
      code?: string;
      name?: string;
      payload?: { code?: string; name?: string };
    };
    const code = point.code ?? point.payload?.code;
    const name = point.name ?? point.payload?.name;
    if (code) navigateToLogsWithFilter("topic", code, name, dateRange);
  }

  return (
    <div>
      <div className="relative">
        <ResponsiveContainer width="100%" height={220}>
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              innerRadius={64}
              outerRadius={92}
              paddingAngle={2}
              strokeWidth={2}
              stroke="#faf8f2"
              cursor="pointer"
              onClick={handleSliceClick}
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
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <div className="text-2xl font-semibold text-[var(--ink)]">{total}</div>
          <div className="font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--muted)]">
            Total
          </div>
        </div>
      </div>
      {/* Single column: this card sits in a 1/3 track, so two columns left each
          legend entry ~110px wide and truncated every topic name to
          "Workplace Polic...". One column per row fits the full label. */}
      <ul className="mt-4 grid grid-cols-1 gap-y-1.5">
        {data.map((item, index) => (
          <li key={item.code}>
            <button
              type="button"
              onClick={() => handleSliceClick(item)}
              className="flex w-full items-center gap-2 rounded-sm px-1 py-0.5 text-left transition hover:bg-[var(--paper-deep)]/60"
              title={`${item.name} — view these questions in Logs`}
            >
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ backgroundColor: COLORS[index % COLORS.length] }}
                aria-hidden="true"
              />
              <span className="truncate text-[11px] text-[var(--ink-soft)]">{item.name}</span>
              <span className="font-mono ml-auto shrink-0 text-[11px] text-[var(--muted)]">
                {total > 0 ? Math.round((item.value / total) * 100) : 0}%
              </span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
