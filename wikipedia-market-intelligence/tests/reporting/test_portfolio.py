"""Portfolio mode (spec §36-§37): many topics x many editions, filters, report, chart, HTML, validation."""

import json
import statistics

import pytest

from wiki_market_intel import compare_languages, portfolio
from wiki_market_intel.analytics import portfolio as portfolio_kpis
from wiki_market_intel.reporting import generator
from wiki_market_intel.reporting import portfolio as portfolio_report
from wiki_market_intel.validate import validate_file
from tests.reporting.test_end_to_end import run_cli  # noqa: F401  (fixture)

LANGS = ["de", "en", "fr"]
TOPICS = [{"topic": "meditation", "category": "mindfulness"}, {"topic": "sleep", "category": "sleep"},
          {"topic": "Mercury", "category": "space"}]                     # Mercury is ambiguous


@pytest.fixture
def pf(services):
    return portfolio(TOPICS, LANGS, "3y", services=services)


def test_rows_keep_the_input_order_and_come_from_each_comparison(pf, services):
    assert [(r.topic, r.language) for r in pf.rows] == [(t["topic"], l) for t in TOPICS for l in LANGS]
    c = compare_languages("meditation", LANGS, "3y", services=services)
    for row, cmp_row in zip(pf.rows[:3], c.rows):
        assert row.annual_views == cmp_row.annual_views and row.topic_affinity == cmp_row.topic_affinity
        assert row.signals.market_size == c.analyses[row.language].signals.market_size


def test_an_ambiguous_topic_is_recorded_not_fatal(pf):
    mercury = [r for r in pf.rows if r.topic == "Mercury"]
    assert {r.status for r in mercury} == {"needs_review"} and all("candidates" in r.reason for r in mercury)
    assert all(r.excluded_by == "status:needs_review" for r in mercury)
    assert any("Mercury" in n and "review" in n for n in pf.notes)


def test_portfolio_split_is_the_median_of_measured_pairs(pf):
    measured = [r for r in pf.rows if r.status == "ok"]
    assert pf.demand_threshold == statistics.median(r.annual_views for r in measured)
    schlaf = next(r for r in pf.rows if r.topic == "sleep" and r.language == "de")
    assert schlaf.yoy_growth > 0 and schlaf.quadrant in ("investigate", "explore")


def test_filters_hide_rows_but_never_move_the_split(services, pf):
    filtered = portfolio(TOPICS, LANGS, "3y", min_views=100_000, min_growth=-0.5, categories=["sleep"],
                         services=services)
    assert filtered.demand_threshold == pf.demand_threshold
    reasons = {(r.topic, r.language): r.excluded_by for r in filtered.rows}
    assert reasons[("meditation", "de")] == "category"
    assert all(r.topic == "sleep" and r.annual_views >= 100_000 for r in filtered.visible)
    assert len(filtered.rows) == len(pf.rows)                           # hidden rows stay in the result


def test_one_language_uses_single_analyses(services):
    single = portfolio(["meditation", "sleep"], ["de"], "3y", services=services)
    assert set(single.analyses) == {"meditation", "sleep"} and not single.comparisons
    assert all(r.topic_affinity is None for r in single.rows)          # affinity needs other editions


def test_ready_answer_groups_by_quadrant_without_ranking(pf):
    lines = portfolio_kpis.ready_answer(pf.rows)
    assert lines[0] == portfolio_kpis.NO_VERDICT
    text = "\n".join(lines).lower()
    for word in ("best", "most promising", "winner", "top pick", "recommend"):
        assert word not in text


@pytest.mark.parametrize("lang, heading", [("en", "## 2. Portfolio Matrix"), ("uk", "## 2. Матриця портфеля")])
def test_report_in_both_languages(pf, lang, heading):
    text = portfolio_report.render(pf, "charts/portfolio.png", lang)
    assert heading in text and "![" in text
    section4 = text.split("## 4.")[1].split("## 5.")[0]
    assert "Mercury" in section4
    if lang == "uk":
        for english in ("Topic", "Reason", "ambiguous topic", "Filters applied", "No filters"):
            assert english not in text.split("## 6.")[0]


def test_writer_produces_json_markdown_chart_and_self_contained_html(pf, settings):
    files = generator.write_portfolio(pf, settings.reports_dir)
    assert files.json.name == "portfolio.json" and files.charts and files.charts[0].is_file()
    page = files.html.read_text("utf-8")
    assert page.startswith("<!doctype html>") and "data:image/png;base64," in page
    assert 'src="charts/' not in page                                   # the chart is embedded
    assert validate_file(files.json) == []


def test_validate_catches_an_edited_portfolio_row(pf, settings):
    files = generator.write_portfolio(pf, settings.reports_dir)
    data = json.loads(files.json.read_text("utf-8"))
    data["rows"][0]["quadrant"] = "investigate" if data["rows"][0]["quadrant"] != "investigate" else "watch"
    files.json.write_text(json.dumps(data), "utf-8")
    assert any("quadrant" in p for p in validate_file(files.json))


def test_cli_portfolio_from_yaml_with_category_filter(run_cli, settings, tmp_path, capsys):  # noqa: F811
    topics = tmp_path / "topics.yaml"
    topics.write_text("topics:\n  - {topic: meditation, category: mindfulness}\n  - {topic: sleep, category: sleep}\n",
                      "utf-8")
    assert run_cli("portfolio", "--topics", str(topics), "--languages", "de,en,fr", "--category", "sleep",
                   "--min-growth", "-100", "--name", "wellness") == 0
    out = capsys.readouterr().out
    assert "READY ANSWER" in out and portfolio_kpis.NO_VERDICT in out
    assert "HIDDEN (3 rows" in out and "meditation de: category" in out
    path = next(settings.reports_dir.rglob("portfolio.json"))
    assert path.parent.parent.name == "wellness" and validate_file(path) == []


def test_other_reports_also_write_html(run_cli, settings):  # noqa: F811
    run_cli("analyze", "--topic", "meditation", "--language", "de")
    page = next(settings.reports_dir.rglob("report.html")).read_text("utf-8")
    assert "<h2>1. Executive Decision Card</h2>" in page and "data:image/png;base64," in page


@pytest.mark.parametrize("question, phrase", [
    ("tell me the top 3 topic-market combos we should build for", "'top 3'"),
    ("Which markets should we enter first?", "'Which markets should'"),
    ("Яка категорія найкраща для нашого продукту?", "'найкраща'"),
    ("Compare meditation and yoga in German and French", None),
    ("Stop guessing: how is sleep trending?", None),
])
def test_ranking_requests_are_detected_in_the_users_words(question, phrase):
    assert portfolio_kpis.ranking_phrase(question) == phrase


def test_cli_opens_a_ranking_request_with_the_no_ranking_sentence(run_cli, capsys):  # noqa: F811
    run_cli("portfolio", "--topics", "meditation,sleep", "--languages", "de,en",
            "--question", "What are the top 3 combos we should build for?")
    out = capsys.readouterr().out
    assert "RANKING REQUEST: the user asked for 'top 3'" in out
    assert "You asked for 'top 3'. Wikipedia pageviews can't say which topic or market is best" in out
    assert out.index("RANKING REQUEST") < out.index("READY ANSWER")
