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
from backend.api.models import ActivityLogItem
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


class TrendPointItem(BaseModel):
    date: str
    interaction_count: int
    negative_feedback_count: int
    error_or_fallback_count: int


class AnalyticsTrendResponse(BaseModel):
    refreshed_at: str | None
    points: list[TrendPointItem]


class ActiveUserItem(BaseModel):
    pseudonymous_user_id: str
    display_name: str
    interaction_count: int
    negative_feedback_count: int


class AnalyticsActiveUsersResponse(BaseModel):
    refreshed_at: str | None
    users: list[ActiveUserItem]


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


@app.get("/api/admin/analytics/trend", response_model=AnalyticsTrendResponse)
def get_analytics_trend(authorization: str = Header(default="")) -> AnalyticsTrendResponse:
    # Daily time-series (summed across topics) for the dashboard's line/bar
    # combo chart, sourced from the same analytics.daily_topic_aggregates
    # table as /summary and /topics - no separate storage needed.
    _require_admin(authorization)
    _require_postgres_backend()
    rows = _aggregate_rows()

    by_date: dict[date, dict[str, int]] = {}
    for row in rows:
        bucket = by_date.setdefault(
            row.bucket_date,
            {
                "interaction_count": 0,
                "negative_feedback_count": 0,
                "error_or_fallback_count": 0,
            },
        )
        bucket["interaction_count"] += row.interaction_count
        bucket["negative_feedback_count"] += row.negative_feedback_count
        bucket["error_or_fallback_count"] += row.error_or_fallback_count

    points = [
        TrendPointItem(date=bucket_date.isoformat(), **counts)
        for bucket_date, counts in sorted(by_date.items())
    ]

    refreshed_at = max((row.refreshed_at for row in rows), default=None)
    return AnalyticsTrendResponse(
        refreshed_at=refreshed_at.isoformat() if refreshed_at else None,
        points=points,
    )


@app.get("/api/admin/analytics/active-users", response_model=AnalyticsActiveUsersResponse)
def get_analytics_active_users(
    authorization: str = Header(default=""),
) -> AnalyticsActiveUsersResponse:
    # Most-active users by interaction count, with a human-readable email
    # resolved from the linked activity_logs row - admins already see this
    # same email on the Logs screen, so this is not a new PII exposure, just
    # a ranked summary of who is asking the most questions.
    _require_admin(authorization)
    _require_postgres_backend()

    from backend.db.engine import get_session
    from backend.db.models import ActivityLog, CanonicalInteraction

    session = get_session()
    try:
        rows = session.execute(
            select(
                CanonicalInteraction.pseudonymous_user_id,
                CanonicalInteraction.feedback_rating,
                CanonicalInteraction.activity_log_id,
            ).where(CanonicalInteraction.pseudonymous_user_id.is_not(None))
        ).all()

        activity_log_ids = [row[2] for row in rows if row[2] is not None]
        email_by_log_id: dict[int, str] = {}
        if activity_log_ids:
            log_rows = session.execute(
                select(ActivityLog.id, ActivityLog.details_json).where(
                    ActivityLog.id.in_(activity_log_ids)
                )
            ).all()
            for log_id, details in log_rows:
                if isinstance(details, dict):
                    email = str(details.get("user_email") or "").strip()
                    if email:
                        email_by_log_id[log_id] = email
    finally:
        session.close()

    by_user: dict[str, dict[str, object]] = {}
    for pseudonymous_user_id, feedback_rating, activity_log_id in rows:
        bucket = by_user.setdefault(
            pseudonymous_user_id,
            {"interaction_count": 0, "negative_feedback_count": 0, "email": ""},
        )
        bucket["interaction_count"] = int(bucket["interaction_count"]) + 1
        if feedback_rating == "thumbs_down":
            bucket["negative_feedback_count"] = int(bucket["negative_feedback_count"]) + 1
        if not bucket["email"] and activity_log_id in email_by_log_id:
            bucket["email"] = email_by_log_id[activity_log_id]

    users = [
        ActiveUserItem(
            pseudonymous_user_id=pseudonymous_user_id,
            display_name=str(bucket["email"]) or f"User {pseudonymous_user_id[:8]}",
            interaction_count=int(bucket["interaction_count"]),
            negative_feedback_count=int(bucket["negative_feedback_count"]),
        )
        for pseudonymous_user_id, bucket in by_user.items()
    ]
    users.sort(key=lambda item: item.interaction_count, reverse=True)

    aggregate_rows = _aggregate_rows()
    refreshed_at = max((row.refreshed_at for row in aggregate_rows), default=None)
    return AnalyticsActiveUsersResponse(
        refreshed_at=refreshed_at.isoformat() if refreshed_at else None,
        users=users[:20],
    )


@app.get("/api/admin/analytics/logs-by-topic", response_model=list[ActivityLogItem])
def get_logs_by_topic(
    topic: str,
    limit: int = 200,
    authorization: str = Header(default=""),
) -> list[ActivityLogItem]:
    # Accurate topic filter for the Logs screen (drill-through from the
    # dashboard): joins analytics.canonical_interactions.topic_code back to
    # app.activity_logs by activity_log_id, instead of guessing from
    # keywords in the question text.
    _require_admin(authorization)
    _require_postgres_backend()

    from backend.db.engine import get_session
    from backend.db.models import ActivityLog, CanonicalInteraction

    session = get_session()
    try:
        activity_log_ids = [
            row[0]
            for row in session.execute(
                select(CanonicalInteraction.activity_log_id).where(
                    CanonicalInteraction.topic_code == topic,
                    CanonicalInteraction.activity_log_id.is_not(None),
                )
            )
        ]
        if not activity_log_ids:
            return []

        rows = session.execute(
            select(ActivityLog)
            .where(ActivityLog.id.in_(activity_log_ids))
            .order_by(ActivityLog.created_at.desc())
            .limit(max(1, min(limit, 1000)))
        ).scalars().all()
    finally:
        session.close()

    results: list[ActivityLogItem] = []
    for row in rows:
        details = dict(row.details_json) if isinstance(row.details_json, dict) else {}
        details.pop("feedback_token", None)
        results.append(
            ActivityLogItem(
                id=row.id,
                event_type=row.event_type,
                action=row.action,
                status=row.status,
                summary=row.summary,
                details=details,
                created_at=row.created_at.isoformat(),
            )
        )
    return results
