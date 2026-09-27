"""Anomalies through the pipeline: result, report (en/uk), CLI, validation, comparison."""

import json

from wiki_market_intel import analyze, compare_languages
from wiki_market_intel.reporting import comparison as comparison_report
from wiki_market_intel.reporting import markdown
from wiki_market_intel.validate import validate_file
from tests.reporting.test_end_to_end import run_cli  # noqa: F401  (fixture)


def test_analysis_carries_anomalies_and_counts_them(services):
    r = analyze("meditation", "de", "3y", services=services)
    dates = [a.date for a in r.anomalies]
    assert "2025-11" in dates and all(a.cause == "unknown" for a in r.anomalies)
    assert r.quality.anomaly_count == len(r.anomalies)
    assert r.anomaly_analysis.seasonal_adjustment and r.anomaly_analysis.months_checked == 36
    assert "anomalies" not in {m.metric for m in r.quality.missing_metrics}


def test_report_section_9_lists_anomalies_without_causes(services):
    r = analyze("meditation", "de", "3y", services=services)
    text = markdown.render(r, None, "en")
    section = text.split("## 9. Anomalies")[1].split("## 10.")[0]
    assert "| Month | Actual | Expected (baseline) | Change vs baseline |" in section
    assert "Potential anomaly detected: 2025-11 pageviews were" in section and "Cause: unknown." in section
    for invented in ("because", "due to", "caused by", "news"):
        assert invented not in section.lower()


def test_ukrainian_anomaly_section(services):
    r = analyze("meditation", "de", "3y", services=services)
    section = markdown.render(r, None, "uk").split("## 9. Аномалії")[1].split("## 10.")[0]
    assert "Можлива аномалія: у 2025-11 перегляди були на" in section and "Причина: невідома." in section
    for english in ("Potential anomaly", "Month", "Expected", "Severity", "provisional", "Cause"):
        assert english not in section


def test_observation_states_the_spike_free_yoy_when_it_differs(services):
    from wiki_market_intel.analytics.summary import RULE6_GAP
    r = analyze("meditation", "de", "3y", services=services)
    text = " ".join(r.observations)
    excluded = r.anomaly_analysis.yoy_excluding_anomalies
    if excluded is not None and abs(excluded - r.growth.yoy) > RULE6_GAP:
        assert "With the flagged months replaced by their expected values" in text
    assert "potential anomal" in text


def test_validate_recomputes_anomalies(run_cli, settings):  # noqa: F811
    run_cli("analyze", "--topic", "meditation", "--language", "de")
    path = next(settings.reports_dir.rglob("analysis.json"))
    assert validate_file(path) == []
    data = json.loads(path.read_text("utf-8"))
    data["anomalies"] = []                          # someone deletes the flags
    path.write_text(json.dumps(data), "utf-8")
    assert any(p.startswith("anomalies:") for p in validate_file(path))


def test_cli_prints_flagged_months(run_cli, capsys):  # noqa: F811
    run_cli("analyze", "--topic", "meditation", "--language", "de")
    out = capsys.readouterr().out
    assert "ANOMALY 2025-11:" in out and "cause unknown" in out


def test_comparison_counts_anomalies_per_edition(services):
    c = compare_languages("meditation", ["de", "en", "fr"], "3y", services=services)
    rows = {r.language: r for r in c.rows}
    assert rows["de"].anomaly_count == len(c.analyses["de"].anomalies)
    text = comparison_report.render(c, None, None, "en")
    assert "| Anomalies |" in text and "2025-11" in text
