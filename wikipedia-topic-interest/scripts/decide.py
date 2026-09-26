#!/usr/bin/env python3
"""
Turn an analysis into a decision memo: an action, the evidence behind it, what to
do next, what would change the call, and how far to trust it.

Everything here is a deterministic rule over numbers already computed in
analyze.py. Nothing is generated freely, so every sentence in the memo can be
traced to a figure, and the same data always produces the same recommendation.
The rules are listed in references/ANALYSIS_METHODS.md ("Decision rules").
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import analyze as stats
import i18n
from i18n import Translator

# Actions, strongest first. "tone" maps to a status colour in the report and is
# always shown with its label, never as colour alone.
ACTIONS = {
    "PRIORITISE": {"tone": "good"},
    "PROMISING": {"tone": "good"},
    "STABLE": {"tone": "neutral"},
    "NO_CLEAR_SIGNAL": {"tone": "neutral"},
    "DEPRIORITISE": {"tone": "bad"},
    "INSUFFICIENT_EVIDENCE": {"tone": "muted"},
}
ACTION_ORDER = list(ACTIONS)

# Names an answer may use for an edition (English, then a Ukrainian stem). The
# first is used in the memo; all are used by the claim check to match sentences.
LANGUAGE_NAMES = {
    "en": ["English", "англійськ"], "de": ["German", "німецьк"], "fr": ["French", "французьк"],
    "es": ["Spanish", "іспанськ"], "pt": ["Portuguese", "португальськ"], "it": ["Italian", "італійськ"],
    "nl": ["Dutch", "нідерландськ"], "pl": ["Polish", "польськ"], "cs": ["Czech", "чеськ"],
    "sk": ["Slovak", "словацьк"], "uk": ["Ukrainian", "українськ"], "ru": ["Russian", "російськ"],
    "tr": ["Turkish", "турецьк"], "ro": ["Romanian", "румунськ"], "hu": ["Hungarian", "угорськ"],
    "sv": ["Swedish", "шведськ"], "fi": ["Finnish", "фінськ"], "da": ["Danish", "данськ"],
    "no": ["Norwegian", "норвезьк"], "el": ["Greek", "грецьк"], "bg": ["Bulgarian", "болгарськ"],
    "hr": ["Croatian", "хорватськ"], "sr": ["Serbian", "сербськ"], "he": ["Hebrew", "іврит"],
    "ar": ["Arabic", "арабськ"], "fa": ["Persian", "перськ"], "hi": ["Hindi", "гінді"],
    "id": ["Indonesian", "індонезійськ"], "vi": ["Vietnamese", "в'єтнамськ"], "th": ["Thai", "тайськ"],
    "ja": ["Japanese", "японськ"], "ko": ["Korean", "корейськ"], "zh": ["Chinese", "китайськ"],
}


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get(code, [code])[0]


def _p(value: float) -> str:
    return "p<0.001" if value < 0.001 else f"p={value:.3f}".rstrip("0").rstrip(".")


# Below this confidence no call is made at all. It matches the "moderate" band.
MIN_CONFIDENCE_TO_DECIDE = 50


def _next_month(yyyymm: str) -> str:
    year, month = int(yyyymm[:4]), int(yyyymm[5:7])
    month += 1
    if month == 13:
        year, month = year + 1, 1
    return f"{year:04d}-{month:02d}"


def _range_text(ci: Optional[List[float]], tr: Translator = Translator()) -> str:
    return tr("range", low=f"{ci[0]:+.0f}%", high=f"{ci[1]:+.0f}%") if ci else tr("range.none")


def _range_position(ci: Optional[List[float]]) -> str:
    if not ci:
        return "unknown"
    if ci[0] > 0:
        return "above"
    if ci[1] < 0:
        return "below"
    return "crosses"


# ---------------------------------------------------------------------------
# one series
# ---------------------------------------------------------------------------

def action_for(result: Dict[str, Any]) -> str:
    """The rule table, in order. Documented in references/ANALYSIS_METHODS.md."""
    quality, volume, trend = result["quality"], result["volume"], result["trend"]
    relative = trend.get("relative")
    direction = relative["direction"] if relative else trend["direction"]
    ci = relative.get("share_ci90_pct") if relative else trend.get("ci90_pct")

    if (quality["confidence"] < MIN_CONFIDENCE_TO_DECIDE
            or volume["median_monthly"] < stats.LOW_VOLUME_MONTHLY
            or direction == "too_short_to_judge"):
        return "INSUFFICIENT_EVIDENCE"
    if direction == "growing":
        return "PRIORITISE" if _range_position(ci) == "above" else "PROMISING"
    if direction == "declining":
        return "DEPRIORITISE"
    if direction == "flat":
        return "STABLE"
    return "NO_CLEAR_SIGNAL"


def evidence(result: Dict[str, Any], tr: Translator = Translator()) -> List[str]:
    """The chain from raw numbers to the call, one step per line, each with its figure."""
    trend, volume, quality = result["trend"], result["volume"], result["quality"]
    relative = trend.get("relative")
    yoy = trend.get("year_over_year")
    period = (tr("ev.period", recent=yoy["recent_12m"]["period"], previous=yoy["previous_12m"]["period"])
              if yoy else tr("ev.period.none"))
    project = f"{result.get('lang', '')}.wikipedia"
    steps = [tr("ev.readers", raw=f"{trend['headline_change_pct']:+.1f}%", period=period,
                median=f"{volume['median_monthly']:,}")]
    if relative:
        if relative.get("edition_change_pct") is not None:
            steps.append(tr("ev.platform", project=project, edition=f"{relative['edition_change_pct']:+.1f}%"))
        position = _range_position(relative.get("share_ci90_pct"))
        steps.append(tr("ev.signal", share=f"{relative['share_change_pct']:+.1f}%",
                        range=_range_text(relative.get("share_ci90_pct"), tr), meaning=tr(f"ev.meaning.{position}")))
        if relative.get("months_up") is not None:
            steps.append(tr("ev.consistency", up=relative["months_up"], p=_p(relative["p_value"])))
    else:
        steps.append(tr("ev.no_baseline"))
    if volume.get("per_million_edition_views") is not None:
        steps.append(tr("ev.intensity", per_million=volume["per_million_edition_views"]))
    peak = tr.month(quality.get("seasonal_peak_month"))
    if peak:
        steps.append(tr("ev.timing", strength=quality["seasonality_strength"], month=peak))
    return steps


def next_steps(result: Dict[str, Any], action: str, data_to: str, tr: Translator = Translator()) -> List[str]:
    lang = result.get("lang", "")
    volume = result["volume"]
    peak = tr.month(result["quality"].get("seasonal_peak_month"))
    rerun = tr("next.rerun", month=_next_month(data_to))
    timing = [tr("next.timing", month=peak)] if peak else []
    median = f"{volume['median_monthly']:,}"
    if volume.get("per_million_edition_views") is not None:
        size = tr("next.STABLE.size_intensity", median=median, per_million=volume["per_million_edition_views"])
    else:
        size = tr("next.STABLE.size", median=median)
    language = tr.language(lang, language_name(lang))
    steps = {
        "PRIORITISE": [tr("next.PRIORITISE", language=language)] + timing + [rerun],
        "PROMISING": [tr("next.PROMISING", language=language), rerun],
        "STABLE": [size, tr("next.STABLE.search", language=language)] + timing,
        "NO_CLEAR_SIGNAL": [tr("next.NO_CLEAR_SIGNAL"), rerun],
        "DEPRIORITISE": [tr("next.DEPRIORITISE.1"), tr("next.DEPRIORITISE.2"), tr("next.DEPRIORITISE.3")],
        "INSUFFICIENT_EVIDENCE": [tr("next.INSUFFICIENT_EVIDENCE")],
    }
    return steps[action]


def would_change(result: Dict[str, Any], action: str, tr: Translator = Translator()) -> str:
    return tr(f"change.{action}", project=f"{result.get('lang', '')}.wikipedia")


def trust_notes(result: Dict[str, Any], tr: Translator = Translator()) -> List[Dict[str, str]]:
    """Plain-language limitations for this run, highest risk first.

    Each note says what the risk is *here*, with the number, rather than a generic
    caveat. Levels: high / medium / low risk.
    """
    trend, volume, quality = result["trend"], result["volume"], result["quality"]
    relative = trend.get("relative") or {}
    median = volume["median_monthly"]
    notes: List[Dict[str, str]] = []

    if median < stats.LOW_VOLUME_MONTHLY:
        notes.append({"risk": "high", "text": tr("trust.very_small", median=median)})
    elif median < stats.THIN_VOLUME_MONTHLY:
        notes.append({"risk": "medium", "text": tr("trust.small", median=median, pct=f"{50 / median * 100:.0f}%")})
    else:
        notes.append({"risk": "low", "text": tr("trust.ok", median=f"{median:,}")})

    position = _range_position(relative.get("share_ci90_pct") or trend.get("ci90_pct"))
    if position == "crosses":
        notes.append({"risk": "medium", "text": tr("trust.crosses")})
    elif position in ("above", "below"):
        notes.append({"risk": "low", "text": tr(f"trust.established.{position}")})

    if quality["volatility_pct"] > stats.HIGH_VOLATILITY:
        notes.append({"risk": "medium", "text": tr("trust.volatile", pct=f"{quality['volatility_pct']:.0f}%")})
    if quality["spike_months"] and quality["spike_share_of_views"] >= 0.10:
        # A spike that lands on the same calendar month in different years is a
        # recurring peak (school year, New Year), not news. Say which it is.
        by_calendar: Dict[str, List[str]] = {}
        for month in quality["spike_months"]:
            by_calendar.setdefault(month[5:7], []).append(month)
        recurring = [mm for mm, months in by_calendar.items() if len(months) > 1]
        share = f"{quality['spike_share_of_views'] * 100:.0f}%"
        if recurring:
            names = tr("trust.recurring.join").join(tr.month(mm) for mm in recurring)
            notes.append({"risk": "low", "text": tr("trust.recurring", months=names,
                                                    dates=", ".join(quality["spike_months"][:4]), pct=share)})
        else:
            notes.append({"risk": "medium", "text": tr("trust.one_off", dates=", ".join(quality["spike_months"][:3]),
                                                       pct=share)})
    notes.append({"risk": "medium", "text": tr("trust.one_article", title=result.get("title", ""))})
    notes.append({"risk": "medium", "text": tr("trust.curiosity")})
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(notes, key=lambda n: order[n["risk"]])


def decide_series(result: Dict[str, Any], data_to: str, tr: Translator = Translator()) -> Dict[str, Any]:
    action = action_for(result)
    relative = result["trend"].get("relative") or {}
    code = result.get("lang", "")
    what = tr("what", title=result.get("title", result["label"]), edition=tr.edition(code, language_name(code)))
    figures = (tr("headline.figures", share=f"{relative['share_change_pct']:+.1f}%",
                  range=_range_text(relative.get("share_ci90_pct"), tr)) if relative else "")
    sentence = tr(f"headline.{action}", what=what)
    position = _range_position(relative.get("share_ci90_pct"))
    if action == "STABLE" and position in ("below", "above"):
        # Inside the flat band, but the whole range is on one side of zero: a small
        # real drift. Too small to change the call, too real to hide.
        sentence += tr("headline.softening" if position == "below" else "headline.slight_gain")
    headline = tr("headline.full", short=tr(f"short.{action}"), sentence=sentence, figures=figures,
                  confidence=result["quality"]["confidence"])
    return {
        "label": result["label"],
        "action": action,
        "action_label": tr(f"action.{action}"),
        "tone": ACTIONS[action]["tone"],
        "headline": headline,
        "evidence": evidence(result, tr),
        "next_steps": next_steps(result, action, data_to, tr),
        "would_change": would_change(result, action, tr),
        "trust": trust_notes(result, tr),
    }


# ---------------------------------------------------------------------------
# the whole analysis
# ---------------------------------------------------------------------------

def _share_range(result: Dict[str, Any]) -> Optional[List[float]]:
    relative = result["trend"].get("relative")
    return (relative.get("share_ci90_pct") if relative else None) or result["trend"].get("ci90_pct")


def _within_noise(best: Dict[str, Any], calls: List[Dict[str, Any]], results: List[Dict[str, Any]]) -> List[str]:
    """Other viable candidates whose 90% range overlaps the best one's.

    Compares the chosen candidate directly with each alternative, so the warning
    cannot be lost when the ranking by growth and the ranking by action disagree.
    """
    by_label = {r["label"]: r for r in results}
    mine = _share_range(by_label[best["label"]])
    if not mine:
        return []
    ties = []
    for call in calls:
        if call is best or call["action"] in ("DEPRIORITISE", "INSUFFICIENT_EVIDENCE"):
            continue
        theirs = _share_range(by_label[call["label"]])
        if theirs and theirs[1] >= mine[0] and mine[1] >= theirs[0]:
            ties.append(call["label"])
    return ties


def decide(analysis: Dict[str, Any], lang: str = "en") -> Optional[Dict[str, Any]]:
    """Memo content for the whole run: one call per series plus an overall call.

    `lang` changes only the wording (see i18n.py); the actions are the same codes
    in every language, so checks and history compare like with like.
    """
    tr = Translator(lang)
    usable = [r for r in analysis.get("series", []) if r.get("status") == "ok"]
    if not usable:
        return None
    data_to = analysis["period"]["to"]
    calls = [decide_series(r, data_to, tr) for r in usable]

    # Overall: best action first, then the priority score the comparison computed.
    scores = {p["label"]: p["priority_score"] for p in analysis.get("comparison", {}).get("priority", [])}
    ranked = sorted(calls, key=lambda c: (ACTION_ORDER.index(c["action"]), -scores.get(c["label"], 0)))
    best = ranked[0]

    if len(calls) == 1:
        overall = best["headline"]
    else:
        overall = tr("overall.best", label=best["label"], headline=best["headline"])
        ties = _within_noise(best, calls, usable)
        if ties:
            overall += tr("overall.ties", labels=", ".join(ties))
        elif any(c["action"] not in ("DEPRIORITISE", "INSUFFICIENT_EVIDENCE") and c is not best for c in calls):
            overall += tr("overall.clear")
        dropped = [c["label"] for c in calls if c["action"] == "DEPRIORITISE"]
        if dropped:
            overall += tr("overall.dropped", labels=", ".join(dropped))
        thin = [c["label"] for c in calls if c["action"] == "INSUFFICIENT_EVIDENCE"]
        if thin:
            overall += tr("overall.thin", labels=", ".join(thin))

    return {
        "overall": overall,
        "overall_action": best["action"],
        "overall_action_label": tr(f"action.{best['action']}"),
        "language": tr.lang,
        "overall_tone": best["tone"],
        "calls": ranked,
        "rules": "references/ANALYSIS_METHODS.md#decision-rules",
    }
