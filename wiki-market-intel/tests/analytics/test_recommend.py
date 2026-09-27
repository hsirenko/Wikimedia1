"""High-level recommendation: evidence-based next steps from written rules, never a go/no-go."""

import json

import pytest

from wiki_market_intel import analyze, analyze_cluster, compare_languages, portfolio
from wiki_market_intel.analytics import recommend
from wiki_market_intel.i18n import Translator
from wiki_market_intel.reporting import markdown
from wiki_market_intel.validate import validate_file
from tests.reporting.test_end_to_end import run_cli  # noqa: F401  (fixture)

EN = Translator("en")


@pytest.mark.parametrize("views, rel, median, tier", [
    (11_999, 0.20, None, "deprioritise"),              # too small, however it grows
    (50_000, -0.25, None, "deprioritise"),             # 25% or more behind the edition
    (50_000, -0.10, None, "validate_first"),           # within 10% of the edition
    (50_000, -0.11, None, "monitor"),
    (50_000, 0.05, 40_000, "validate_first"),
    (30_000, 0.05, 40_000, "monitor"),                 # below the set's median
    (50_000, None, None, "monitor"),                   # no YoY yet
])
def test_tier_rules(views, rel, median, tier):
    assert recommend.tier(views, rel, median)[0] == tier


def test_relative_growth_is_share_adjusted_when_the_edition_is_known():
    assert recommend.relative(-0.161, -0.073) == pytest.approx(0.839 / 0.927 - 1)
    assert recommend.relative(-0.161, None) == -0.161


def test_single_analysis_recommendation(services):
    r = analyze("meditation", "de", "3y", services=services)
    rec = r.recommendation
    assert rec.scope == "analysis" and len(rec.items) == 1
    assert rec.text == recommend.sentences(rec, EN) and rec.text[-1].startswith("Basis: Wikipedia reader attention")
    assert rec.peak_month == "January"                                 # the fixture peaks in January


def test_comparison_orders_validation_by_the_rules(services):
    c = compare_languages("meditation", ["de", "en", "fr"], "3y", services=services)
    tiers = {i.label: i.tier for i in c.recommendation.items}
    assert set(tiers) == {"de.wikipedia", "en.wikipedia", "fr.wikipedia"}
    fr = next(i for i in c.recommendation.items if i.label == "fr.wikipedia")
    assert fr.relative is not None and fr.relative > 0 and fr.tier in ("validate_first", "monitor")
    order = {"validate_first": 0, "monitor": 1, "deprioritise": 2}
    assert [order[i.tier] for i in c.recommendation.items] == sorted(order[i.tier] for i in c.recommendation.items)


def test_cluster_adds_related_topics_without_text_similarity_noise(services):
    r = analyze_cluster("meditation", "de", "3y", services=services)
    rec = r.recommendation
    assert "Zazen" in rec.related_explore                            # growing narrower concept
    assert "Buddhismus" in rec.related_context
    assert not any(n.endswith(" *") for n in rec.related_declining)  # similarity noise stays out


def test_portfolio_recommendation_uses_visible_rows(services):
    p = portfolio(["meditation", "sleep"], ["de", "en", "fr"], "3y", min_views=100_000, services=services)
    labels = {i.label for i in p.recommendation.items}
    assert labels == {f"{r.canonical_topic or r.topic} · {r.project}" for r in p.visible}


@pytest.mark.parametrize("lang", ["en", "uk"])
def test_sentences_never_give_a_verdict(services, lang):
    c = compare_languages("meditation", ["de", "en", "fr"], "3y", services=services)
    text = " ".join(recommend.sentences(c.recommendation, Translator(lang))).lower()
    for word in ("go/no-go call", "invest in", "buy", "winner", "best market"):
        assert word not in text
    assert ("not a go/no-go" in text) if lang == "en" else ("не рішення «так/ні»" in text)


def test_report_opens_with_the_recommendation_then_the_kpi_breakdown(services):
    r = analyze("meditation", "de", "3y", services=services)
    text = markdown.render(r, None, "en")
    assert (text.index("## 1. Recommendation") < text.index("## 2. Graph")
            < text.index("## 3. Key Observations") < text.index("## 4. KPI Breakdown"))
    assert "_Rule: validate first" in text


def test_validate_catches_an_edited_recommendation(run_cli, settings):  # noqa: F811
    run_cli("compare", "--topic", "meditation", "--languages", "de,en,fr")
    path = next(settings.reports_dir.rglob("comparison.json"))
    assert validate_file(path) == []
    data = json.loads(path.read_text("utf-8"))
    data["recommendation"]["items"][-1]["tier"] = "validate_first" if data["recommendation"]["items"][-1]["tier"] != "validate_first" else "deprioritise"
    path.write_text(json.dumps(data), "utf-8")
    assert any(p.startswith("recommendation:") for p in validate_file(path))
