"""Topic ecosystem (spec §19-§20) on a known fake cluster around Meditation (de).

Fake cluster: Buddhismus (facet_of, 4x larger), Entspannungsverfahren (broader, smaller),
Transzendentale Meditation (narrower, also returned by text similarity), Zazen (narrower,
growing), Q_NOART (narrower, no German article), Yoga (similar text, bigger, roughly stable),
Rosenkranz (similar text, 10 views a month). The fake edition is flat, so share-adjusted YoY = YoY.
"""

import json
import re

import pytest

from wiki_market_intel import analyze, analyze_cluster
from wiki_market_intel.reporting import markdown
from wiki_market_intel.validate import validate_file
from tests.reporting.test_end_to_end import run_cli  # noqa: F401  (fixture)


@pytest.fixture
def cluster(services):
    return analyze_cluster("meditation", "de", "3y", services=services)


def related(result):
    return {t.title: t for t in result.ecosystem.related_topics}


def test_relations_are_typed_deduplicated_and_sourced(cluster):
    r = related(cluster)
    assert (r["Buddhismus"].relationship, r["Buddhismus"].source) == ("facet_of", "wikidata:P1269 facet of")
    assert r["Entspannungsverfahren"].relationship == "broader"
    assert r["Zazen"].relationship == "narrower" and r["Zazen"].wikidata_id == "Q_ZAZEN"
    # Found by both reverse subclass-of and text similarity: kept once, as the typed relation.
    assert r["Transzendentale Meditation"].relationship == "narrower"
    assert r["Yoga"].relationship == "similar_content"
    assert "Meditation" not in r                                       # the topic itself is excluded
    assert cluster.ecosystem.skipped_without_article == {"narrower": 1}
    assert cluster.ecosystem.computed and cluster.ecosystem.has_wikidata


def test_signals_follow_the_documented_rules(cluster):
    r = related(cluster)
    assert r["Buddhismus"].signal == "larger_category"                 # broader (facet of) and larger
    assert r["Entspannungsverfahren"].signal == "declining_category"   # broader but smaller: not "larger"
    assert r["Zazen"].signal == "emerging_category"
    assert r["Yoga"].signal == "adjacent_opportunity"                  # bigger, not declining
    assert r["Rosenkranz"].signal == "too_small"


def test_relative_size_and_share_adjusted_growth(cluster):
    r = related(cluster)
    focal = cluster.demand.annual_views
    assert r["Buddhismus"].relative_size == pytest.approx(r["Buddhismus"].annual_views / focal)
    assert cluster.ecosystem.edition_yoy == pytest.approx(0.0)
    assert r["Zazen"].share_adjusted_yoy == pytest.approx(r["Zazen"].yoy_growth)


def test_concentration_uses_typed_relations_only(cluster):
    c = cluster.ecosystem.concentration
    typed = [t.annual_views for t in cluster.ecosystem.related_topics if t.relationship != "similar_content"]
    views = sorted([cluster.demand.annual_views, *typed], reverse=True)
    assert c.articles == len(views) == 5
    assert c.top_1 == pytest.approx(views[0] / sum(views)) and c.top_5 == pytest.approx(1.0)
    assert c.top_10 is None and c.top_20 is None                       # fewer articles than k
    assert c.largest == "Buddhismus"                                   # named: often not the topic itself


def test_cap_is_applied_and_recorded(services):
    r = analyze_cluster("meditation", "de", "3y", max_related=3, services=services)
    assert len(r.ecosystem.related_topics) == 3 and r.ecosystem.capped_from == 6
    assert {t.relationship for t in r.ecosystem.related_topics} <= {"broader", "facet_of", "narrower"}


def test_analyze_does_not_compute_the_ecosystem(services):
    r = analyze("meditation", "de", "3y", services=services)
    assert not r.ecosystem.computed and r.ecosystem.related_topics == []
    gap = next(m for m in r.quality.missing_metrics if m.metric == "ecosystem.related_topics")
    assert gap.status == "unavailable" and "cluster" in gap.reason


def test_report_section_9_en_and_uk(cluster):
    en = markdown.render(cluster, None, "en", "charts/ecosystem.png").split("## 9. Topic Ecosystem")[1].split("## 10.")[0]
    assert "| **Meditation** |" in en and "| Buddhismus | facet of |" in en and "larger category" in en
    assert "### Interest concentration" in en and "n/a (fewer than 10 articles)" in en
    assert "adjacent interest signal" in en and "no article in this edition" in en
    for word in ("BUY", "best", "winner", "product-market"):
        assert word not in en
    uk = markdown.render(cluster, None, "uk", "charts/ecosystem.png").split("## 9. Екосистема теми")[1].split("## 10.")[0]
    assert "ширша категорія" in uk and "Концентрація інтересу" in uk
    for english in ("larger category", "facet of", "similar text", "Interest concentration", "Topic", "skipped"):
        assert english not in uk, english


def test_cli_cluster_writes_chart_and_validates(run_cli, settings, capsys):  # noqa: F811
    assert run_cli("cluster", "--topic", "meditation", "--language", "de") == 0
    out = capsys.readouterr().out
    assert "RELATED: 6 topics measured" in out and "larger_category" in out
    assert "than its edition by" in out and "*Yoga" in out           # unambiguous wording, similarity marked
    path = next(settings.reports_dir.rglob("analysis.json"))
    assert path.parent.parent.name == "cluster-de"
    assert (path.parent / "charts" / "ecosystem.png").exists()
    assert validate_file(path) == []
    data = json.loads(path.read_text("utf-8"))
    data["ecosystem"]["related_topics"][0]["signal"] = "emerging_category"
    path.write_text(json.dumps(data), "utf-8")
    assert any("signal" in p for p in validate_file(path))


def test_topic_without_wikidata_uses_only_text_similarity(services):
    r = analyze_cluster("Obscurium", "en", "3y", services=services)
    assert r.ecosystem.has_wikidata is False
    assert all(t.relationship == "similar_content" for t in r.ecosystem.related_topics)


def test_quote_ready_sentences_carry_the_caveats(cluster):
    from wiki_market_intel.analytics.ecosystem import quote_ready
    lines = quote_ready(cluster.ecosystem.related_topics)
    text = "\n".join(lines)
    assert "Yoga (found by text similarity only, not a stated relationship)" in text
    assert "than its edition" in text and "Buddhismus (facet of concept)" in text
    zazen = next(l for l in lines if l.strip().startswith("- Zazen"))
    assert "better than its edition" in zazen                          # the growing one
    for word in ("best", "most promising", "primary", "top opportunity"):
        assert word not in text.lower()


def test_headline_counts_topics_that_outpaced_the_edition(cluster):
    from wiki_market_intel.analytics.ecosystem import headline, quote_ready
    eco = cluster.ecosystem
    text = headline(eco.related_topics, eco.edition_yoy, "de.wikipedia")
    better = [t.title for t in eco.related_topics
              if t.signal not in (None, "too_small") and (t.share_adjusted_yoy or 0) > 0]
    assert f"{len(better)} grew faster than de.wikipedia" in text and "does not rank" in text
    assert quote_ready(eco.related_topics, eco.edition_yoy, "de.wikipedia")[0] == text


def test_cli_prints_the_summary_before_the_detail_table(run_cli, capsys):  # noqa: F811
    run_cli("cluster", "--topic", "meditation", "--language", "de")
    out = capsys.readouterr().out
    assert out.index("RECOMMENDATION") < out.index("RELATED TOPICS BY SIGNAL") < out.index("DETAIL TABLE")
