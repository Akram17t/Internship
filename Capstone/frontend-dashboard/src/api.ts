import type {
  AnalyticsActiveUsersResponse,
  AnalyticsSummary,
  AnalyticsTopicsResponse,
  AnalyticsTrendResponse,
  DateRange,
} from "./types";

const LOCAL_TIME_ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone;

function rangeQuery(range?: DateRange): string {
  if (!range || (!range.start && !range.end)) return "";
  const params = new URLSearchParams();
  if (range.start) params.set("start_date", range.start);
  if (range.end) params.set("end_date", range.end);
  if (LOCAL_TIME_ZONE) params.set("tz", LOCAL_TIME_ZONE);
  return `?${params.toString()}`;
}

const AUTH_STORAGE_KEY = "ics-hr-ai-auth-v1";

interface StoredSession {
  role?: string;
  token?: string;
}

function getAdminToken(): string {
  try {
    const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
    if (!raw) return "";
    const parsed: StoredSession = JSON.parse(raw);
    if (parsed.role !== "admin") return "";
    return parsed.token || "";
  } catch {
    return "";
  }
}

export class AnalyticsApiError extends Error {}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getAdminToken();
  if (!token) {
    throw new AnalyticsApiError(
      "Not signed in as admin. Log in via the main app first, then reopen this dashboard.",
    );
  }

  const response = await fetch(path, {
    ...init,
    headers: {
      ...(init?.headers || {}),
      Authorization: `Bearer ${token}`,
    },
    cache: "no-store",
  });

  if (!response.ok) {
    let detail = `Request failed (HTTP ${response.status}).`;
    try {
      const payload = await response.json();
      detail = payload?.detail || detail;
    } catch {
      // ignore body parse errors, use default detail
    }
    throw new AnalyticsApiError(detail);
  }

  return response.json() as Promise<T>;
}

export function fetchSummary(range?: DateRange): Promise<AnalyticsSummary> {
  return request<AnalyticsSummary>(`/api/admin/analytics/summary${rangeQuery(range)}`);
}

export function fetchTopics(range?: DateRange): Promise<AnalyticsTopicsResponse> {
  return request<AnalyticsTopicsResponse>(`/api/admin/analytics/topics${rangeQuery(range)}`);
}

export function fetchTrend(range?: DateRange): Promise<AnalyticsTrendResponse> {
  return request<AnalyticsTrendResponse>(`/api/admin/analytics/trend${rangeQuery(range)}`);
}

export function fetchActiveUsers(range?: DateRange): Promise<AnalyticsActiveUsersResponse> {
  return request<AnalyticsActiveUsersResponse>(
    `/api/admin/analytics/active-users${rangeQuery(range)}`,
  );
}

export function navigateToLogsWithFilter(
  type: "user" | "topic",
  value: string,
  label?: string,
  range?: DateRange,
): void {
  const bridge = (window as unknown as {
    navigateToLogsWithFilter?: (
      type: string,
      value: string,
      label?: string,
      range?: DateRange,
    ) => void;
  }).navigateToLogsWithFilter;
  bridge?.(type, value, label, range);
}

export function refreshAnalytics(): Promise<{ buckets_written: number }> {
  return request<{ buckets_written: number }>("/api/admin/analytics/refresh", {
    method: "POST",
  });
}
