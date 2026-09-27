"""Map API payloads to monthly KPI-ready series."""

from __future__ import annotations

from datetime import date
from typing import Any

from wiki_market_intel.models.metrics import MonthlyPoint, PageviewRecord
from wiki_market_intel.models.topic import ArticleRef


def month_range(start: date, end: date) -> list[date]:
    start_month = date(start.year, start.month, 1)
    end_month = date(end.year, end.month, 1)
    current = start_month
    months: list[date] = []
    while current <= end_month:
        months.append(current)
        current = date(current.year + (current.month // 12), (current.month % 12) + 1, 1)
    return months


def _field(item: Any, name: str, default=None):
    return getattr(item, name, item.get(name, default) if isinstance(item, dict) else default)


def _month(timestamp: str) -> date:
    return date(int(timestamp[:4]), int(timestamp[4:6]), 1)


def normalize(items: list[Any], article: ArticleRef) -> list[PageviewRecord]:
    out: list[PageviewRecord] = []
    for item in items:
        project = _field(item, "project", f"{article.language}.wikipedia")
        out.append(PageviewRecord(
            project=project,
            language=project.split(".")[0],
            article_title=_field(item, "article", article.title).replace("_", " "),
            article_id=str(article.page_id) if article.page_id is not None else None,
            date=_month(_field(item, "timestamp")),
            views=int(_field(item, "views", 0)),
            unique_devices=_field(item, "unique_devices"),
            access=_field(item, "access"),
            agent=_field(item, "agent"),
            granularity=_field(item, "granularity", "monthly"),
            source="wikimedia",
        ))
    return out


def monthly_series(records: list[PageviewRecord], start: date, end: date) -> list[MonthlyPoint]:
    by_month: dict[str, int] = {}
    for record in records:
        key = f"{record.date:%Y-%m}"
        by_month[key] = by_month.get(key, 0) + record.views
    return [MonthlyPoint(month=f"{m:%Y-%m}", views=by_month.get(f"{m:%Y-%m}")) for m in month_range(start, end)]


def edition_totals(items: list[Any], start: date, end: date) -> list[MonthlyPoint]:
    by_month: dict[str, int] = {}
    for item in items:
        key = f"{_month(_field(item, 'timestamp')):%Y-%m}"
        by_month[key] = by_month.get(key, 0) + int(_field(item, "views", 0))
    return [MonthlyPoint(month=f"{m:%Y-%m}", views=by_month.get(f"{m:%Y-%m}")) for m in month_range(start, end)]
