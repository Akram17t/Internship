from __future__ import annotations

"""Canonical interaction write path (simplified analytics).

Writes one analytics.canonical_interactions row per chat activity_log entry.
Called from backend/db/repository.py's insert_activity_log (postgres
backend only) so no FastAPI route needs to change to get analytics data.

This is a reduced-scope version of the design's CanonicalInteractionService:
no historical backfill matching, no lineage table, no versioned taxonomy -
just a direct 1:1 write with a rule-based topic tag.
"""

import hashlib
import hmac
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from backend.analytics.topics import classify_topic
from backend.db.models import CanonicalInteraction
from backend.settings import get_env


def pseudonymize_user(identifier: str) -> str:
    # Stable pseudonym: HMAC-SHA256(secret, identifier). Different identifiers
    # never reveal the source value; same identifier + same secret always
    # produces the same pseudonym.
    secret = get_env("ANALYTICS_PSEUDONYM_SECRET", "change-me-dev-only-pseudonym-secret")
    digest = hmac.new(secret.encode("utf-8"), identifier.strip().lower().encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()[:32]


def record_canonical_interaction(
    session: Session,
    *,
    activity_log_id: int,
    status: str,
    details: dict[str, Any],
    created_at: datetime,
) -> None:
    if str(details.get("action", "")) and details.get("event_type") not in (None, "chat"):
        return

    question = str(details.get("question") or "").strip()
    if not question:
        # Non-chat activity logs (e.g. document events) are out of scope for
        # this simplified usage dashboard.
        return

    user_email = str(details.get("user_email") or "").strip()
    conversation_id = str(details.get("conversation_id") or "").strip() or None
    classification = classify_topic(question)

    response_time_seconds = details.get("response_time_seconds")
    response_time_ms = (
        int(float(response_time_seconds) * 1000) if response_time_seconds is not None else None
    )

    feedback = details.get("feedback")
    feedback_rating = None
    if isinstance(feedback, dict):
        feedback_rating = str(feedback.get("rating") or "").strip() or None

    row = CanonicalInteraction(
        activity_log_id=activity_log_id,
        conversation_id=conversation_id,
        pseudonymous_user_id=pseudonymize_user(user_email) if user_email else None,
        occurred_at=created_at,
        response_status=status,
        answer_source=str(details.get("answer_source") or "").strip() or None,
        response_time_ms=response_time_ms,
        citation_count=details.get("citation_count"),
        form_count=details.get("form_count"),
        feedback_rating=feedback_rating,
        topic_code=classification.topic_code,
        topic_confidence=classification.confidence,
        created_at=created_at,
    )
    session.add(row)


def update_canonical_interaction_feedback(
    session: Session, *, activity_log_id: int, rating: str
) -> None:
    from sqlalchemy import update

    session.execute(
        update(CanonicalInteraction)
        .where(CanonicalInteraction.activity_log_id == activity_log_id)
        .values(feedback_rating=rating)
    )
