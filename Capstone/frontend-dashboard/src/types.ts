export interface TopicSummaryItem {
  topic_code: string;
  topic_name: string;
  interaction_count: number;
  unique_user_count: number;
  negative_feedback_count: number;
  error_or_fallback_count: number;
}

export interface AnalyticsSummary {
  total_interactions: number;
  total_unique_users: number;
  total_negative_feedback: number;
  total_error_or_fallback: number;
  unclassified_percentage: number;
  refreshed_at: string | null;
  earliest_date: string | null;
  latest_date: string | null;
}

export interface AnalyticsTopicsResponse {
  refreshed_at: string | null;
  topics: TopicSummaryItem[];
}

export interface TrendPoint {
  date: string;
  interaction_count: number;
  negative_feedback_count: number;
  error_or_fallback_count: number;
}

export interface AnalyticsTrendResponse {
  refreshed_at: string | null;
  points: TrendPoint[];
}

export interface ActiveUserItem {
  pseudonymous_user_id: string;
  display_name: string;
  interaction_count: number;
  negative_feedback_count: number;
}

export interface AnalyticsActiveUsersResponse {
  refreshed_at: string | null;
  users: ActiveUserItem[];
}
