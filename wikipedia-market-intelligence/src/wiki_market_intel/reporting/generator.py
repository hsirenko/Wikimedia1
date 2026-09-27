"""Write an analysis to reports/{topic}/{language}/{date}/ (spec §25)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from wiki_market_intel.models.analysis import AnalysisResult, ComparisonResult
from wiki_market_intel.reporting import charts, comparison, markdown


@dataclass
class ReportFiles:
    directory: Path
    json: Path
    markdown: Path
    chart: Path | None


def slug(text: str) -> str:
    return re.sub(r"[^\w-]+", "-", text.strip().lower(), flags=re.UNICODE).strip("-") or "topic"


def write(result: AnalysisResult, reports_dir: Path, lang: str | None = None) -> ReportFiles:
    """`lang` defaults to the language recorded in the result (from the user's question)."""
    lang = lang or result.metadata.report_language
    day = result.metadata.generated_at[:10]
    directory = Path(reports_dir) / slug(result.metadata.topic) / result.metadata.language / day
    directory.mkdir(parents=True, exist_ok=True)

    json_path = directory / "analysis.json"
    json_path.write_text(result.model_dump_json(indent=2), "utf-8")

    chart = charts.trend_chart(result, directory / "charts" / "trend.png", lang)
    md_path = directory / "report.md"
    md_path.write_text(markdown.render(result, "charts/trend.png" if chart else None, lang), "utf-8")
    return ReportFiles(directory=directory, json=json_path, markdown=md_path, chart=chart)


@dataclass
class ComparisonFiles:
    directory: Path
    json: Path
    markdown: Path
    charts: list[Path]


def write_comparison(result: ComparisonResult, reports_dir: Path, lang: str | None = None) -> ComparisonFiles:
    """reports/{topic}/compare-{languages}/{date}/: comparison.json, report.md, charts/."""
    lang = lang or result.metadata.report_language
    day = result.metadata.generated_at[:10]
    directory = (Path(reports_dir) / slug(result.metadata.topic) /
                 ("compare-" + "-".join(result.metadata.languages)) / day)
    directory.mkdir(parents=True, exist_ok=True)
    json_path = directory / "comparison.json"
    json_path.write_text(result.model_dump_json(indent=2), "utf-8")
    matrix = charts.opportunity_matrix(result, directory / "charts" / "opportunity.png", lang)
    penetration = charts.penetration_chart(result, directory / "charts" / "penetration.png", lang)
    md_path = directory / "report.md"
    md_path.write_text(comparison.render(result, "charts/opportunity.png" if matrix else None,
                                         "charts/penetration.png" if penetration else None, lang), "utf-8")
    return ComparisonFiles(directory=directory, json=json_path, markdown=md_path,
                           charts=[p for p in (matrix, penetration) if p])
