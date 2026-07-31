from __future__ import annotations

from datetime import datetime, timezone

# Import the backend facade first so its PostgreSQL repository delegation is
# initialized in the same order as the running application.
from backend import cache_db as _cache_db  # noqa: F401
from backend.db.repository import _datetime_bound


def test_datetime_bound_converts_aware_iso_string() -> None:
    result = _datetime_bound("2026-07-02T17:00:00+00:00")

    assert result == datetime(2026, 7, 2, 17, 0, tzinfo=timezone.utc)
    assert result.tzinfo is not None


def test_datetime_bound_assumes_utc_for_naive_iso_string() -> None:
    result = _datetime_bound("2026-07-02T17:00:00")

    assert result == datetime(2026, 7, 2, 17, 0, tzinfo=timezone.utc)


def test_datetime_bound_preserves_datetime_instance() -> None:
    value = datetime(2026, 8, 1, 16, 59, 59, tzinfo=timezone.utc)

    assert _datetime_bound(value) is value
    assert _datetime_bound(None) is None
    assert _datetime_bound("") is None
