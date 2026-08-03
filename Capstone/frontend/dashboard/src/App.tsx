import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchActiveUsers,
  fetchSummary,
  fetchTopics,
  fetchTrend,
  refreshAnalytics,
  AnalyticsApiError,
} from "./api";
import type {
  ActiveUserItem,
  AnalyticsSummary,
  DateRange,
  TopicSummaryItem,
  TrendPoint,
} from "./types";
import { KpiCard } from "./components/KpiCard";
import { TrendChart } from "./components/TrendChart";
import { TopicDonutChart } from "./components/TopicDonutChart";
import { TopicPerformanceTable } from "./components/TopicPerformanceTable";
import { ActiveUsersTable } from "./components/ActiveUsersTable";
import { Card } from "./components/Card";
import { DateRangePicker } from "./components/DateRangePicker";
import { presetRange, previousRangeFor } from "./lib/dateRange";

// null means "no meaningful baseline" (previous period was zero) rather than 0%.
function percentDelta(current: number, previous: number): number | null {
  if (previous === 0) return current === 0 ? 0 : null;
  return ((current - previous) / previous) * 100;
}

function formatRefreshedAt(value: string | null): string {
  if (!value) return "Never";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "Unknown";
  return parsed.toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatDay(value: string): string {
  const parsed = new Date(`${value}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

function formatCoverage(earliest: string | null, latest: string | null): string {
  if (!earliest || !latest) return "No data yet";
  if (earliest === latest) return formatDay(earliest);
  return `${formatDay(earliest)} – ${formatDay(latest)}`;
}

// Grid-line dividers between KPI cells, matching .logs-summary-grid's single
// bordered strip (no per-card shadow). Exactly 3 cards fit one row at sm+,
// so a single divide-x/divide-y switch is enough -- no wrapping to reason about.
const kpiGridClass =
  "mt-6 grid grid-cols-1 divide-y divide-[var(--line)] border border-[var(--ink)] bg-[var(--paper-light)] " +
  "sm:grid-cols-3 sm:divide-y-0 sm:divide-x sm:divide-[var(--line)]";

export default function App() {
  const [dateRange, setDateRange] = useState<DateRange>(() => presetRange(30));
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null);
  const [previousSummary, setPreviousSummary] = useState<AnalyticsSummary | null>(null);
  const [topics, setTopics] = useState<TopicSummaryItem[]>([]);
  const [trendPoints, setTrendPoints] = useState<TrendPoint[]>([]);
  const [activeUsers, setActiveUsers] = useState<ActiveUserItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [error, setError] = useState<string>("");

  const load = useCallback(async (range: DateRange) => {
    setError("");
    try {
      const previousRange = previousRangeFor(range);
      const [summaryData, topicsData, trendData, activeUsersData, previousSummaryData] =
        await Promise.all([
          fetchSummary(range),
          fetchTopics(range),
          fetchTrend(range),
          fetchActiveUsers(range),
          fetchSummary(previousRange),
        ]);
      setSummary(summaryData);
      setTopics(topicsData.topics);
      setTrendPoints(trendData.points);
      setActiveUsers(activeUsersData.users);
      setPreviousSummary(previousSummaryData);
    } catch (err) {
      setError(err instanceof AnalyticsApiError ? err.message : "Unable to load analytics.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(dateRange);
  }, [dateRange, load]);

  async function handleRefresh() {
    setIsRefreshing(true);
    try {
      await refreshAnalytics();
      await load(dateRange);
    } catch (err) {
      setError(err instanceof AnalyticsApiError ? err.message : "Unable to refresh analytics.");
    } finally {
      setIsRefreshing(false);
    }
  }

  const negativeFeedbackPct = useMemo(() => {
    if (!summary || summary.total_interactions === 0) return 0;
    return Math.round((summary.total_negative_feedback / summary.total_interactions) * 1000) / 10;
  }, [summary]);

  return (
    // `analytics-dashboard` is the scope hook for index.css -- see the comment
    // there. Height is left to the host app's screen container: this bundle is
    // embedded inside .screen-stack, which already owns the scroll region, so a
    // min-h-screen here would add a second full viewport of height inside it.
    <div className="analytics-dashboard bg-[var(--paper)]">
      <div className="mx-auto w-full max-w-[var(--page-max)] px-[var(--page-gutter)]">
        {/* Page heading: red-dot kicker / big Instrument Sans title with one
            accent word / red underline bar / description, with a meta block on
            the right -- the same recipe (and the same type sizes) as
            .logs-heading > .logs-intro and .policy-heading > .policy-intro in
            the host app's styles.css, so this screen does not read as a
            different design from the rest of the admin panel. */}
        <div className="flex flex-wrap items-start justify-between gap-12 border-b border-[var(--ink)] pt-18 pb-10">
          <div className="max-w-[760px]">
            <span className="font-mono mb-5 block text-[10px] uppercase tracking-[0.18em] text-[var(--red)]">
              <span aria-hidden="true" className="mr-2">
                ●
              </span>
              Dashboard / Usage Analytics
            </span>
            <h1 className="m-0 text-[clamp(52px,6vw,78px)] leading-[0.98] font-medium tracking-[-0.045em] text-[var(--ink)]">
              Usage <span className="text-[var(--red)]">Analytics</span>
            </h1>
            <span className="mt-7 block h-[3px] w-16 bg-[var(--red)]" aria-hidden="true" />
            <p className="mt-6 max-w-[680px] text-lg leading-[1.55] text-[var(--muted)]">
              Track chatbot usage, top questions, and answer quality for any date range.
            </p>
          </div>
          {/* The aggregates are a materialised table refreshed on demand, so
              "when was this last rebuilt" and "what does the warehouse actually
              cover" are the two things a reader needs to trust the numbers --
              and neither was surfaced anywhere before. */}
          <dl className="font-mono grid gap-4 text-right text-[10px] uppercase tracking-[0.14em] text-[var(--muted)]">
            <div>
              <dt>Last refreshed</dt>
              <dd className="mt-1.5 text-[13px] normal-case tracking-normal text-[var(--ink)]">
                {formatRefreshedAt(summary?.refreshed_at ?? null)}
              </dd>
            </div>
            <div>
              <dt>Data available</dt>
              <dd className="mt-1.5 text-[13px] normal-case tracking-normal text-[var(--ink)]">
                {formatCoverage(summary?.earliest_date ?? null, summary?.latest_date ?? null)}
              </dd>
            </div>
          </dl>
        </div>

        <main className="py-8">
          {error ? (
            <div className="font-mono mb-6 border border-[var(--red)] bg-[var(--red)]/5 px-4 py-3 text-sm text-[var(--deep-red)]">
              {error}
            </div>
          ) : null}

          {/* Overview toolbar: dark ink bar, same recipe as .logs-list-toolbar. */}
          <div className="flex flex-wrap items-end justify-between gap-6 border border-[var(--ink)] bg-[var(--ink)] px-6 py-5 text-[var(--paper-light)]">
            <div>
              <span className="font-mono block text-[9px] uppercase tracking-[0.14em] text-[var(--red)]">
                Overview
              </span>
              <p className="mt-1.5 text-[15px]">
                Showing {dateRange.start} to {dateRange.end}
              </p>
            </div>
            <div className="flex items-end gap-3">
              <DateRangePicker value={dateRange} onChange={setDateRange} />
              <button
                type="button"
                onClick={handleRefresh}
                disabled={isRefreshing}
                aria-label="Refresh"
                title="Refresh"
                className="grid h-11 w-11 shrink-0 place-items-center border border-[rgba(250,248,242,0.32)] bg-transparent text-[var(--paper-light)] transition hover:-translate-y-0.5 hover:border-[var(--paper-light)] hover:bg-[rgba(250,248,242,0.1)] disabled:cursor-not-allowed disabled:opacity-60"
              >
                <span
                  className={`material-symbols-outlined ${isRefreshing ? "animate-spin" : ""}`}
                  style={{ fontSize: 18 }}
                  aria-hidden="true"
                >
                  refresh
                </span>
              </button>
            </div>
          </div>

          {isLoading ? (
            <div className="flex h-64 items-center justify-center text-[var(--muted)]">Loading...</div>
          ) : (
            <>
              <section className={kpiGridClass}>
                <KpiCard
                  label="Total Questions"
                  value={String(summary?.total_interactions ?? 0)}
                  subtext="In selected range"
                  icon="forum"
                  delta={{
                    value: percentDelta(
                      summary?.total_interactions ?? 0,
                      previousSummary?.total_interactions ?? 0,
                    ),
                    goodDirection: "up",
                  }}
                />
                <KpiCard
                  label="Active Users"
                  value={String(summary?.total_unique_users ?? 0)}
                  subtext="Distinct users in range"
                  icon="group"
                  delta={{
                    value: percentDelta(
                      summary?.total_unique_users ?? 0,
                      previousSummary?.total_unique_users ?? 0,
                    ),
                    goodDirection: "up",
                  }}
                />
                <KpiCard
                  label="Negative Feedback"
                  value={String(summary?.total_negative_feedback ?? 0)}
                  subtext={`${negativeFeedbackPct}% of questions`}
                  icon="thumb_down"
                  delta={{
                    value: percentDelta(
                      summary?.total_negative_feedback ?? 0,
                      previousSummary?.total_negative_feedback ?? 0,
                    ),
                    goodDirection: "down",
                  }}
                />
              </section>

              <section className="mt-6 grid grid-cols-1 items-stretch gap-6 lg:grid-cols-3">
                <Card
                  title="Questions over time"
                  subtitle="Questions asked per day"
                  className="min-w-0 lg:col-span-2"
                >
                  <TrendChart points={trendPoints} dateRange={dateRange} />
                </Card>
                <Card title="Topic share" subtitle="Click a slice to see it in Logs">
                  <TopicDonutChart topics={topics} dateRange={dateRange} />
                </Card>
              </section>

              {/* Same 2:1 split as the charts row above, so the page keeps one
                  column rhythm the whole way down instead of switching to
                  halves partway. The users table fits the 1/3 track now that it
                  is down to two columns. */}
              <section className="mt-6 grid grid-cols-1 items-stretch gap-6 lg:grid-cols-3">
                <Card
                  title="Topic performance"
                  subtitle="Distinct employees asking per topic — click a row to see it in Logs"
                  className="min-w-0 lg:col-span-2"
                >
                  <TopicPerformanceTable topics={topics} dateRange={dateRange} />
                </Card>
                <Card
                  title="Most active users"
                  subtitle="Click a row to see it in Logs"
                  // Grid items default to min-width: auto, so without this a wide
                  // table (e.g. a long email in the User column) grows this
                  // column past its track instead of scrolling internally --
                  // the overflow-x-auto wrapper inside ActiveUsersTable never gets
                  // a chance to engage, and the whole page gets clipped/overflows
                  // horizontally at common laptop widths (~1280px).
                  className="min-w-0"
                >
                  <ActiveUsersTable users={activeUsers} dateRange={dateRange} />
                </Card>
              </section>
            </>
          )}
        </main>
      </div>
    </div>
  );
}
