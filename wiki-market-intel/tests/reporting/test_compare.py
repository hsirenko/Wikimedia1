"""Language comparison end to end on the fake Wikimedia (de real data, en scaled, fr growing,
es: article without data, uk: no article), plus report, CLI and validation."""

import json
import math
import re

import pytest

from wiki_market_intel import analyze, compare_languages
from wiki_market_intel.reporting import comparison as comparison_report
from wiki_market_intel.reporting import generator
from wiki_market_intel.validate import validate_file
from tests.conftest import EDITION_TOTALS
from tests.reporting.test_end_to_end import run_cli  # noqa: F401  (fixture)

LANGS = ["de", "en", "fr", "es", "uk"]


@pytest.fixture
def cmp(services):
    return compare_languages("meditation", LANGS, "3y", services=services)


def test_topic_is_resolved_once_and_every_edition_gets_a_row(cmp, fake):
    assert [r.language for r in cmp.rows] == LANGS
    status = {r.language: r.status for r in cmp.rows}
    assert status == {"de": "ok", "en": "ok", "fr": "ok", "es": "no_data", "uk": "no_article"}
    assert cmp.resolution.wikidata_id == "Q108458" and cmp.resolution.missing_languages == ["uk"]
    wikidata_calls = [r for r in fake.requests if "wikidata.org" in str(r.url)]
    assert len(wikidata_calls) == 1


def test_missing_editions_are_rows_without_numbers_never_zeros(cmp):
    for row in cmp.rows:
        if row.status != "ok":
            assert row.annual_views is None and row.topic_share is None and row.quadrant is None


def test_share_penetration_and_affinity_match_their_definitions(cmp):
    ok = {r.language: r for r in cmp.rows if r.status == "ok"}
    total = sum(r.annual_views for r in ok.values())
    for lang, row in ok.items():
        assert math.isclose(row.topic_share, row.annual_views / total)
        assert math.isclose(row.topic_penetration, row.annual_views / (EDITION_TOTALS[lang] * 12))
    pooled = total / sum(EDITION_TOTALS[l] * 12 for l in ok)
    assert math.isclose(ok["de"].topic_affinity, (ok["de"].annual_views / (EDITION_TOTALS["de"] * 12)) / pooled)


def test_growing_edition_lands_on_the_growth_side_of_the_matrix(cmp):
    fr = next(r for r in cmp.rows if r.language == "fr")
    assert fr.yoy_growth > 0 and fr.quadrant in ("investigate", "explore")
    de = next(r for r in cmp.rows if r.language == "de")
    assert de.yoy_growth < 0 and de.quadrant in ("established", "watch")


def test_per_language_results_carry_share_and_affinity(cmp):
    de = cmp.analyses["de"]
    assert de.localization.topic_share is not None and de.localization.topic_affinity is not None
    assert not [m for m in de.quality.missing_metrics if m.metric == "localization.topic_share"]


def test_single_analysis_now_reports_penetration(services):
    r = analyze("meditation", "de", "3y", services=services)
    assert math.isclose(r.localization.topic_penetration, r.demand.annual_views / (EDITION_TOTALS["de"] * 12))
    assert r.quality.project_denominator_available is True
    reasons = {m.metric: m.status for m in r.quality.missing_metrics}
    assert reasons["localization.topic_share"] == "unavailable"       # needs a comparison
    assert "localization.topic_penetration" not in reasons


def test_compare_needs_two_languages(services):
    with pytest.raises(ValueError):
        compare_languages("meditation", ["de"], services=services)


def test_comparison_files_and_validation(cmp, tmp_path):
    files = generator.write_comparison(cmp, tmp_path)
    assert files.json.name == "comparison.json" and files.json.parent.parent.name == "compare-de-en-fr-es-uk"
    assert {c.name for c in files.charts} == {"opportunity.png", "penetration.png"}
    assert validate_file(files.json) == []
    data = json.loads(files.json.read_text("utf-8"))
    data["rows"][0]["topic_affinity"] = 9.9
    files.json.write_text(json.dumps(data), "utf-8")
    assert any("topic_affinity" in p for p in validate_file(files.json))


def test_english_comparison_report(cmp):
    text = comparison_report.render(cmp, "charts/opportunity.png", "charts/penetration.png", "en")
    assert text.startswith("# Language Comparison Report: Meditation")
    assert [int(n) for n in re.findall(r"^## (\d+)\.", text, re.M)] == list(range(1, 11))
    assert "| uk.wikipedia | no article |" in text and "| es.wikipedia | no data |" in text
    assert "not an official Wikimedia metric" in text and "descriptive labels, not investment" in text
    for word in ("BUY", "SELL", "BEST", "WINNER"):
        assert word not in text


def test_ukrainian_comparison_report_has_no_english_leftovers(cmp):
    text = comparison_report.render(cmp, "charts/opportunity.png", "charts/penetration.png", "uk")
    assert text.startswith("# Звіт порівняння мов: Meditation")
    for english in ("Summary", "Language Opportunity", "Opportunity Matrix", "no article", "no data",
                    "investigate", "established", "Topic share", "What the data", "left out", "Notes"):
        assert english not in text, english


def test_cli_compare(run_cli, settings, capsys):  # noqa: F811
    assert run_cli("compare", "--topic", "meditation", "--languages", "de,en,fr,uk",
                   "--question", "Порівняй інтерес до медитації в різних мовах") == 0
    out = capsys.readouterr().out
    assert "de.wikipedia" in out and "no article" in out and "REPORT_LANGUAGE uk" in out
    assert next(settings.reports_dir.rglob("report.md")).read_text("utf-8").startswith("# Звіт порівняння мов")
    assert run_cli("validate") == 0


def test_cli_compare_rejects_a_single_language(run_cli, capsys):  # noqa: F811
    assert run_cli("compare", "--topic", "meditation", "--languages", "de") == 2
