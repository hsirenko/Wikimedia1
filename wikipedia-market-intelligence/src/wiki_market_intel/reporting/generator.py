"""Write an analysis to reports/{topic}/{language}/{date}/ (spec §25)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from wiki_market_intel.models.analysis import AnalysisResult
from wiki_market_intel.reporting import charts, markdown


@dataclass
class ReportFiles:
    directory: Path
    json: Path
    markdown: Path
    chart: Path | None


def slug(text: str) -> str:
    return re.sub(r"[^\w-]+", "-", text.strip().lower(), flags=re.UNICODE).strip("-") or "topic"


def write(result: AnalysisResult, reports_dir: Path) -> ReportFiles:
    day = result.metadata.generated_at[:10]
    directory = Path(reports_dir) / slug(result.metadata.topic) / result.metadata.language / day
    directory.mkdir(parents=True, exist_ok=True)

    json_path = directory / "analysis.json"
    json_path.write_text(result.model_dump_json(indent=2), "utf-8")

    chart = charts.trend_chart(result, directory / "charts" / "trend.png")
    md_path = directory / "report.md"
    md_path.write_text(markdown.render(result, "charts/trend.png" if chart else None), "utf-8")
    return ReportFiles(directory=directory, json=json_path, markdown=md_path, chart=chart)
