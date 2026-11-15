"""What kind of day a Vexcel photo was taken on: workday / saturday / sunday / holiday.

Holidays are the US federal holidays offices close for (New Year, MLK, Presidents, Memorial,
Juneteenth, July 4, Labor, Thanksgiving + the Friday after, Christmas Eve and Day), with
weekend observance. Checked on the real counts: Sundays (0.69x a lot's usual cars) and Jan 1
(0.50x) are clearly emptier; Dec 31 (1.00x) and most Saturdays (0.96x) are not, so they count as
normal days.
"""
from __future__ import annotations

from datetime import date, timedelta
from functools import lru_cache


def _nth_weekday(y: int, m: int, weekday: int, n: int) -> date:
    d = date(y, m, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_weekday(y: int, m: int, weekday: int) -> date:
    d = date(y, m + 1, 1) - timedelta(days=1)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


@lru_cache(maxsize=None)
def holidays(y: int) -> frozenset[date]:
    fixed = [date(y, 1, 1), date(y, 7, 4), date(y, 12, 25)] + ([date(y, 6, 19)] if y >= 2021 else [])
    days = set(fixed) | {date(y, 12, 24)}
    for d in fixed:  # observed: Saturday -> Friday, Sunday -> Monday
        if d.weekday() == 5:
            days.add(d - timedelta(days=1))
        elif d.weekday() == 6:
            days.add(d + timedelta(days=1))
    thanks = _nth_weekday(y, 11, 3, 4)
    days |= {_nth_weekday(y, 1, 0, 3), _nth_weekday(y, 2, 0, 3), _last_weekday(y, 5, 0),
             _nth_weekday(y, 9, 0, 1), thanks, thanks + timedelta(days=1)}
    return frozenset(days)


def day_kind(d: date) -> str:
    if d in holidays(d.year):
        return "holiday"
    return {5: "saturday", 6: "sunday"}.get(d.weekday(), "workday")


def classify(dates: list[date]) -> str:
    """One label for a flight's photos of a building; 'mixed' if they span different kinds of day."""
    kinds = {day_kind(d) for d in dates}
    if not kinds:
        return "unknown"
    return kinds.pop() if len(kinds) == 1 else "mixed"


def classify_str(dates: str) -> str:
    """'2025-01-31;2025-02-16' -> day type."""
    if not isinstance(dates, str) or not dates:
        return "unknown"
    return classify([date.fromisoformat(s) for s in dates.split(";")])
