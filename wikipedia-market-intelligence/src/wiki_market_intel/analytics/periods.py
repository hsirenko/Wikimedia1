"""Analysis periods (spec §9). All periods are whole calendar months and end at the
last complete month, so an incomplete month is never compared with a full one."""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from dateutil.relativedelta import relativedelta

from wiki_market_intel.models.metrics import MonthlyPoint, PeriodRef

DATA_START = date(2015, 7, 1)   # first month of per-article pageview data


@dataclass(frozen=True)
class Period:
    label: str
    start: date
    end: date

    @property
    def months(self) -> int:
        return (self.end.year - self.start.year) * 12 + self.end.month - self.start.month + 1

    @property
    def days(self) -> int:
        count, current = 0, self.start
        while current <= self.end:
            count += calendar.monthrange(current.year, current.month)[1]
            current += relativedelta(months=1)
        return count

    def values(self, series: list[MonthlyPoint]) -> list[int | None]:
        wanted = {f"{self.start + relativedelta(months=i):%Y-%m}" for i in range(self.months)}
        found = {p.month: p.views for p in series if p.month in wanted}
        return [found.get(m) for m in sorted(wanted)]

    def is_complete(self, series: list[MonthlyPoint]) -> bool:
        values = self.values(series)
        return bool(values) and all(v is not None for v in values)

    def ref(self, series: list[MonthlyPoint]) -> PeriodRef:
        return PeriodRef(label=self.label, start=f"{self.start:%Y-%m}", end=f"{self.end:%Y-%m}",
                         months=self.months, complete=self.is_complete(series))


def _span(label: str, end: date, months: int, offset: int = 0) -> Period:
    last = end - relativedelta(months=offset)
    return Period(label=label, start=last - relativedelta(months=months - 1), end=last)


def build_periods(end: date, requested_months: int) -> dict[str, Period]:
    """Every period the analysis needs, keyed by name."""
    return {
        "requested": _span("requested period", end, requested_months),
        "previous_equivalent": _span("previous equivalent period", end, requested_months, requested_months),
        "last_12m": _span("last 12 months", end, 12),
        "previous_12m": _span("previous 12 months", end, 12, 12),
        "twelve_months_3y_earlier": _span("12 months ending 3 years earlier", end, 12, 36),
        "last_36m": _span("last 36 months", end, 36),
        "previous_36m": _span("previous 36 months", end, 36, 36),
        "last_3m": _span("last 3 months", end, 3),
        "previous_3m": _span("previous 3 months", end, 3, 3),
        "preceding_3m": _span("3 months before that", end, 3, 6),
    }


def fetch_window(periods: dict[str, Period]) -> tuple[date, date]:
    """One request covers every period. Nothing before July 2015 exists."""
    start = max(DATA_START, min(p.start for p in periods.values()))
    return start, max(p.end for p in periods.values())


def parse_period(text: str) -> int:
    """'3y' -> 36, '18m' -> 18, '24' -> 24."""
    text = text.strip().lower()
    if text.endswith("y"):
        months = int(float(text[:-1]) * 12)
    elif text.endswith("m"):
        months = int(text[:-1])
    else:
        months = int(text)
    if months < 1:
        raise ValueError("period must be at least one month")
    return months
