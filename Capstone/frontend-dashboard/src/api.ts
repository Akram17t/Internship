import type {
  AnalyticsActiveUsersResponse,
  AnalyticsSummary,
  AnalyticsTopicsResponse,
  AnalyticsTrendResponse,
} from "./types";

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

export function fetchSummary(): Promise<AnalyticsSummary> {
  return request<AnalyticsSummary>("/api/admin/analytics/summary");
}

export function fetchTopics(): Promise<AnalyticsTopicsResponse> {
  return request<AnalyticsTopicsResponse>("/api/admin/analytics/topics");
}

export function fetchTrend(): Promise<AnalyticsTrendResponse> {
  return request<AnalyticsTrendResponse>("/api/admin/analytics/trend");
}

export function fetchActiveUsers(): Promise<AnalyticsActiveUsersResponse> {
  return request<AnalyticsActiveUsersResponse>("/api/admin/analytics/active-users");
}

export function navigateToLogsWithFilter(
  type: "user" | "topic",
  value: string,
  label?: string,
): void {
  const bridge = (window as unknown as {
    navigateToLogsWithFilter?: (type: string, value: string, label?: string) => void;
  }).navigateToLogsWithFilter;
  bridge?.(type, value, label);
}

export function refreshAnalytics(): Promise<{ buckets_written: number }> {
  return request<{ buckets_written: number }>("/api/admin/analytics/refresh", {
    method: "POST",
  });
}
