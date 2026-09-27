"""Decision signals (spec §22): five separate labels from written rules, never one score or verdict."""

import json

import pytest

from wiki_market_intel import analyze, compare_languages
from wiki_market_intel.analytics import signals
from wiki_market_intel.models.metrics import Growth, Seasonality, Signals
from wiki_market_intel.reporting import comparison as comparison_report
from wiki_market_intel.reporting import markdown
from wiki_market_intel.validate import validate_file
from tests.reporting.test_end_to_end import run_cli  # noqa: F401  (fixture)


@pytest.mark.parametrize("views, label", [(0, "very_low"), (11_999, "very_low"), (12_000, "low"), (59_999, "low"),
                                          (60_000, "medium"), (300_000, "high"), (1_499_999, "high"),
                                          (1_500_000, "very_high"), (None, None)])
def test_market_size_bands(views, label):
    assert signals.market_size(views) == label


def test_growth_prefers_the_three_year_cagr_and_falls_back_to_yoy():
    assert signals.growth(Growth(yoy=0.40, three_year_cagr=-0.05)) == ("declining", "three_year_cagr")
    assert signals.growth(Growth(yoy=0.02)) == ("stable", "yoy")
    assert signals.growth(Growth(yoy=0.03)) == ("growing", "yoy")
    assert signals.growth(Growth(three_year_cagr=0.15)) == ("strongly_growing", "three_year_cagr")
    assert signals.growth(Growth()) == (None, None)


@pytest.mark.parametrize("affinity, label", [(0.79, "weak"), (0.80, "moderate"), (1.249, "moderate"),
                                             (1.25, "strong"), (None, None)])
def test_localization_bands(affinity, label):
    assert signals.localization(affinity) == label


SEASONAL = dict(observations_per_month=3)


def test_stability_from_the_seasonal_peak():
    assert signals.stability(Seasonality(peak_to_average=1.05, **SEASONAL), [], 36) == "stable"
    assert signals.stability(Seasonality(peak_to_average=1.12, **SEASONAL), [], 36) == "moderately_seasonal"
    assert signals.stability(Seasonality(peak_to_average=1.30, **SEASONAL), [], 36) == "highly_seasonal"


def test_stability_needs_two_years_of_each_month():
    assert signals.stability(Seasonality(peak_to_average=1.5, observations_per_month=1), [], 12) is None


def test_consecutive_flags_are_one_episode_not_volatility():
    one_event = ["2026-06", "2026-07", "2026-08"]
    assert signals.episodes(one_event) == 1
    assert signals.stability(Seasonality(peak_to_average=1.19, **SEASONAL), one_event, 36) == "moderately_seasonal"
    spread = ["2023-12", "2024-09", "2025-05"]                       # three separate events in 3 years
    assert signals.episodes(spread) == 3
    assert signals.stability(Seasonality(peak_to_average=1.05, **SEASONAL), spread, 36) == "volatile"
    assert signals.stability(Seasonality(peak_to_average=1.05, **SEASONAL), ["2024-01", "2025-06"], 36) == "stable"


def test_missing_signals_are_reported_with_a_reason():
    s, gaps = signals.compute(None, Growth(), Seasonality(), [], None)
    assert s == Signals()
    assert {g.metric for g in gaps} == {f"signals.{n}" for n in signals.SIGNAL_NAMES}
    assert next(g for g in gaps if g.metric == "signals.localization").status == "unavailable"


def test_signals_are_separate_labels_never_a_score_or_verdict():
    fields = set(Signals.model_fields)
    assert fields == {*signals.SIGNAL_NAMES, "growth_basis", "evidence"}


# --- through the pipeline ---------------------------------------------------------------

def test_analysis_carries_signals_and_english_evidence(services):
    r = analyze("meditation", "de", "3y", services=services)
    s = r.signals
    assert s.market_size == signals.market_size(r.demand.annual_views)
    assert s.growth_basis == "three_year_cagr" and s.momentum == r.growth.momentum
    assert s.localization is None                                   # needs a comparison
    assert set(s.evidence) == {"market_size", "growth", "momentum", "stability"}
    assert "views in the last 12 months" in s.evidence["market_size"]
    assert "as a whole changed" in s.evidence["growth"]             # edition context
    metrics = {m.metric: m.status for m in r.quality.missing_metrics}
    assert metrics["signals.localization"] == "unavailable" and "signals" not in metrics


def test_comparison_fills_localization_from_affinity(services):
    c = compare_languages("meditation", ["de", "en", "fr"], "3y", services=services)
    for a in c.analyses.values():
        assert a.signals.localization == signals.localization(a.localization.topic_affinity) is not None
        assert "signals.localization" not in {m.metric for m in a.quality.missing_metrics}
        assert "Affinity" in a.signals.evidence["localization"]
    text = comparison_report.render(c, None, None, "en")
    assert "| de.wikipedia |" in text and "## 4. KPI Breakdown" in text


@pytest.mark.parametrize("lang, heading, na", [("en", "## 4. KPI Breakdown", "not computed"),
                                               ("uk", "## 4. Розбивка за показниками", "не обчислено")])
def test_kpi_breakdown_reads_each_kpi_with_its_signal(services, lang, heading, na):
    from wiki_market_intel.i18n import Translator
    tr = Translator(lang)
    r = analyze("meditation", "de", "3y", services=services)
    section = markdown.render(r, None, lang).split(heading)[1]
    assert section.count("\n| ") == 9                                # header + eight KPIs
    for name in ("market_size", "growth", "momentum", "stability"):
        assert f"**{tr(f'sig.{name}.' + getattr(r.signals, name))}**" in section
    assert na in section                                             # localization, with its reason
    if lang == "uk":
        for english in ("views in the last", "declining", "Market size", "points"):
            assert english not in section


def test_cli_kpi_breakdown_carries_each_signal_with_evidence(run_cli, capsys):  # noqa: F811
    run_cli("analyze", "--topic", "meditation", "--language", "de")
    out = capsys.readouterr().out.split("KPI BREAKDOWN")[1].split("ANOMALY")[0]
    assert "Demand (views, last 12 months): 56,910" in out and "views in the last 12 months; low is" in out
    assert "Localization:" in out and "not computed (Only defined across several editions" in out


def test_validate_catches_an_edited_signal(run_cli, settings):  # noqa: F811
    run_cli("analyze", "--topic", "meditation", "--language", "de")
    path = next(settings.reports_dir.rglob("analysis.json"))
    assert validate_file(path) == []
    data = json.loads(path.read_text("utf-8"))
    data["signals"]["growth"] = "strongly_growing"
    path.write_text(json.dumps(data), "utf-8")
    assert any(p.startswith("signals.growth:") for p in validate_file(path))


def test_compare_cli_leads_with_the_recommendation_and_lists_signals(run_cli, capsys):  # noqa: F811
    run_cli("compare", "--topic", "meditation", "--languages", "de,en,fr")
    out = capsys.readouterr().out
    assert out.index("RECOMMENDATION") < out.index("KPI BREAKDOWN") < out.index("DETAIL TABLE")
    block = out.split("SIGNALS per edition")[1]
    assert "not combined into a score" in block and "go/no-go" in block
    line = next(l for l in block.splitlines() if l.strip().startswith("- de.wikipedia:"))
    assert "market size" in line and "views in the last 12 months" in line and "affinity" in line
