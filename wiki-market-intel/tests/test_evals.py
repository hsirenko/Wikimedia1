"""The reply checker in evals/ passes a reply built from the report and catches the failures seen in testing."""

import importlib.util
from pathlib import Path

from wiki_market_intel import analyze
from wiki_market_intel.analytics import recommend
from wiki_market_intel.i18n import Translator
from wiki_market_intel.reporting import markdown

spec = importlib.util.spec_from_file_location("check_reply", Path(__file__).parents[1] / "evals" / "check_reply.py")
check_reply = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_reply)


def _good_reply(result) -> str:
    rec = recommend.sentences(result.recommendation, Translator("en"))
    g, d = result.growth, result.demand
    return "\n".join([
        "## Recommendation", *rec, "", "## KPI breakdown",
        f"- Demand: {d.annual_views:,} views in the last 12 months.",
        f"- Growth: {g.yoy * 100:+.1f}% year over year; 3-year CAGR {g.three_year_cagr * 100:+.1f}%.",
        "- Momentum: accelerating.", "- Seasonality: peak in January.", "- Localization: n/a (needs compare).",
        "- Anomalies: 2 flagged, cause unknown.", "- Data quality: HIGH.", "",
        "Would you like a one-page PDF summary of this report? I can create it for you."])


def test_a_reply_built_from_the_report_passes(services):
    r = analyze("meditation", "de", "3y", services=services)
    results = check_reply.check(_good_reply(r), markdown.render(r, None, "en"))
    assert all(x["pass"] for x in results.values()), results


def test_the_failures_seen_in_testing_are_caught(services):
    r = analyze("meditation", "de", "3y", services=services)
    bad = ("Short answer: don't launch yet. Interest fell 67% because of the rise of TikTok.\n"
           "## KPI breakdown\n- Demand: 25,473 views in 2024.\n## Recommendation\nMonitor.")
    results = check_reply.check(bad, markdown.render(r, None, "en"))
    failed = {k for k, v in results.items() if not v["pass"]}
    assert {"recommendation_first", "pdf_offer_last", "no_verdict", "no_causes", "numbers_grounded"} <= failed
    assert {"67%", "25473"} <= set(results["numbers_grounded"]["detail"])     # invented figures


def test_numbers_compare_across_number_styles():
    assert check_reply.numbers("−17,2% і 56 910") == check_reply.numbers("-17.2% and 56,910")


def test_self_made_priority_rankings_are_flagged_but_the_tools_wording_is_not():
    assert check_reply.check("Низький пріоритет за цими даними.", "")["no_verdict"]["pass"]
    flagged = check_reply.check("1. Польська — найвищий пріоритет\n2. Турецька — вторинний пріоритет", "")
    assert flagged["no_verdict"]["detail"] == ["найвищий пріоритет", "вторинний пріоритет"]


def test_orderings_in_other_words_are_flagged():
    text = ("РЕКОМЕНДОВАНА ПОСЛІДОВНІСТЬ\n1. Польська — повинна бути в пріоритеті\nПольща → Туреччина → Корея\n"
            "1. Корейська — пріоритет 1")
    assert len(check_reply.check(text, "")["no_verdict"]["detail"]) == 4
