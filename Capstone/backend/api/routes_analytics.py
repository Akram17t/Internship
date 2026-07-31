from __future__ import annotations

"""Simplified analytics dashboard endpoints (PostgreSQL backend only).

Reduced-scope replacement for the design's full analytics API surface:
just a summary and a topics breakdown, both admin-only, both reading from
analytics.daily_topic_aggregates (with an on-demand refresh trigger). No
keyset pagination, no export endpoint, no PII detail/audit endpoint, no
per-user ranking endpoint.

These routes only function when DATABASE_BACKEND=postgres; if the app is
running on the SQLite backend they return 503 so the rest of the app keeps
working unaffected.
"""

from datetime import date, datetime, timezone

from fastapi import Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from backend.analytics.refresh import refresh_daily_aggregates
from backend.analytics.topics import topic_display_name
from backend.api.auth import _require_admin
from backend.api.core import app
from backend.settings import get_env


class TopicSummaryItem(BaseModel):
    topic_code: str
    topic_name: str
    interaction_count: int
    unique_user_count: int
    negative_feedback_count: int
    error_or_fallback_count: int


class AnalyticsSummaryResponse(BaseModel):
    total_interactions: int
    total_unique_users: int
    total_negative_feedback: int
    total_error_or_fallback: int
    unclassified_percentage: float
    refreshed_at: str | None
    earliest_date: str | None
    latest_date: str | None


class AnalyticsTopicsResponse(BaseModel):
    refreshed_at: str | None
    topics: list[TopicSummaryItem]


def _require_postgres_backend() -> None:
    if get_env("DATABASE_BACKEND", "sqlite").strip().lower() != "postgres":
        raise HTTPException(
            status_code=503,
            detail="Analytics dashboard requires DATABASE_BACKEND=postgres.",
        )


def _aggregate_rows():
    from backend.db.engine import get_session
    from backend.db.models import DailyTopicAggregate

    session = get_session()
    try:
        return session.execute(select(DailyTopicAggregate)).scalars().all()
    finally:
        session.close()


@app.post("/api/admin/analytics/refresh")
def refresh_analytics(authorization: str = Header(default="")) -> dict[str, int | str]:
    # Recompute analytics.daily_topic_aggregates from canonical_interactions.
    _require_admin(authorization)
    _require_postgres_backend()
    written = refresh_daily_aggregates()
    return {"buckets_written": written, "refreshed_at": datetime.now(timezone.utc).isoformat()}


@app.get("/api/admin/analytics/summary", response_model=AnalyticsSummaryResponse)
def get_analytics_summary(authorization: str = Header(default="")) -> AnalyticsSummaryResponse:
    _require_admin(authorization)
    _require_postgres_backend()
    rows = _aggregate_rows()

    total_interactions = sum(row.interaction_count for row in rows)
    total_negative_feedback = sum(row.negative_feedback_count for row in rows)
    total_error_or_fallback = sum(row.error_or_fallback_count for row in rows)
    unclassified_interactions = sum(
        row.interaction_count for row in rows if row.topic_code == "unclassified"
    )
    # unique_user_count is per (date, topic) bucket and cannot be summed
    # exactly across buckets without double counting; expose it per-topic in
    # the /topics endpoint instead, and report a best-effort max here.
    total_unique_users = max((row.unique_user_count for row in rows), default=0)

    dates = [row.bucket_date for row in rows]
    refreshed_at = max((row.refreshed_at for row in rows), default=None)
    unclassified_percentage = (
        round((unclassified_interactions / total_interactions) * 100, 2)
        if total_interactions
        else 0.0
    )

    return AnalyticsSummaryResponse(
        total_interactions=total_interactions,
        total_unique_users=total_unique_users,
        total_negative_feedback=total_negative_feedback,
        total_error_or_fallback=total_error_or_fallback,
        unclassified_percentage=unclassified_percentage,
        refreshed_at=refreshed_at.isoformat() if refreshed_at else None,
        earliest_date=min(dates).isoformat() if dates else None,
        latest_date=max(dates).isoformat() if dates else None,
    )


@app.get("/api/admin/analytics/topics", response_model=AnalyticsTopicsResponse)
def get_analytics_topics(authorization: str = Header(default="")) -> AnalyticsTopicsResponse:
    _require_admin(authorization)
    _require_postgres_backend()
    rows = _aggregate_rows()

    by_topic: dict[str, dict[str, int]] = {}
    for row in rows:
        bucket = by_topic.setdefault(
            row.topic_code,
            {
                "interaction_count": 0,
                "unique_user_count": 0,
                "negative_feedback_count": 0,
                "error_or_fallback_count": 0,
            },
        )
        bucket["interaction_count"] += row.interaction_count
        # unique_user_count is summed across daily buckets here as a simple
        # approximation (a user active on multiple days is counted once per
        # day); exact all-time distinct-user counts are out of scope for
        # this simplified aggregate table.
        bucket["unique_user_count"] += row.unique_user_count
        bucket["negative_feedback_count"] += row.negative_feedback_count
        bucket["error_or_fallback_count"] += row.error_or_fallback_count

    topics = [
        TopicSummaryItem(
            topic_code=topic_code,
            topic_name=topic_display_name(topic_code)
            if topic_code != "unclassified"
            else "Unclassified",
            **counts,
        )
        for topic_code, counts in by_topic.items()
    ]
    topics.sort(key=lambda item: item.interaction_count, reverse=True)

    refreshed_at = max((row.refreshed_at for row in rows), default=None)
    return AnalyticsTopicsResponse(
        refreshed_at=refreshed_at.isoformat() if refreshed_at else None,
        topics=topics,
    )
