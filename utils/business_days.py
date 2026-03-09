"""
Business-day utilities for SLA calculations.

Rules:
  - Timezone: America/Los_Angeles
  - Business days are Mon–Fri (no holiday calendar; extend later if needed)
  - `draftDueAt`    = submittedAt + 2 business days
  - `decisionDueAt` = submittedAt + 4 business days
"""
from __future__ import annotations

from datetime import datetime, timedelta

import zoneinfo

LA_TZ = zoneinfo.ZoneInfo("America/Los_Angeles")


def _to_la(dt: datetime) -> datetime:
    """Ensure a datetime is expressed in the LA timezone."""
    if dt.tzinfo is None:
        # Treat naive datetimes as UTC, then convert
        dt = dt.replace(tzinfo=zoneinfo.ZoneInfo("UTC"))
    return dt.astimezone(LA_TZ)


def add_business_days(start: datetime, days: int) -> datetime:
    """
    Return `start` + `days` business days, expressed in LA timezone.

    Args:
        start: The reference datetime (any timezone or naive/UTC).
        days:  Number of business days to add (must be >= 0).

    Returns:
        A timezone-aware datetime in America/Los_Angeles at the same
        wall-clock time as `start`, advanced by `days` business days.
    """
    if days < 0:
        raise ValueError("days must be >= 0")

    current = _to_la(start)
    added = 0

    while added < days:
        current += timedelta(days=1)
        # weekday(): Monday=0, Sunday=6
        if current.weekday() < 5:  # Mon–Fri
            added += 1

    return current


def business_days_between(start: datetime, end: datetime) -> int:
    """
    Count the number of business days between two datetimes (exclusive of start,
    inclusive of end), similar to how "days remaining" is typically reported.

    Returns a negative number if `end` is before `start`.
    """
    start_la = _to_la(start)
    end_la = _to_la(end)

    if end_la <= start_la:
        # Count backwards
        return -business_days_between(end, start)

    count = 0
    cursor = start_la
    while cursor < end_la:
        cursor += timedelta(days=1)
        if cursor.weekday() < 5:
            count += 1

    return count


def is_past_due(deadline: datetime, reference: datetime | None = None) -> bool:
    """Return True if `deadline` is before `reference` (default: now in LA tz)."""
    ref = _to_la(reference) if reference else datetime.now(LA_TZ)
    return _to_la(deadline) < ref


def now_la() -> datetime:
    """Current datetime in America/Los_Angeles."""
    return datetime.now(LA_TZ)


def format_iso(dt: datetime) -> str:
    """Return an ISO-8601 string suitable for storing in Airtable Date/Time fields."""
    return _to_la(dt).isoformat()
