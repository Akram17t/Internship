from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import Date

from backend.analytics.topics import KNOWN_TOPIC_CODES, classify_topic
from backend.api import routes_analytics
from backend.db.models import DailyTopicAggregate


def _aggregate(
    bucket_date: date,
    topic_code: str,
    *,
    interactions: int,
    users: int,
    negative: int = 0,
    errors: int = 0,
):
    return SimpleNamespace(
        bucket_date=bucket_date,
        topic_code=topic_code,
        interaction_count=interactions,
        unique_user_count=users,
        negative_feedback_count=negative,
        error_or_fallback_count=errors,
        refreshed_at=datetime(2026, 7, 31, 12, tzinfo=timezone.utc),
    )


def _disable_route_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(routes_analytics, "_require_admin", lambda _authorization: None)
    monkeypatch.setattr(routes_analytics, "_require_postgres_backend", lambda: None)


def test_daily_aggregate_bucket_uses_sql_date_type() -> None:
    assert isinstance(DailyTopicAggregate.__table__.c.bucket_date.type, Date)


def test_known_topics_cover_classifier_results() -> None:
    assert classify_topic("Bagaimana cara mengajukan cuti?").topic_code in KNOWN_TOPIC_CODES
    assert classify_topic("Pertanyaan tanpa keyword khusus").topic_code == "unclassified"
    assert "unclassified" in KNOWN_TOPIC_CODES


def test_summary_uses_exact_canonical_distinct_user_count(monkeypatch: pytest.MonkeyPatch) -> None:
    _disable_route_guards(monkeypatch)
    monkeypatch.setattr(
        routes_analytics,
        "_aggregate_rows",
        lambda: [
            _aggregate(date(2026, 7, 30), "leave_and_attendance", interactions=4, users=2),
            _aggregate(date(2026, 7, 31), "payroll_and_benefits", interactions=3, users=2),
        ],
    )
    # The same people can occur in multiple date/topic buckets. The exact
    # canonical distinct count is 3, whereas max(bucket)=2 and sum=4.
    monkeypatch.setattr(
        routes_analytics,
        "_canonical_unique_user_counts",
        lambda: (3, {"leave_and_attendance": 2, "payroll_and_benefits": 2}),
    )

    response = routes_analytics.get_analytics_summary("Bearer test")

    assert response.total_interactions == 7
    assert response.total_unique_users == 3
    assert response.earliest_date == "2026-07-30"
    assert response.latest_date == "2026-07-31"


def test_topics_do_not_double_count_users_across_days(monkeypatch: pytest.MonkeyPatch) -> None:
    _disable_route_guards(monkeypatch)
    monkeypatch.setattr(
        routes_analytics,
        "_aggregate_rows",
        lambda: [
            _aggregate(date(2026, 7, 30), "leave_and_attendance", interactions=2, users=2),
            _aggregate(date(2026, 7, 31), "leave_and_attendance", interactions=3, users=2),
        ],
    )
    monkeypatch.setattr(
        routes_analytics,
        "_canonical_unique_user_counts",
        lambda: (2, {"leave_and_attendance": 2}),
    )

    response = routes_analytics.get_analytics_topics("Bearer test")

    assert len(response.topics) == 1
    assert response.topics[0].interaction_count == 5
    assert response.topics[0].unique_user_count == 2


def test_logs_by_topic_rejects_unknown_topic_before_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_route_guards(monkeypatch)

    with pytest.raises(HTTPException) as error:
        routes_analytics.get_logs_by_topic(
            topic="not-a-real-topic", limit=25, authorization="Bearer test"
        )

    assert error.value.status_code == 422
    assert error.value.detail == "Invalid analytics topic."


def test_logs_by_topic_joins_logs_and_removes_feedback_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_route_guards(monkeypatch)
    activity = SimpleNamespace(
        id=17,
        event_type="chat",
        action="query",
        status="success",
        summary="Asked about leave",
        details_json={"question": "How do I take leave?", "feedback_token": "secret"},
        created_at=datetime(2026, 7, 31, 12, tzinfo=timezone.utc),
    )

    class _ScalarRows:
        def all(self):
            return [activity]

    class _Result:
        def scalars(self):
            return _ScalarRows()

    class _Session:
        statement = None
        closed = False

        def execute(self, statement):
            self.statement = statement
            return _Result()

        def close(self):
            self.closed = True

    session = _Session()
    monkeypatch.setattr("backend.db.engine.get_session", lambda: session)

    results = routes_analytics.get_logs_by_topic(
        topic="leave_and_attendance", limit=25, authorization="Bearer test"
    )

    assert session.closed is True
    assert "JOIN analytics.canonical_interactions" in str(session.statement)
    assert len(results) == 1
    assert results[0].id == 17
    assert results[0].details == {"question": "How do I take leave?"}
