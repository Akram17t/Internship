from __future__ import annotations

"""Simplified analytics dashboard endpoints.

Reduced-scope replacement for the design's full analytics API surface:
just a summary and a topics breakdown, both admin-only, both reading from
analytics.daily_topic_aggregates (with an on-demand refresh trigger). No
keyset pagination, no export endpoint, no PII detail/audit endpoint, no
per-user ranking endpoint.
"""

from datetime import date, datetime, timezone
from typing import Annotated

from fastapi import Header, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from backend.analytics.refresh import refresh_daily_aggregates
from backend.analytics.topics import KNOWN_TOPIC_CODES, topic_display_name
from backend.api.auth import _require_admin
from backend.api.core import app
from backend.api.models import ActivityLogItem
from backend.api.routes_admin import _activity_date_range


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


def _resolve_range(
    start_date: str | None, end_date: str | None, tz: str | None
) -> tuple[datetime, datetime]:
    # Mirrors the Logs screen's date-range semantics exactly (same helper,
    # same 30-day default, same 422 on bad input) so switching between
    # Analytics and Logs with the same range feels consistent.
    start_iso, end_iso = _activity_date_range(start_date, end_date, tz)
    return datetime.fromisoformat(start_iso), datetime.fromisoformat(end_iso)


def _aggregate_rows(start_at: datetime | None = None, end_at: datetime | None = None):
    from backend.db.engine import get_session
    from backend.db.models import DailyTopicAggregate

    session = get_session()
    try:
        stmt = select(DailyTopicAggregate)
        if start_at is not None and end_at is not None:
            # bucket_date is written as occurred_at.date() in UTC (see
            # backend/analytics/refresh.py), so this is a day-granularity
            # filter, not full tz precision -- acceptable, pre-existing
            # behavior for the aggregate table.
            stmt = stmt.where(
                DailyTopicAggregate.bucket_date.between(start_at.date(), end_at.date())
            )
        return session.execute(stmt).scalars().all()
    finally:
        session.close()


def _canonical_unique_user_counts(
    start_at: datetime | None = None, end_at: datetime | None = None
) -> tuple[int, dict[str, int]]:
    """Return exact distinct-user counts overall and per topic for the given range."""
    from backend.db.engine import get_session
    from backend.db.models import CanonicalInteraction

    session = get_session()
    try:
        user_column = CanonicalInteraction.pseudonymous_user_id
        base_filter = user_column.is_not(None)
        if start_at is not None and end_at is not None:
            base_filter = base_filter & CanonicalInteraction.occurred_at.between(start_at, end_at)
        total = session.execute(
            select(func.count(func.distinct(user_column))).where(base_filter)
        ).scalar_one()
        rows = session.execute(
            select(
                CanonicalInteraction.topic_code,
                func.count(func.distinct(user_column)),
            )
            .where(base_filter)
            .group_by(CanonicalInteraction.topic_code)
        ).all()
        return int(total or 0), {str(topic_code): int(count or 0) for topic_code, count in rows}
    finally:
        session.close()


@app.post("/api/admin/analytics/refresh")
def refresh_analytics(authorization: str = Header(default="")) -> dict[str, int | str]:
    # Recompute analytics.daily_topic_aggregates from canonical_interactions.
    _require_admin(authorization)
    written = refresh_daily_aggregates()
    return {"buckets_written": written, "refreshed_at": datetime.now(timezone.utc).isoformat()}


@app.get("/api/admin/analytics/summary", response_model=AnalyticsSummaryResponse)
def get_analytics_summary(
    start_date: str | None = None,
    end_date: str | None = None,
    tz: str | None = None,
    authorization: str = Header(default=""),
) -> AnalyticsSummaryResponse:
    _require_admin(authorization)
    start_at, end_at = _resolve_range(start_date, end_date, tz)
    rows = _aggregate_rows(start_at, end_at)

    total_interactions = sum(row.interaction_count for row in rows)
    total_negative_feedback = sum(row.negative_feedback_count for row in rows)
    total_error_or_fallback = sum(row.error_or_fallback_count for row in rows)
    unclassified_interactions = sum(
        row.interaction_count for row in rows if row.topic_code == "unclassified"
    )
    total_unique_users, _unique_users_by_topic = _canonical_unique_user_counts(start_at, end_at)

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
def get_analytics_topics(
    start_date: str | None = None,
    end_date: str | None = None,
    tz: str | None = None,
    authorization: str = Header(default=""),
) -> AnalyticsTopicsResponse:
    _require_admin(authorization)
    start_at, end_at = _resolve_range(start_date, end_date, tz)
    rows = _aggregate_rows(start_at, end_at)
    _total_unique_users, unique_users_by_topic = _canonical_unique_user_counts(start_at, end_at)

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
        bucket["unique_user_count"] = unique_users_by_topic.get(row.topic_code, 0)
        bucket["negative_feedback_count"] += row.negative_feedback_count
        bucket["error_or_fallback_count"] += row.error_or_fallback_count

    # "unclassified" is not a real topic -- dropped from the dashboard
    # entirely (donut/table) rather than shown as its own category.
    topics = [
        TopicSummaryItem(topic_code=topic_code, topic_name=topic_display_name(topic_code), **counts)
        for topic_code, counts in by_topic.items()
        if topic_code != "unclassified"
    ]
    topics.sort(key=lambda item: item.interaction_count, reverse=True)

    refreshed_at = max((row.refreshed_at for row in rows), default=None)
    return AnalyticsTopicsResponse(
        refreshed_at=refreshed_at.isoformat() if refreshed_at else None,
        topics=topics,
    )


@app.get("/api/admin/analytics/trend", response_model=AnalyticsTrendResponse)
def get_analytics_trend(
    start_date: str | None = None,
    end_date: str | None = None,
    tz: str | None = None,
    authorization: str = Header(default=""),
) -> AnalyticsTrendResponse:
    # Daily time-series (summed across topics) for the dashboard's line/bar
    # combo chart, sourced from the same analytics.daily_topic_aggregates
    # table as /summary and /topics - no separate storage needed.
    _require_admin(authorization)
    start_at, end_at = _resolve_range(start_date, end_date, tz)
    rows = _aggregate_rows(start_at, end_at)

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
    start_date: str | None = None,
    end_date: str | None = None,
    tz: str | None = None,
    authorization: str = Header(default=""),
) -> AnalyticsActiveUsersResponse:
    # Most-active users by interaction count, with a human-readable email
    # resolved from the linked activity_logs row - admins already see this
    # same email on the Logs screen, so this is not a new PII exposure, just
    # a ranked summary of who is asking the most questions.
    _require_admin(authorization)
    start_at, end_at = _resolve_range(start_date, end_date, tz)

    from backend.db.engine import get_session
    from backend.db.models import ActivityLog, CanonicalInteraction

    session = get_session()
    try:
        rows = session.execute(
            select(
                CanonicalInteraction.pseudonymous_user_id,
                CanonicalInteraction.feedback_rating,
                CanonicalInteraction.activity_log_id,
            ).where(
                CanonicalInteraction.pseudonymous_user_id.is_not(None),
                CanonicalInteraction.occurred_at.between(start_at, end_at),
            )
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
    topic: Annotated[str, Query(min_length=1, max_length=100)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    authorization: str = Header(default=""),
) -> list[ActivityLogItem]:
    # Accurate topic filter for the Logs screen (drill-through from the
    # dashboard): joins analytics.canonical_interactions.topic_code back to
    # app.activity_logs by activity_log_id, instead of guessing from
    # keywords in the question text.
    _require_admin(authorization)

    selected_topic = topic.strip()
    if selected_topic not in KNOWN_TOPIC_CODES:
        raise HTTPException(status_code=422, detail="Invalid analytics topic.")

    from backend.db.engine import get_session
    from backend.db.models import ActivityLog, CanonicalInteraction

    session = get_session()
    try:
        rows = session.execute(
            select(ActivityLog)
            .join(
                CanonicalInteraction,
                CanonicalInteraction.activity_log_id == ActivityLog.id,
            )
            .where(CanonicalInteraction.topic_code == selected_topic)
            .order_by(ActivityLog.created_at.desc())
            .limit(limit)
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
