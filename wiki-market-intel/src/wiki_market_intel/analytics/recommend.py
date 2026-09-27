"""High-level recommendation: evidence-based next steps, first in every report.

The recommendation says what to *validate* first, what to monitor and what to deprioritise,
from reader attention alone. It is never a go/no-go or an investment verdict: every
sentence ends in "confirm elsewhere" (search volume, app stores, interviews).

Each option (a topic in one edition) gets one tier, the first rule that matches:

| tier           | rule                                                                              |
|----------------|-----------------------------------------------------------------------------------|
| deprioritise   | under 12,000 views a year, or 25% or more behind its edition (share-adjusted YoY)  |
| validate_first | at least 12,000 views a year, within 10% of its edition or ahead of it, and       |
|                | (when several options are compared) demand at or above the set's median            |
| monitor        | everything else                                                                   |

The three numbers are the defaults; users set their own (`Criteria`: --min-audience,
--pace-margin, --drop-margin), and the rule printed under every recommendation shows the values used.

"Behind its edition" uses share-adjusted YoY, (1 + YoY) / (1 + edition YoY) - 1, because
Wikipedia traffic falls in many editions; raw YoY is used when the edition total is missing.
Within a tier, options are listed by audience size (views in the last 12 months).

Also stated, when the data supports it: timing from the seasonal peak of the lead option,
a caution when recent momentum rests on a provisional anomaly, and (for `cluster`) which
related topics to explore and which are falling faster than the edition.
"""

from __future__ import annotations

from wiki_market_intel.analytics.ecosystem import share_adjusted
from wiki_market_intel.models.metrics import Criteria, Recommendation, RecommendationItem

DEFAULT = Criteria()            # 12,000 views a year; 10% pace margin; 25% drop margin
HEADLINE_MAX = 3


def relative(yoy: float | None, edition: float | None) -> float | None:
    """Share-adjusted YoY when the edition total is known, raw YoY otherwise."""
    if yoy is None:
        return None
    adjusted = share_adjusted(yoy, edition)
    return adjusted if adjusted is not None else yoy


def tier(views: int | None, rel: float | None, median: float | None,
         c: Criteria = DEFAULT) -> tuple[str, list[str]]:
    """(tier, reason codes). `median` is None for a single option."""
    if views is None:
        return "monitor", ["no_views"]
    if views < c.min_views:
        return "deprioritise", ["small"]
    if rel is not None and rel <= -c.drop_margin:
        return "deprioritise", ["far_behind"]
    reasons = []
    above = median is None or views >= median
    reasons.append("above_median" if median is not None and above else "below_median" if median is not None else "sizeable")
    if rel is None:
        return "monitor", reasons + ["no_yoy"]
    reasons.append("ahead" if rel > 0 else "keeps_pace" if rel >= -c.pace_margin else "behind")
    if above and rel >= -c.pace_margin:
        return "validate_first", reasons
    return "monitor", reasons


def item(label: str, views: int | None, yoy: float | None, edition: float | None, median: float | None,
         c: Criteria = DEFAULT, **extra) -> RecommendationItem:
    rel = relative(yoy, edition)
    t, reasons = tier(views, rel, median, c)
    return RecommendationItem(label=label, tier=t, reasons=reasons, annual_views=views, yoy=yoy,
                              edition_yoy=edition, relative=rel, **extra)


def build(scope: str, items: list[RecommendationItem], median: float | None = None,
          c: Criteria = DEFAULT) -> Recommendation:
    order = {"validate_first": 0, "monitor": 1, "deprioritise": 2}
    items = sorted(items, key=lambda i: (order[i.tier], -(i.annual_views or 0)))
    return Recommendation(scope=scope, items=items, median=median, criteria=c)


# ---------------------------------------------------------------------------
# per report type
# ---------------------------------------------------------------------------

def _timing(rec: Recommendation, result) -> None:
    s, sig = result.seasonality, result.signals
    if s.peak_month and sig.stability in ("moderately_seasonal", "highly_seasonal"):
        rec.peak_month, rec.peak_ratio = s.peak_month, s.peak_to_average


def _recent(rec: Recommendation, result) -> None:
    g = result.growth
    if g.momentum in ("accelerating", "decelerating") and g.last_three_month_growth is not None:
        rec.momentum, rec.recent_growth = g.momentum, g.last_three_month_growth
        provisional = [a for a in result.anomalies if a.provisional]
        if provisional:
            rec.provisional_anomaly, rec.provisional_change = provisional[-1].date, provisional[-1].change_vs_baseline


def for_analysis(result, edition: float | None, c: Criteria = DEFAULT) -> Recommendation:
    """One topic in one edition (analyze / cluster). The label uses the edition's own article title."""
    title = result.topic.article_title or result.topic.canonical_name or result.metadata.topic
    label = f"{title} · {result.metadata.project}"
    rec = build("analysis", [item(label, result.demand.annual_views, result.growth.yoy, edition, None, c,
                                  project=result.metadata.project)], None, c)
    rec.lead_label = label
    _timing(rec, result)
    _recent(rec, result)
    if result.ecosystem.computed:
        for t in result.ecosystem.related_topics:
            name = t.title + (" *" if t.relationship == "similar_content" else "")
            if t.signal in ("emerging_category", "adjacent_opportunity"):
                rec.related_explore.append(name)
            elif t.signal == "larger_category":
                rec.related_context.append(name)
            elif t.signal == "declining_category" and t.relationship != "similar_content":
                rec.related_declining.append(name)      # text-similar noise is left out here
    return rec


def for_units(scope: str, units: list[dict], median: float | None, lead_result=None,
              c: Criteria = DEFAULT) -> Recommendation:
    """Several options (comparison editions or portfolio pairs). Each unit: label, views, yoy,
    edition, project. `lead_result(label)` returns the full analysis of an option, for timing."""
    rec = build(scope, [item(u["label"], u["views"], u["yoy"], u["edition"], median, c, project=u["project"],
                             affinity=u.get("affinity")) for u in units], median, c)
    firsts = [i for i in rec.items if i.tier == "validate_first"]
    if firsts and lead_result:
        lead = lead_result(firsts[0].label)
        if lead is not None:
            rec.lead_label = firsts[0].label
            _timing(rec, lead)
            _recent(rec, lead)
    return rec


# ---------------------------------------------------------------------------
# sentences, in the report language
# ---------------------------------------------------------------------------

def margin(value: float, tr) -> str:
    """0.1 -> '10%' (no trailing .0), in the report language's number style."""
    text = f"{value * 100:g}%"
    return text.replace(".", ",") if tr.lang == "uk" else text


def _names(labels: list[str], tr, limit: int = 5) -> str:
    shown = ", ".join(labels[:limit])
    return shown + (tr("rec_and_more", n=len(labels) - limit) if len(labels) > limit else "")


def _versus(i: RecommendationItem, tr) -> str:
    """'-16.1% year over year, against -7.3% for the whole edition' (or without the edition)."""
    yoy = tr.percent(i.yoy) if i.yoy is not None else tr("na")
    if i.edition_yoy is None:
        return tr("rec_yoy_only", yoy=yoy)
    return tr("rec_yoy_vs", yoy=yoy, edition=tr.percent(i.edition_yoy))


def _why(i: RecommendationItem, tr, median: float | None, pace: float = DEFAULT.pace_margin) -> str:
    _margin_text = margin(pace, tr)
    views = tr.number(i.annual_views) if i.annual_views is not None else tr("na")
    if "small" in i.reasons:
        return tr("rec_why_small", views=views)
    if "far_behind" in i.reasons:
        return tr("rec_why_far", views=views, versus=_versus(i, tr), pct=tr.percent(abs(i.relative), signed=False))
    median_part = tr("rec_above_median", median=tr.number(median)) if median is not None and "above_median" in i.reasons \
        else tr("rec_below_median", median=tr.number(median)) if median is not None else ""
    text = tr("rec_why", views=views, median=median_part, versus=_versus(i, tr))
    if i.relative is None:
        text += tr("rec_rel_unknown")
    elif "ahead" in i.reasons:
        text += tr("rec_rel_ahead", pct=tr.percent(abs(i.relative), signed=False))
    elif "keeps_pace" in i.reasons:
        text += tr("rec_rel_pace", pct=tr.percent(abs(i.relative), signed=False), margin=_margin_text)
    else:
        text += tr("rec_rel_behind", pct=tr.percent(abs(i.relative), signed=False))
    if i.affinity is not None:
        text += tr("rec_affinity", value=tr.decimal(i.affinity))
    return text


NICHE_MIN_VIEWS = 1_000


def _what_would_change(rec: Recommendation, tr) -> list[str]:
    """When nothing qualifies: would a niche audience threshold change it, and is the concept too narrow?"""
    out = []
    c = rec.criteria
    if c.min_views > NICHE_MIN_VIEWS:
        niche = Criteria(min_views=NICHE_MIN_VIEWS, pace_margin=c.pace_margin, drop_margin=c.drop_margin)
        qualify = [i for i in rec.items if tier(i.annual_views, i.relative, rec.median, niche)[0] == "validate_first"]
        if qualify:
            out.append(tr("rec_niche_yes", n=tr.number(NICHE_MIN_VIEWS), names=_names([i.label for i in qualify], tr)))
        else:
            out.append(tr("rec_niche_no", n=tr.number(NICHE_MIN_VIEWS)))
    measured = [i for i in rec.items if i.annual_views is not None]
    if measured and all(i.annual_views < c.min_views for i in measured):
        out.append(tr("rec_too_narrow", min=tr.number(c.min_views)))
    return out


def sentences(rec: Recommendation, tr) -> list[str]:
    """[headline, supporting points..., basis], in the report language."""
    points: list[str] = []
    firsts = [i for i in rec.items if i.tier == "validate_first"]
    monitor = [i for i in rec.items if i.tier == "monitor"]
    drop = [i for i in rec.items if i.tier == "deprioritise"]

    if rec.scope == "analysis":
        i = rec.items[0]
        head = tr({"validate_first": "rec_single_validate", "monitor": "rec_single_monitor",
                   "deprioritise": "rec_single_drop"}[i.tier])
        points.append(f"{i.label}: {_why(i, tr, None, rec.criteria.pace_margin)}.")
    else:
        if firsts:
            lead = firsts[:HEADLINE_MAX]
            rest = tr("rec_then", names=_names([x.label for x in lead[1:]], tr)) if len(lead) > 1 else ""
            head = tr("rec_validate_first", first=lead[0].label, rest=rest)
            points += [f"{x.label}: {_why(x, tr, rec.median, rec.criteria.pace_margin)}." for x in lead]
            if len(firsts) > HEADLINE_MAX:
                points.append(tr("rec_also_validate", names=_names([x.label for x in firsts[HEADLINE_MAX:]], tr)))
        else:
            head = tr("rec_none_head")
            points.append(tr("rec_none", min=tr.number(rec.criteria.min_views),
                             margin=margin(rec.criteria.pace_margin, tr)))
            points += _what_would_change(rec, tr)
            biggest = max((x for x in rec.items if x.annual_views), key=lambda x: x.annual_views, default=None)
            if biggest and biggest.tier != "deprioritise":             # a deprioritised one is listed below
                points.append(tr("rec_biggest", label=biggest.label, why=_why(biggest, tr, rec.median)))
        if monitor and len(monitor) <= 5:          # each with its evidence, so the "why" comes from the data
            points += [tr("rec_monitor_item", label=x.label, why=_why(x, tr, rec.median, rec.criteria.pace_margin))
                       for x in monitor]
        elif monitor:
            points.append(tr("rec_monitor", names=_names([x.label for x in monitor], tr)))
        if drop:
            points.append(tr("rec_drop", names=_names([f"{x.label} ({_why(x, tr, None)})" for x in drop], tr, 4)))

    for project, hits in rec.missing.items():
        text = tr("rec_missing", project=project)
        if hits:
            text += " " + tr("rec_missing_hits", hits=", ".join(hits))
        points.append(text)
    if rec.peak_month and rec.lead_label:
        points.append(tr("rec_timing", label=rec.lead_label, month=tr.month(rec.peak_month, in_form=True),
                         ratio=tr.decimal(rec.peak_ratio)))
    if rec.momentum == "accelerating":
        text = tr("rec_recent_up", label=rec.lead_label, pct=tr.percent(rec.recent_growth))
        if rec.provisional_anomaly:
            text += " " + tr("rec_recent_provisional", month=rec.provisional_anomaly,
                             pct=tr.percent(rec.provisional_change))
        points.append(text)
    elif rec.momentum == "decelerating":
        points.append(tr("rec_recent_down", label=rec.lead_label, pct=tr.percent(rec.recent_growth)))
    if rec.related_explore:
        points.append(tr("rec_related_explore", names=_names(rec.related_explore, tr)))
    if rec.related_context:
        points.append(tr("rec_related_context", names=_names(rec.related_context, tr)))
    if rec.related_declining:
        points.append(tr("rec_related_declining", names=_names(rec.related_declining, tr)))
    if any(n.endswith(" *") for n in rec.related_explore + rec.related_context):
        points.append(tr("rec_similar_mark"))
    if rec.concept:
        points.insert(0, tr("rec_concept", concept=rec.concept))
    return [head, *points, tr("rec_basis")]


def rule_text(rec: Recommendation, tr) -> str:
    c = rec.criteria
    return tr("rec_rule", min=tr.number(c.min_views), median=tr("rec_rule_median") if rec.scope != "analysis" else "",
              pace=margin(c.pace_margin, tr), drop=margin(c.drop_margin, tr))


# ---------------------------------------------------------------------------
# entry points over whole results (used by the service and by `validate`)
# ---------------------------------------------------------------------------

def _concept(name: str | None, qid: str | None) -> str | None:
    return f"{name} (Wikidata {qid})" if name and qid else name


def of_analysis(result, criteria: Criteria | None = None) -> Recommendation:
    from wiki_market_intel.analytics.signals import edition_yoy
    rec = for_analysis(result, edition_yoy(result), criteria or DEFAULT)
    rec.concept = _concept(result.topic.canonical_name, result.topic.wikidata_id)
    return _with_text(rec)


def of_comparison(c, criteria: Criteria | None = None) -> Recommendation:
    from wiki_market_intel.analytics.signals import edition_yoy
    by_project = {a.metadata.project: a for a in c.analyses.values()}
    units = [{"label": r.project, "views": r.annual_views, "yoy": r.yoy_growth, "project": r.project,
              "edition": edition_yoy(by_project[r.project]), "affinity": r.topic_affinity}
             for r in c.rows if r.status == "ok" and r.annual_views is not None and r.project in by_project]
    rec = for_units("comparison", units, c.demand_threshold, by_project.get, criteria or DEFAULT)
    rec.concept = _concept(c.resolution.canonical_topic, c.resolution.wikidata_id)
    rec.missing = {f"{lang}.wikipedia": hits for lang, hits in c.missing_candidates.items()}
    for lang in c.resolution.missing_languages:
        rec.missing.setdefault(f"{lang}.wikipedia", [])
    return _with_text(rec)


def of_portfolio(p, criteria: Criteria | None = None) -> Recommendation:
    from wiki_market_intel.analytics.portfolio import label
    lookup = {}
    for r in p.rows:
        c = p.comparisons.get(r.topic)
        lookup[label(r)] = c.analyses.get(r.language) if c else p.analyses.get(r.topic)
    units = [{"label": label(r), "views": r.annual_views, "yoy": r.yoy_growth, "project": r.project,
              "edition": r.edition_yoy, "affinity": r.topic_affinity} for r in p.visible if r.status == "ok" and r.annual_views is not None]
    return _with_text(for_units("portfolio", units, p.demand_threshold, lookup.get, criteria or DEFAULT))


def _with_text(rec: Recommendation) -> Recommendation:
    from wiki_market_intel.i18n import Translator
    rec.text = sentences(rec, Translator("en"))
    return rec
