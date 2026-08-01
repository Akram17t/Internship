"""Backfill answer provenance onto conversation messages stored before it was kept.

app.conversation_messages only started recording answer_source / feedback_id /
feedback_token / duration_ms recently. Everything written before that has the
columns but they are NULL, so reopening those conversations still shows an
assistant turn with no badge and no feedback row.

The same facts were always written to the activity log, so this recovers them:
each chat activity log holds the conversation_id, the exact answer text, the
answer_source, the feedback token and the response time. Matching on
(conversation_id, exact answer text) is precise -- no time-window guessing --
and a message is only touched when exactly one log matches it, so an ambiguous
pair (the same answer twice in one conversation) is skipped rather than
guessed at.

Run:  python -m backend.scripts.backfill_message_metadata [--commit]
Without --commit it only reports what it would change.
"""

from __future__ import annotations

import argparse
import json
from typing import Any


def _details(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commit",
        action="store_true",
        help="actually write the values (default is a dry run)",
    )
    args = parser.parse_args()

    from sqlalchemy import select, update

    from backend.db.engine import get_session
    from backend.db.models import ActivityLog, ConversationMessage

    session = get_session()
    try:
        logs = session.execute(
            select(ActivityLog.id, ActivityLog.details_json).where(
                ActivityLog.event_type == "chat"
            )
        ).all()

        # (conversation_id, answer text) -> list of candidate logs. A key with
        # more than one candidate is ambiguous and gets skipped.
        by_answer: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for log_id, raw in logs:
            details = _details(raw)
            conversation_id = str(details.get("conversation_id") or "").strip()
            answer = str(details.get("answer") or "").strip()
            if not conversation_id or not answer:
                continue
            response_time = details.get("response_time_seconds")
            by_answer.setdefault((conversation_id, answer), []).append(
                {
                    "feedback_id": log_id,
                    "feedback_token": str(details.get("feedback_token") or "") or None,
                    "answer_source": str(details.get("answer_source") or "") or None,
                    "duration_ms": (
                        int(float(response_time) * 1000) if response_time is not None else None
                    ),
                }
            )

        rows = session.execute(
            select(ConversationMessage).where(
                ConversationMessage.role == "assistant",
                ConversationMessage.answer_source.is_(None),
            )
        ).scalars().all()

        matched = 0
        ambiguous = 0
        unmatched = 0
        for row in rows:
            key = (str(row.conversation_id or ""), str(row.content or "").strip())
            candidates = by_answer.get(key) or []
            if len(candidates) != 1:
                if candidates:
                    ambiguous += 1
                else:
                    unmatched += 1
                continue
            found = candidates[0]
            matched += 1
            if args.commit:
                session.execute(
                    update(ConversationMessage)
                    .where(ConversationMessage.id == row.id)
                    .values(**found)
                )

        if args.commit:
            session.commit()

        print(f"assistant turns missing provenance : {len(rows)}")
        print(f"  matched to exactly one log       : {matched}")
        print(f"  ambiguous (same answer repeated) : {ambiguous}")
        print(f"  no matching log (log purged)     : {unmatched}")
        print("committed" if args.commit else "dry run -- re-run with --commit to write")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
