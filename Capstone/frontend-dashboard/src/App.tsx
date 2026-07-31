import { useCallback, useEffect, useState } from "react";
import {
  fetchActiveUsers,
  fetchSummary,
  fetchTopics,
  fetchTrend,
  navigateToLogsWithFilter,
  refreshAnalytics,
  AnalyticsApiError,
} from "./api";
import type { ActiveUserItem, AnalyticsSummary, TopicSummaryItem, TrendPoint } from "./types";
import { KpiCard } from "./components/KpiCard";
import { TrendChart } from "./components/TrendChart";
import { TopicDonutChart } from "./components/TopicDonutChart";
import { TopicBarChart } from "./components/TopicBarChart";
import { ActiveUsersTable } from "./components/ActiveUsersTable";

function ChatIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5">
      <path
        d="M21 12a8.5 8.5 0 1 1-3.6-6.94L21 4v4.06A8.46 8.46 0 0 1 21 12Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function UsersIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5">
      <circle cx="9" cy="8" r="3" stroke="currentColor" strokeWidth="1.6" />
      <path
        d="M3 20c0-3 2.7-5 6-5s6 2 6 5"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
      <path d="M15 8a3 3 0 1 1 4.24 2.72" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M17 15c2.4.4 4 1.9 4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

function ThumbDownIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5">
      <path
        d="M7 14V4m0 10-3 0a2 2 0 0 1-2-2.4l1.4-6A2 2 0 0 1 5.4 4H16a2 2 0 0 1 2 2v6a2 2 0 0 1-2 2h-2l-3.5 5.5a1.5 1.5 0 0 1-2.7-1V14"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function TopicIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" className="h-5 w-5">
      <path
        d="M4 6h16M4 12h10M4 18h6"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

function RefreshIcon({ spinning }: { spinning?: boolean }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      className={`h-4 w-4 ${spinning ? "animate-spin" : ""}`}
    >
      <path
        d="M4 12a8 8 0 0 1 14-5.3M20 12a8 8 0 0 1-14 5.3M4.5 3.5v4h4M19.5 20.5v-4h-4"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export default function App() {
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [topics, setTopics] = useState<TopicSummaryItem[]>([]);
  const [trendPoints, setTrendPoints] = useState<TrendPoint[]>([]);
  const [activeUsers, setActiveUsers] = useState<ActiveUserItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string>("");

  const load = useCallback(async () => {
    setError("");
    try {
      const [summaryData, topicsData, trendData, activeUsersData] = await Promise.all([
        fetchSummary(),
        fetchTopics(),
        fetchTrend(),
        fetchActiveUsers(),
      ]);
      setSummary(summaryData);
      setTopics(topicsData.topics);
      setTrendPoints(trendData.points);
      setActiveUsers(activeUsersData.users);
    } catch (err) {
      setError(err instanceof AnalyticsApiError ? err.message : "Unable to load analytics.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleRefresh() {
    setIsRefreshing(true);
    try {
      await refreshAnalytics();
      await load();
    } catch (err) {
      setError(err instanceof AnalyticsApiError ? err.message : "Unable to refresh analytics.");
    } finally {
      setIsRefreshing(false);
    }
  }

  const dateRangeLabel =
    summary?.earliest_date && summary?.latest_date
      ? `${summary.earliest_date} to ${summary.latest_date}`
      : "No data yet";

  const topTopic = topics.slice().sort((a, b) => b.interaction_count - a.interaction_count)[0];

  return (
    <div className="min-h-screen bg-[var(--paper)]">
      <header className="border-b border-[var(--ink)] bg-[var(--paper-light)]">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-5">
          <div>
            <p
              className="text-[10px] font-medium uppercase tracking-[0.18em] text-[var(--red)]"
              style={{ fontFamily: '"JetBrains Mono", monospace' }}
            >
              ● HR Assistant / Admin
            </p>
            <h1 className="text-xl font-semibold text-[var(--ink)]">Usage Analytics</h1>
          </div>
          <button
            type="button"
            onClick={handleRefresh}
            disabled={isRefreshing}
            className="flex items-center gap-2 border border-[var(--ink)] bg-[var(--paper-light)] px-4 py-2 text-sm font-medium text-[var(--ink)] transition hover:bg-[var(--ink)] hover:text-[var(--paper)] disabled:cursor-not-allowed disabled:opacity-60"
          >
            <RefreshIcon spinning={isRefreshing} />
            {isRefreshing ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8">
        {error ? (
          <div
            className="mb-6 border border-[var(--red)] bg-[var(--red)]/5 px-4 py-3 text-sm text-[var(--deep-red)]"
            style={{ fontFamily: '"JetBrains Mono", monospace' }}
          >
            {error}
          </div>
        ) : null}

        {isLoading ? (
          <div className="flex h-64 items-center justify-center text-[var(--muted)]">Loading...</div>
        ) : (
          <>
            <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              <KpiCard
                label="Total Questions"
                value={String(summary?.total_interactions ?? 0)}
                subtext={dateRangeLabel}
                icon={<ChatIcon />}
                accent="ink"
              />
              <KpiCard
                label="Active Users"
                value={String(summary?.total_unique_users ?? 0)}
                subtext="Distinct users across all questions"
                icon={<UsersIcon />}
                accent="muted"
              />
              <KpiCard
                label="Most Discussed Topic"
                value={topTopic ? topTopic.topic_name : "-"}
                subtext={topTopic ? `${topTopic.interaction_count} questions` : "No data yet"}
                icon={<TopicIcon />}
                accent="ink"
              />
              <KpiCard
                label="Negative Feedback"
                value={String(summary?.total_negative_feedback ?? 0)}
                subtext="Thumbs-down across all topics"
                icon={<ThumbDownIcon />}
                accent="red"
              />
            </section>

            <section className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
              <div className="border border-[var(--ink)] bg-[var(--paper-light)] p-5 lg:col-span-2">
                <div className="mb-2">
                  <h2 className="text-sm font-semibold text-[var(--ink)]">Questions over time</h2>
                  <p
                    className="text-[11px] text-[var(--muted)]"
                    style={{ fontFamily: '"JetBrains Mono", monospace' }}
                  >
                    Daily volume vs. negative feedback
                  </p>
                </div>
                <TrendChart points={trendPoints} />
              </div>
              <div className="border border-[var(--ink)] bg-[var(--paper-light)] p-5">
                <div className="mb-2">
                  <h2 className="text-sm font-semibold text-[var(--ink)]">Topic share</h2>
                  <p
                    className="text-[11px] text-[var(--muted)]"
                    style={{ fontFamily: '"JetBrains Mono", monospace' }}
                  >
                    Click a slice to view those questions in Logs
                  </p>
                </div>
                <TopicDonutChart topics={topics} />
              </div>
            </section>

            <section className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
              <div className="border border-[var(--ink)] bg-[var(--paper-light)] p-5">
                <div className="mb-2">
                  <h2 className="text-sm font-semibold text-[var(--ink)]">Top topics</h2>
                  <p
                    className="text-[11px] text-[var(--muted)]"
                    style={{ fontFamily: '"JetBrains Mono", monospace' }}
                  >
                    Click a bar to view those questions in Logs
                  </p>
                </div>
                <TopicBarChart topics={topics} />
              </div>
              <div className="border border-[var(--ink)] bg-[var(--paper-light)] p-5">
                <div className="mb-3 flex items-center justify-between">
                  <h2 className="text-sm font-semibold text-[var(--ink)]">Most active users</h2>
                  <span
                    className="text-[10px] text-[var(--muted)]"
                    style={{ fontFamily: '"JetBrains Mono", monospace' }}
                  >
                    Click a row to view in Logs
                  </span>
                </div>
                <ActiveUsersTable users={activeUsers} />
              </div>
            </section>

            <section className="mt-6">
              <div className="border border-[var(--ink)] bg-[var(--paper-light)] p-5">
                <div className="mb-3 flex items-center justify-between">
                  <h2 className="text-sm font-semibold text-[var(--ink)]">Topic breakdown</h2>
                  <span
                    className="text-[10px] text-[var(--muted)]"
                    style={{ fontFamily: '"JetBrains Mono", monospace' }}
                  >
                    Refreshed{" "}
                    {summary?.refreshed_at ? new Date(summary.refreshed_at).toLocaleString() : "-"}
                  </span>
                </div>
                <div className="overflow-hidden border border-[var(--ink)]">
                  <table className="w-full text-left text-sm">
                    <thead
                      className="bg-[var(--paper-deep)] text-[10px] uppercase tracking-[0.1em] text-[var(--muted)]"
                      style={{ fontFamily: '"JetBrains Mono", monospace' }}
                    >
                      <tr>
                        <th className="px-3 py-2">Topic</th>
                        <th className="px-3 py-2 text-right">Questions</th>
                        <th className="px-3 py-2 text-right">Users</th>
                        <th className="px-3 py-2 text-right">Neg. feedback</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[var(--paper-deep)]">
                      {topics
                        .slice()
                        .sort((a, b) => b.interaction_count - a.interaction_count)
                        .map((topic) => (
                          <tr
                            key={topic.topic_code}
                            className="cursor-pointer transition hover:bg-[var(--paper-deep)]/60"
                            onClick={() =>
                              navigateToLogsWithFilter("topic", topic.topic_code, topic.topic_name)
                            }
                            title="View these questions in Logs"
                          >
                            <td className="px-3 py-2 text-[var(--ink-soft)] underline decoration-[var(--muted)]/40">
                              {topic.topic_name}
                            </td>
                            <td className="px-3 py-2 text-right font-medium text-[var(--ink)]">
                              {topic.interaction_count}
                            </td>
                            <td className="px-3 py-2 text-right text-[var(--muted)]">
                              {topic.unique_user_count}
                            </td>
                            <td className="px-3 py-2 text-right text-[var(--muted)]">
                              {topic.negative_feedback_count}
                            </td>
                          </tr>
                        ))}
                      {topics.length === 0 ? (
                        <tr>
                          <td colSpan={4} className="px-3 py-6 text-center text-[var(--muted)]">
                            No data yet.
                          </td>
                        </tr>
                      ) : null}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>
          </>
        )}
      </main>
    </div>
  );
}
