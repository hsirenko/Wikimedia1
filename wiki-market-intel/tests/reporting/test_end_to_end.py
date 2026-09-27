"""The milestone-1 slice end to end on real captured data (meditation, German), plus
reporting, the CLI and validation."""

import json
import re

import httpx
import pytest

from wiki_market_intel import analyze
from wiki_market_intel import cli
from wiki_market_intel.models.analysis import AnalysisResult
from wiki_market_intel.reporting import generator, markdown
from wiki_market_intel.service import build_services
from wiki_market_intel.validate import validate_file
from tests.conftest import TODAY, FakeWikimedia, load

SECTIONS = ["1. Recommendation", "2. KPI Breakdown", "3. Topic Definition", "4. Demand", "5. Growth",
            "6. Seasonality", "7. Language Opportunity", "8. Localization", "9. Topic Ecosystem", "10. Anomalies",
            "11. Data Quality", "12. Business Implications"]


def expected_from_fixture():
    """The same KPIs computed independently of the package, straight from the fixture."""
    views = {i["timestamp"][:6]: i["views"] for i in load("pageviews_meditation_de_2020-09_2026-08.json")["items"]}

    def block(a, b):
        return sum(v for k, v in views.items() if a <= k <= b)

    last, prev, old = block("202509", "202608"), block("202409", "202508"), block("202209", "202308")
    return {"annual": last, "yoy": last / prev - 1, "cagr": (last / old) ** (1 / 3) - 1,
            "m3": block("202606", "202608") / block("202603", "202605") - 1}


@pytest.fixture
def result(services):
    return analyze("meditation", "de", "3y", services=services)


def test_analysis_matches_an_independent_calculation(result):
    exp = expected_from_fixture()
    assert result.demand.annual_views == exp["annual"]
    assert result.growth.yoy == pytest.approx(exp["yoy"])
    assert result.growth.three_year_cagr == pytest.approx(exp["cagr"])
    assert result.growth.last_three_month_growth == pytest.approx(exp["m3"])
    assert (result.metadata.period_start, result.metadata.period_end) == ("2023-09", "2026-08")
    assert result.quality.quality_level == "HIGH" and result.quality.coverage == 1.0
    assert 3 <= len(result.summary) <= 5


def test_result_records_what_is_needed_to_reproduce_it(result):
    m = result.metadata
    assert m.generated_at and m.data_retrieved_at and m.software_version and m.api.endswith("/per-article")
    assert result.topic.wikidata_id == "Q108458" and result.topic.article_id == "28837"
    assert result.sources[0].raw_path and result.formulas


def test_explicit_dates_exclude_incomplete_months(services):
    r = analyze("meditation", "de", start="2023-09-01", end="2026-09-01", services=services)
    assert (r.metadata.period_start, r.metadata.period_end) == ("2023-09", "2026-08")
    future = analyze("meditation", "de", "12m", end="2027-01", services=services)
    assert future.metadata.period_end == "2026-08"          # capped at the last complete month


def test_json_output_is_machine_readable_and_valid(result, tmp_path):
    files = generator.write(result, tmp_path / "reports")
    assert files.json.parent.parts[-3:] == ("meditation", "de", files.json.parent.name)
    data = json.loads(files.json.read_text("utf-8"))
    for key in ("metadata", "topic", "demand", "growth", "seasonality", "localization", "anomalies",
                "ecosystem", "quality", "signals"):
        assert key in data
    assert data["demand"]["unique_devices"] is None             # null, not 0
    AnalysisResult.model_validate(data)
    assert files.chart and files.chart.exists() and files.chart.stat().st_size > 5000


def test_markdown_has_every_section_in_order(result):
    text = markdown.render(result, "charts/trend.png")
    positions = [text.index(f"## {s}") for s in SECTIONS]
    assert positions == sorted(positions)
    assert text.startswith("# Wikipedia Market Intelligence Report")
    assert "### What the data does NOT establish" in text


def test_missing_metrics_render_with_their_reason_never_as_zero(result):
    text = markdown.render(result, None)
    unique = re.search(r"\| Unique devices \| (.+) \|", text).group(1)
    assert unique.startswith("n/a (unsupported:") and "per project" in unique
    assert "Trend chart unavailable" in text
    for word in ("BUY", "SELL", "WINNER", "exploded"):
        assert word not in text


def test_incomplete_data_is_shown_as_such(settings):
    fixture = load("pageviews_meditation_de_2020-09_2026-08.json")
    fixture["items"] = [i for i in fixture["items"] if not i["timestamp"].startswith("202601")]
    services = build_services(settings, transport=httpx.MockTransport(FakeWikimedia(pageviews=fixture)),
                              today=TODAY, backoff=0)
    r = analyze("meditation", "de", "3y", services=services)
    assert r.demand.annual_views is None and r.growth.yoy is None
    # 35 of 36 months = 97.2%: under the 98% needed for HIGH, above the 90% needed for MEDIUM.
    assert r.quality.coverage == pytest.approx(35 / 36) and r.quality.quality_level == "MEDIUM"
    assert r.quality.missing_data == ["2026-01: no pageviews returned (zero views or no data)"]
    assert "n/a (insufficient data" in markdown.render(r, None)


# --- CLI -------------------------------------------------------------------

@pytest.fixture
def run_cli(settings, fake, monkeypatch):
    monkeypatch.setattr(cli, "build_services", lambda s, **kw: build_services(
        s, transport=httpx.MockTransport(fake), today=TODAY, backoff=0, **kw))

    def run(*argv):
        return cli.main(list(argv), settings=settings)
    return run


def test_cli_analyze_writes_json_markdown_and_chart(run_cli, settings, capsys):
    assert run_cli("analyze", "--topic", "meditation", "--language", "de", "--period", "3y") == 0
    out = capsys.readouterr().out
    assert out.index("RECOMMENDATION") < out.index("KPI BREAKDOWN") < out.index("OBSERVATIONS")
    assert "Growth (year over year): -17.2%" in out and "Data quality: HIGH" in out
    assert "PDF_OFFER folder:" in out and out.index("PDF_OFFER") > out.index("Wrote")
    assert "Would you like a one-page PDF summary of this report?" in out.strip().splitlines()[-1]   # the reply's last line
    written = list(settings.reports_dir.rglob("*"))
    assert {p.name for p in written} >= {"analysis.json", "report.md", "report.html", "trend.png"}


def test_cli_accepts_yaml_input(run_cli, tmp_path):
    spec = tmp_path / "input.yaml"
    spec.write_text("topic: meditation\nlanguage: de\nperiod:\n  start: 2023-09-01\n  end: 2026-09-01\n")
    assert run_cli("analyze", "--input", str(spec)) == 0


@pytest.mark.parametrize("topic, language, code, text", [
    ("Mercury", "en", 3, "Topic resolution requires review."),
    ("Qwxzzyq", "de", 4, "Not found"),
    ("Mindfulness", "de", 4, "has no article"),
])
def test_cli_exit_codes_distinguish_failures(run_cli, capsys, topic, language, code, text):
    assert run_cli("analyze", "--topic", topic, "--language", language) == code
    assert text in capsys.readouterr().out


def test_cli_reports_api_errors(settings, monkeypatch, capsys):
    broken = FakeWikimedia(fail={"per-article": [httpx.Response(500)] * 4})
    monkeypatch.setattr(cli, "build_services", lambda s, **kw: build_services(
        s, transport=httpx.MockTransport(broken), today=TODAY, backoff=0, **kw))
    assert cli.main(["analyze", "--topic", "meditation", "--language", "de"], settings=settings) == 5
    assert "API error" in capsys.readouterr().err


def test_validate_passes_and_catches_a_tampered_report(run_cli, settings, capsys):
    run_cli("analyze", "--topic", "meditation", "--language", "de")
    path = next(settings.reports_dir.rglob("analysis.json"))
    assert validate_file(path) == []
    data = json.loads(path.read_text("utf-8"))
    data["growth"]["yoy"] = 0.5
    path.write_text(json.dumps(data), "utf-8")
    assert run_cli("validate") == 1
    assert "growth.yoy: stored 0.5" in capsys.readouterr().out


def test_cache_clear_keeps_raw_responses(run_cli, settings, capsys):
    run_cli("analyze", "--topic", "meditation", "--language", "de")
    assert run_cli("cache", "clear") == 0
    assert "Cleared" in capsys.readouterr().out
    assert list(settings.raw_dir.rglob("*.json"))


def test_validate_accepts_reports_from_older_versions(run_cli, settings):
    """A field added later (here seasonality.observations_per_month) must not fail old reports."""
    run_cli("analyze", "--topic", "meditation", "--language", "de")
    path = next(settings.reports_dir.rglob("analysis.json"))
    data = json.loads(path.read_text("utf-8"))
    del data["seasonality"]["observations_per_month"]
    path.write_text(json.dumps(data), "utf-8")
    assert validate_file(path) == []
