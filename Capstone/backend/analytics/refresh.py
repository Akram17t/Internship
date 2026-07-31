from __future__ import annotations

"""Simplified daily aggregate refresh for the analytics dashboard.

Reduced-scope replacement for the design's queue-based AnalyticsRefreshWorker:
a synchronous recompute-from-detail function, callable on demand (e.g. from
an admin endpoint). No queue table, no watermark, no incremental bucket
math - it recomputes every bucket fully from
analytics.canonical_interactions on each call, which is correct (if less
efficient at very large scale) for MVP data volumes.
"""

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from backend.db.engine import get_session
from backend.db.models import CanonicalInteraction, DailyTopicAggregate


def refresh_daily_aggregates(session: Session | None = None) -> int:
    # Returns the number of (date, topic) buckets written.
    owns_session = session is None
    session = session or get_session()
    try:
        rows = session.execute(
            select(
                CanonicalInteraction.occurred_at,
                CanonicalInteraction.topic_code,
                CanonicalInteraction.pseudonymous_user_id,
                CanonicalInteraction.feedback_rating,
                CanonicalInteraction.response_status,
                CanonicalInteraction.answer_source,
            )
        ).all()

        buckets: dict[tuple, dict[str, object]] = {}
        for occurred_at, topic_code, pseudonymous_user_id, feedback_rating, response_status, answer_source in rows:
            bucket_date = occurred_at.date()
            key = (bucket_date, topic_code)
            bucket = buckets.setdefault(
                key,
                {
                    "interaction_count": 0,
                    "unique_users": set(),
                    "negative_feedback_count": 0,
                    "error_or_fallback_count": 0,
                },
            )
            bucket["interaction_count"] += 1
            if pseudonymous_user_id:
                bucket["unique_users"].add(pseudonymous_user_id)
            if feedback_rating == "thumbs_down":
                bucket["negative_feedback_count"] += 1
            if response_status == "error" or answer_source in {
                "fallback",
                "out_of_scope",
                "blocked",
            }:
                bucket["error_or_fallback_count"] += 1

        now = datetime.now(timezone.utc)
        session.execute(delete(DailyTopicAggregate))
        written = 0
        for (bucket_date, topic_code), bucket in buckets.items():
            stmt = pg_insert(DailyTopicAggregate).values(
                bucket_date=bucket_date,
                topic_code=topic_code,
                interaction_count=bucket["interaction_count"],
                unique_user_count=len(bucket["unique_users"]),
                negative_feedback_count=bucket["negative_feedback_count"],
                error_or_fallback_count=bucket["error_or_fallback_count"],
                refreshed_at=now,
            )
            session.execute(stmt)
            written += 1

        if owns_session:
            session.commit()
        return written
    finally:
        if owns_session:
            session.close()
