import { useMemo, useState } from "react";
import type { DateRange, TopicSummaryItem } from "../types";
import { navigateToLogsWithFilter } from "../api";

interface TopicPerformanceTableProps {
  topics: TopicSummaryItem[];
  dateRange?: DateRange;
}

type SortKey = "interaction_count" | "unique_user_count";

export function TopicPerformanceTable({ topics, dateRange }: TopicPerformanceTableProps) {
  // Unique users, not raw question count: the question this table answers is
  // "how many different employees were curious about this topic", and volume
  // alone lets one person asking the same thing ten times outrank a topic ten
  // separate people asked about once. Sorting by volume is still one click away.
  const [sortKey, setSortKey] = useState<SortKey>("unique_user_count");

  const sorted = useMemo(
    () =>
      topics
        .slice()
        // Volume breaks ties so equal-curiosity topics keep a stable, meaningful
        // order instead of falling back to whatever the API happened to return.
        .sort((a, b) => b[sortKey] - a[sortKey] || b.interaction_count - a.interaction_count),
    [topics, sortKey],
  );

  // The bar tracks whichever column is sorted, so the visual weight always
  // belongs to the metric being ranked by.
  const maxCount = Math.max(1, ...topics.map((topic) => topic[sortKey]));

  if (topics.length === 0) {
    return (
      <div className="flex h-72 items-center justify-center text-sm text-[var(--muted)]">
        No classified interactions yet.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-sm">
        <thead className="bg-[var(--paper-deep)] text-[11px] text-[var(--muted)]">
          <tr>
            <th className="border-b border-[var(--line)] py-2.5 pr-3 pl-3 font-normal">Topic</th>
            <th className="w-2/5 border-b border-[var(--line)] py-2.5 pr-3 font-normal">
              <button
                type="button"
                onClick={() => setSortKey("unique_user_count")}
                className={`flex items-center gap-1 whitespace-nowrap transition hover:text-[var(--ink)] ${
                  sortKey === "unique_user_count" ? "text-[var(--ink)]" : ""
                }`}
              >
                Users asking{" "}
                <span className={sortKey === "unique_user_count" ? "" : "invisible"}>▼</span>
              </button>
            </th>
            <th className="border-b border-[var(--line)] py-2.5 pr-3 text-right font-normal">
              <button
                type="button"
                onClick={() => setSortKey("interaction_count")}
                className={`ml-auto flex items-center gap-1 whitespace-nowrap transition hover:text-[var(--ink)] ${
                  sortKey === "interaction_count" ? "text-[var(--ink)]" : ""
                }`}
              >
                Questions{" "}
                <span className={sortKey === "interaction_count" ? "" : "invisible"}>▼</span>
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((topic) => {
            const ranked = topic[sortKey];
            const barWidth = ranked === 0 ? 0 : Math.max(4, (ranked / maxCount) * 100);
            return (
              <tr
                key={topic.topic_code}
                className="group cursor-pointer border-b border-[var(--line-soft)] transition last:border-b-0 hover:bg-[rgba(188,24,35,0.045)]"
                onClick={() =>
                  navigateToLogsWithFilter("topic", topic.topic_code, topic.topic_name, dateRange)
                }
                title="View these questions in Logs"
              >
                <td className="border-l-4 border-transparent py-3 pr-3 pl-3 text-[15px] text-[var(--ink)] transition-colors group-hover:border-l-[var(--red)]">
                  {topic.topic_name}
                </td>
                <td className="py-3 pr-3">
                  <div className="flex items-center gap-2">
                    <div className="h-2 flex-1 rounded-full bg-[var(--paper-deep)]">
                      <div
                        className="h-2"
                        style={{
                          width: `${barWidth}%`,
                          backgroundColor: "var(--red)",
                          borderTopRightRadius: 4,
                          borderBottomRightRadius: 4,
                        }}
                      />
                    </div>
                    <span className="font-mono w-10 shrink-0 text-right tabular-nums text-[var(--ink)]">
                      {sortKey === "unique_user_count"
                        ? topic.unique_user_count
                        : topic.interaction_count}
                    </span>
                  </div>
                </td>
                <td className="py-3 pr-3 text-right font-mono tabular-nums text-[var(--muted)]">
                  {sortKey === "unique_user_count"
                    ? topic.interaction_count
                    : topic.unique_user_count}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
