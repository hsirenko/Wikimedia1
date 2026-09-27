"""Decision signals (spec §22): five separate labels, each from one documented rule.

They are evidence for a human decision. They are never combined into a single score,
and never turned into BUY / INVEST.

| signal       | input                                   | rule                                                        |
|--------------|-----------------------------------------|-------------------------------------------------------------|
| market_size  | pageviews, last 12 months               | very_low < 12k <= low < 60k <= medium < 300k <= high < 1.5M <= very_high |
| growth       | 3-year CAGR (YoY if under 4 years)      | declining < -3% <= stable < +3% <= growing < +15% <= strongly_growing |
| momentum     | 3M growth minus previous 3M growth      | accelerating > +5 points, decelerating < -5 points, else stable |
| localization | affinity (only inside a comparison)     | weak < 0.80 <= moderate < 1.25 <= strong                    |
| stability    | anomaly episodes, then seasonal peak    | volatile: >= 2 episodes and >= 1 per 12 months checked;      |
|              |                                         | else highly_seasonal: peak >= 1.30x the average month;      |
|              |                                         | moderately_seasonal: >= 1.12x; else stable                  |

An episode is a run of consecutive flagged months: a spike and the months right after it are
one event, not three signs of volatility.

Market size is absolute on purpose (spec: "based on absolute demand"): a large edition
reaches more readers, so the same topic can be `low` in one edition and `high` in another.
Growth uses raw pageviews; the explanation adds the whole edition's YoY for context,
because Wikipedia traffic falls in many editions.
"""

from __future__ import annotations

from datetime import date

from wiki_market_intel.analytics import formulas as f
from wiki_market_intel.analytics.periods import build_periods
from wiki_market_intel.models.metrics import AnomalyAnalysis, Growth, MissingMetric, Seasonality, Signals

MARKET_SIZE = [(12_000, "very_low"), (60_000, "low"), (300_000, "medium"), (1_500_000, "high")]
GROWTH = [(-0.03, "declining"), (0.03, "stable"), (0.15, "growing")]
AFFINITY = [(0.80, "weak"), (1.25, "moderate")]
HIGHLY_SEASONAL = 1.30
MODERATELY_SEASONAL = 1.12
VOLATILE_MIN_EPISODES = 2
VOLATILE_RATE = 1 / 12      # at least one episode per year checked

SIGNAL_NAMES = ("market_size", "growth", "momentum", "localization", "stability")
REASONS = {
    "market_size": ("insufficient_data", "Needs complete pageviews for the last 12 months."),
    "growth": ("insufficient_data", "Needs at least 24 months of pageviews for YoY (48 for the 3-year CAGR)."),
    "momentum": ("insufficient_data", "Needs the last 6 months of pageviews."),
    "localization": ("unavailable", "Only defined across several editions: run `compare` with the languages to "
                                    "compare (the per-language results inside a comparison carry this value)."),
    "stability": ("insufficient_data", "Needs at least 2 years of each calendar month to separate seasonality "
                                       "from noise."),
}


def _band(value: float, bands: list[tuple[float, str]], top: str) -> str:
    for limit, label in bands:
        if value < limit:
            return label
    return top


def market_size(annual_views: int | None) -> str | None:
    return None if annual_views is None else _band(annual_views, MARKET_SIZE, "very_high")


def growth(g: Growth) -> tuple[str | None, str | None]:
    """(label, basis). The 3-year CAGR is the longer, steadier history; YoY when it is missing."""
    if g.three_year_cagr is not None:
        return _band(g.three_year_cagr, GROWTH, "strongly_growing"), "three_year_cagr"
    if g.yoy is not None:
        return _band(g.yoy, GROWTH, "strongly_growing"), "yoy"
    return None, None


def localization(affinity: float | None) -> str | None:
    return None if affinity is None else _band(affinity, AFFINITY, "strong")


def episodes(flagged: list[str]) -> int:
    """Runs of consecutive flagged months ('YYYY-MM'), each counted once."""
    index = sorted(int(m[:4]) * 12 + int(m[5:7]) for m in flagged)
    return sum(1 for i, m in enumerate(index) if i == 0 or m - index[i - 1] > 1)


def is_volatile(flagged: list[str], months_checked: int | None) -> bool:
    n = episodes(flagged)
    return bool(months_checked) and n >= VOLATILE_MIN_EPISODES and n / months_checked >= VOLATILE_RATE


def stability(s: Seasonality, flagged: list[str], months_checked: int | None) -> str | None:
    if is_volatile(flagged, months_checked):
        return "volatile"
    if s.peak_to_average is None or (s.observations_per_month or 0) < 2:
        return None
    if s.peak_to_average >= HIGHLY_SEASONAL:
        return "highly_seasonal"
    if s.peak_to_average >= MODERATELY_SEASONAL:
        return "moderately_seasonal"
    return "stable"


def compute(annual_views: int | None, g: Growth, s: Seasonality, flagged: list[str], months_checked: int | None,
            affinity: float | None = None) -> tuple[Signals, list[MissingMetric]]:
    grow, basis = growth(g)
    signals = Signals(market_size=market_size(annual_views), growth=grow, momentum=g.momentum,
                      localization=localization(affinity), stability=stability(s, flagged, months_checked),
                      growth_basis=basis)
    gaps = [MissingMetric(metric=f"signals.{name}", status=REASONS[name][0], reason=REASONS[name][1])
            for name in SIGNAL_NAMES if getattr(signals, name) is None]
    return signals, gaps


# ---------------------------------------------------------------------------
# explanations: one sentence per signal, in the report language
# ---------------------------------------------------------------------------

def _limits(label: str, bands: list[tuple[float, str]], top: str) -> tuple[float | None, float | None]:
    lower = None
    for limit, name in bands:
        if name == label:
            return lower, limit
        lower = limit
    return lower, None


def _points(value: float, lang: str) -> str:
    text = f"{value * 100:+.1f}"
    return text.replace(".", ",").replace("-", "−") if lang == "uk" else text


def edition_yoy(result) -> float | None:
    if not result.edition_monthly:
        return None
    end = date.fromisoformat(result.metadata.period_end + "-01")
    periods = build_periods(end, 12)
    return f.yoy_growth(f.total(periods["last_12m"].values(result.edition_monthly)),
                        f.total(periods["previous_12m"].values(result.edition_monthly)))


def explain(result, tr) -> dict[str, str]:
    """{signal: sentence with its evidence and rule}, built from the result's own KPIs."""
    sig, out = result.signals, {}
    num, pct, dec = tr.number, tr.percent, tr.decimal

    def band(lower, upper, fmt) -> str:
        if lower is None:
            return tr("sig_below", upper=fmt(upper))
        if upper is None:
            return tr("sig_at_least", lower=fmt(lower))
        return tr("sig_between", lower=fmt(lower), upper=fmt(upper))

    if sig.market_size:
        lo, hi = _limits(sig.market_size, MARKET_SIZE, "very_high")
        out["market_size"] = tr("sigx.market_size", views=num(result.demand.annual_views),
                                label=tr(f"sig.market_size.{sig.market_size}"),
                                band=band(lo, hi, lambda v: num(v)))
    if sig.growth:
        value = result.growth.three_year_cagr if sig.growth_basis == "three_year_cagr" else result.growth.yoy
        lo, hi = _limits(sig.growth, GROWTH, "strongly_growing")
        text = tr("sigx.growth", basis=tr(f"sig_basis.{sig.growth_basis}"), value=pct(value),
                  label=tr(f"sig.growth.{sig.growth}"), band=band(lo, hi, lambda v: pct(v)))
        edition = edition_yoy(result)
        if edition is not None:
            text += " " + tr("sigx.growth_edition", project=result.metadata.project, value=pct(edition))
        out["growth"] = text
    if sig.momentum and result.growth.acceleration is not None:
        out["momentum"] = tr("sigx.momentum", recent=pct(result.growth.last_three_month_growth),
                             previous=pct(result.growth.previous_three_month_growth),
                             points=_points(result.growth.acceleration, tr.lang),
                             label=tr(f"sig.momentum.{sig.momentum}"))
    if sig.localization:
        lo, hi = _limits(sig.localization, AFFINITY, "strong")
        out["localization"] = tr("sigx.localization", value=dec(result.localization.topic_affinity),
                                 label=tr(f"sig.localization.{sig.localization}"),
                                 band=band(lo, hi, lambda v: dec(v)))
    if sig.stability:
        info = result.anomaly_analysis or AnomalyAnalysis()
        dates = [a.date for a in result.anomalies]
        flags = tr("sigx.flags", n=len(dates), months=info.months_checked or 0, episodes=episodes(dates))
        if sig.stability == "volatile":
            out["stability"] = tr("sigx.volatile", flags=flags, label=tr("sig.stability.volatile"))
        else:
            s = result.seasonality
            month = tr.month(s.peak_month)
            out["stability"] = tr("sigx.stability", month=month.lower() if tr.lang == "uk" else month, ratio=dec(s.peak_to_average),
                                  label=tr(f"sig.stability.{sig.stability}"), flags=flags,
                                  moderate=dec(MODERATELY_SEASONAL), high=dec(HIGHLY_SEASONAL))
    return out


NO_VERDICT = ("Each edition has five separate signals; they are not combined into a score. Wikipedia pageviews "
              "measure reader attention, not revenue or demand for a product, so neither these signals nor the "
              "recommendation are a go/no-go.")


def brief(result) -> str:
    """One quote-ready English sentence with an edition's five signals and the number behind each."""
    sig, g, s = result.signals, result.growth, result.seasonality

    def part(name: str, label: str | None, detail: str | None) -> str:
        text = f"{name} {label.replace('_', ' ') if label else 'n/a'}"
        return f"{text} ({detail})" if label and detail else text

    growth_value = g.three_year_cagr if sig.growth_basis == "three_year_cagr" else g.yoy
    basis = "3-year CAGR" if sig.growth_basis == "three_year_cagr" else "YoY"
    parts = [
        part("market size", sig.market_size,
             f"{result.demand.annual_views:,} views in the last 12 months" if result.demand.annual_views else None),
        part("growth", sig.growth, f"{basis} {growth_value * 100:+.1f}%" if growth_value is not None else None),
        part("momentum", sig.momentum,
             f"{g.acceleration * 100:+.1f} points" if g.acceleration is not None else None),
        part("localization", sig.localization,
             f"affinity {result.localization.topic_affinity:.2f}" if result.localization.topic_affinity is not None
             else None),
        part("stability", sig.stability,
             f"peak {s.peak_to_average:.2f}x the average month" if s.peak_to_average is not None
             and sig.stability != "volatile" else None),
    ]
    return f"{result.metadata.project}: " + "; ".join(parts) + "."
