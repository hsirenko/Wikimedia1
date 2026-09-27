#!/usr/bin/env python3
"""
wikitrends - the single entry point for this skill.

One command does the whole job: resolve titles, fetch pageviews, run the stats,
draw charts, write a one-page PDF, and print a short digest. That matters because
a small fast model should not have to orchestrate five scripts or hold a raw JSON
series in context.

    # Is interest in astronomy growing in Ukrainian Wikipedia?
    python3 scripts/wikitrends.py analyze --topic astronomy --langs uk --months 36

    # Compare two editions
    python3 scripts/wikitrends.py analyze --topic "intermittent fasting" --langs pl,cs --months 24

    # Compare topics inside one edition
    python3 scripts/wikitrends.py analyze --topic astronomy --topic chemistry --langs uk

    # Skip resolution when you already know the titles
    python3 scripts/wikitrends.py analyze --articles "uk:Астрономія,pl:Astronomia"

Full output lands in files; stdout stays short on purpose. Run with --help for all flags.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shlex
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import analyze as stats
import decide
import i18n
import wm_api
from wm_api import ApiError, WikimediaClient, month_window, parse_month, resolve_topic

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_MONTHS = 24
MAX_PARALLEL = 4

# Plain-language labels. "underperforming its edition" is accurate but was misread in
# testing; "LOSING GROUND" needs no decoding.
VERDICT_LABEL = {
    "outperforming its edition": "GAINING GROUND",
    "tracking its edition": "HOLDING GROUND",
    "underperforming its edition": "LOSING GROUND",
}

LIMITATIONS = [
    "Pageviews measure reading curiosity, not purchase intent or willingness to pay.",
    "Bot traffic is excluded (agent=user), but VPN use and redirects still distort edition-level figures.",
    "A language edition's readers are not a country: en.wikipedia is read worldwide.",
    "Wikipedia pageview data begins July 2015.",
    "Article quality and internal linking affect traffic independently of public interest.",
]
METHOD_NOTE = (
    "Direction comes from a Mann-Kendall trend test over all months (not first-vs-last); "
    "magnitude from a Theil-Sen slope and a year-over-year comparison of 12-month blocks, "
    "which cancels seasonality. Spike months are flagged via a median-absolute-deviation "
    "outlier test. Cross-edition figures are normalised to views per million edition views. "
    "Ranges are 90% intervals from resampling paired months; overlapping ranges mean two "
    "editions are not clearly different."
)


# ---------------------------------------------------------------------------
# argument helpers
# ---------------------------------------------------------------------------

def _split_langs(value: str) -> List[str]:
    return [item.strip().lower() for item in value.replace(" ", ",").split(",") if item.strip()]


def _parse_articles(value: str) -> List[Tuple[str, str]]:
    """'uk:Астрономія,pl:Astronomia' -> [('uk','Астрономія'), ('pl','Astronomia')]"""
    pairs = []
    for chunk in value.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if ":" not in chunk:
            raise argparse.ArgumentTypeError(f"--articles needs lang:Title, got '{chunk}'")
        lang, title = chunk.split(":", 1)
        pairs.append((lang.strip().lower(), title.strip()))
    return pairs


def _window(args) -> Tuple[str, str, str, str]:
    if args.since or args.until:
        today = date.today()
        end_month = parse_month(args.until) if args.until else month_window(1, today)[3]
        start_month = parse_month(args.since) if args.since else month_window(DEFAULT_MONTHS, today)[2]
        start = start_month.replace("-", "") + "01"
        year, month = (int(p) for p in end_month.split("-"))
        end = f"{end_month.replace('-', '')}{wm_api._last_day(year, month):02d}"
        return start, end, start_month, end_month
    return month_window(args.months)


# ---------------------------------------------------------------------------
# pipeline
# ---------------------------------------------------------------------------

def run_analysis(
    topics: List[str],
    langs: List[str],
    articles: Optional[List[Tuple[str, str]]] = None,
    months: int = DEFAULT_MONTHS,
    window: Optional[Tuple[str, str, str, str]] = None,
    pivot: str = "en",
    granularity: str = "monthly",
    agent: str = "user",
    normalise_chart: bool = False,
    weights: Optional[Dict[str, float]] = None,
    save_fetch: bool = False,
) -> Dict[str, Any]:
    """Resolve, fetch and analyse. Writes a Wikipedia snapshot when save_fetch is set."""
    client = WikimediaClient(agent=agent)
    start, end, start_month, end_month = window or month_window(months)

    # 1. Work out which (language, article title) pairs to fetch.
    targets: List[Dict[str, str]] = []
    resolutions: List[Dict[str, Any]] = []
    notes: List[str] = []

    if articles:
        for lang, title in articles:
            targets.append({"lang": lang, "title": title, "topic": title})
    else:
        for topic in topics:
            resolution = resolve_topic(topic, langs, pivot)
            resolutions.append(resolution)
            if resolution["status"] != "resolved":
                notes.append(resolution["reason"])
                continue
            for lang, title in resolution["articles"].items():
                targets.append({"lang": lang, "title": title, "topic": topic})
            for lang in resolution["missing_languages"]:
                notes.append(
                    f"{lang}.wikipedia has never created an article about '{topic}' (Wikidata "
                    f"{resolution['qid']} lists no {lang} sitelink), so there is no readership to "
                    f"measure. This is a genuine gap in that edition, not a failed title lookup."
                )

    if not targets:
        empty = {
            "status": "no_data",
            "period": {"from": start_month, "to": end_month},
            "notes": notes or ["Nothing to analyse."],
            "resolutions": resolutions,
            "series": [],
            "comparison": {},
        }
        if save_fetch:
            empty["wikipedia_fetch"] = save_wikipedia_fetch(
                topics or [title for _, title in (articles or [])],
                langs, empty["period"], resolutions, [], {},
            )
        return empty

    # 2. Fetch. Baselines are per edition and shared between topics.
    projects = sorted({f"{t['lang']}.wikipedia" for t in targets})
    baselines: Dict[str, Dict[str, int]] = {}

    # One unreachable edition (a typo'd language code, a project without data) must
    # not discard the rest of the analysis, so failures are captured per request.
    def fetch_baseline(project: str):
        try:
            return project, client.project_baseline(project, start, end, granularity), None
        except ApiError as exc:
            return project, {}, str(exc)

    def fetch_article(target: Dict[str, str]):
        project = f"{target['lang']}.wikipedia"
        try:
            return target, client.article_pageviews(project, target["title"], start, end, granularity)
        except ApiError as exc:
            return target, {"found": False, "reason": str(exc), "points": []}

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL) as pool:
        for project, data, error in pool.map(fetch_baseline, projects):
            baselines[project] = data
            if error:
                notes.append(
                    f"Could not read edition-wide totals for {project} ({error}); figures for it "
                    f"are raw views only and cannot be compared across editions."
                )
        fetched = list(pool.map(fetch_article, targets))

    raw_articles = [
        {
            "topic": target["topic"],
            "lang": target["lang"],
            "project": f"{target['lang']}.wikipedia",
            "title": target["title"],
            "found": bool(payload.get("found")),
            "reason": payload.get("reason"),
            "points": payload.get("points") or [],
        }
        for target, payload in fetched
    ]

    # 3. Analyse each series.
    # With explicit --articles the "topic" is just the title, so "lang: title" reads better.
    multi_topic = not articles and len({t["topic"] for t in targets}) > 1
    results: List[Dict[str, Any]] = []
    for target, payload in fetched:
        project = f"{target['lang']}.wikipedia"
        label = (
            f"{target['topic']} [{target['lang']}]" if multi_topic
            else f"{target['lang']}: {target['title']}"
        )
        if not payload["found"]:
            notes.append(
                f"No pageview data for '{target['title']}' in {project} over "
                f"{start_month}..{end_month} ({payload.get('reason', 'unknown reason')})."
            )
            results.append({"label": label, "status": "no_data", "project": project,
                            "title": target["title"], "series": []})
            continue
        result = stats.analyze_series(payload["points"], baselines.get(project), label)
        result.update({"project": project, "title": target["title"], "topic": target["topic"],
                       "lang": target["lang"]})
        results.append(result)

    analysis = {
        "status": "ok" if any(r.get("status") == "ok" for r in results) else "no_data",
        "period": {"from": start_month, "to": end_month, "months_requested": months},
        "settings": {"agent": agent, "granularity": granularity, "access": client.access},
        "resolutions": resolutions,
        "series": results,
        "comparison": stats.compare(results, weights),
        "notes": notes,
        "normalise_chart": normalise_chart,
    }
    # The recommendation is a fixed rule over the numbers above (decide.py), so the
    # digest, the JSON and the PDF always carry the same, reproducible call.
    analysis["decision"] = decide.decide(analysis)
    if save_fetch:
        analysis["wikipedia_fetch"] = save_wikipedia_fetch(
            topics or [title for _, title in (articles or [])],
            langs, analysis["period"], resolutions, raw_articles, baselines,
        )
    return analysis


def assets_dir() -> str:
    override = os.environ.get("WIKITRENDS_ASSETS_DIR")
    return override if override else os.path.join(SKILL_ROOT, "assets")


def _safe_filename_part(text: str) -> str:
    cleaned = "".join(c if c.isalnum() or c in "-_" else "-" for c in (text or "").strip())
    return cleaned.strip("-")[:60] or "topic"


def save_wikipedia_fetch(
    topics: List[str],
    langs: List[str],
    period: Dict[str, Any],
    resolutions: List[Dict[str, Any]],
    articles: List[Dict[str, Any]],
    baselines: Dict[str, Dict[str, int]],
) -> Optional[str]:
    """Write the Wikipedia payload for this request to assets/{topic}_{date}_{time}.json.

    This is the raw fetch (titles, monthly views, edition totals), not the analysis.
    Disabled with WIKITRENDS_NO_ASSETS so tests do not fill the skill folder.
    """
    if os.environ.get("WIKITRENDS_NO_ASSETS"):
        return None
    now = datetime.now()
    topic_part = "-".join(_safe_filename_part(t) for t in topics[:3]) if topics else "articles"
    name = f"{topic_part}_{now.strftime('%Y-%m-%d_%H%M%S')}.json"
    folder = assets_dir()
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    # Same second can produce two files on a fast rerun; keep both.
    if os.path.exists(path):
        path = os.path.join(folder, f"{topic_part}_{now.strftime('%Y-%m-%d_%H%M%S')}_{os.getpid()}.json")
    payload = {
        "saved_at": now.isoformat(timespec="seconds"),
        "topics": topics,
        "languages": langs,
        "period": period,
        "resolutions": resolutions,
        "articles": articles,
        "edition_totals": baselines,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return path


# ---------------------------------------------------------------------------
# assumptions, claim checking, run history
# ---------------------------------------------------------------------------

def assumptions(analysis: Dict[str, Any], tr: Optional["i18n.Translator"] = None) -> List[str]:
    """What the numbers silently depend on, stated for this run so it can be quoted."""
    tr = tr or i18n.Translator("en")
    period = analysis["period"]
    resolved = [r for r in analysis.get("resolutions", []) if r.get("status") == "resolved"]
    if resolved:
        source = "; ".join(tr("assume.source", topic=r["topic"], qid=r["qid"]) for r in resolved)
        articles = tr("assume.articles", source=source)
    else:
        articles = tr("assume.articles_given")
    return [
        articles,
        tr("assume.traffic", start=period["from"], end=period["to"]),
        tr("assume.growth", band=f"{stats.FLAT_BAND_PCT:.0f}", p=stats.SIGNIFICANCE_P),
        tr("assume.share"),
    ]


LANGUAGE_NAMES = decide.LANGUAGE_NAMES


def _mentions(result: Dict[str, Any], sentence: str) -> bool:
    lowered = sentence.lower()
    lang = result.get("lang", "#")
    names = LANGUAGE_NAMES.get(lang, [])
    return (result["label"] in sentence or (result.get("title") and result["title"] in sentence)
            or bool(re.search(rf"(?<![\w-]){re.escape(lang)}(?![\w-])", sentence))
            or any(name.lower() in lowered for name in names))


def _series_figures(result: Dict[str, Any]) -> Tuple[List[float], List[float]]:
    """(point figures the digest prints for one series, 90% range bounds).

    Bounds are kept apart: '+11%' is a legitimate end of a range, but not a
    legitimate growth figure, and accepting it as one lets a wrong claim through.
    """
    trend, quality = result["trend"], result["quality"]
    relative = trend.get("relative") or {}
    points = [trend["headline_change_pct"], relative.get("share_change_pct"),
              relative.get("edition_change_pct"), quality["volatility_pct"],
              round(quality["spike_share_of_views"] * 100, 1)]
    bounds = (trend.get("ci90_pct") or []) + (relative.get("share_ci90_pct") or [])
    return [v for v in points if v is not None], bounds


RANGE_WORDS = re.compile(r"\.\.|–|\bto\b|\bдо\b|range|interval|інтервал|діапазон|\bCI\b", re.IGNORECASE)


def check_text(analysis: Dict[str, Any], text: str) -> List[str]:
    """Problems in agent-written text: numbers the analysis never produced, confidence
    scores written as percentages, and verdict labels attached to the wrong series.

    Works sentence by sentence. When a sentence names exactly one edition, its numbers
    must match *that* edition's figures, so a value borrowed from another language is
    caught. Differences between growth figures are accepted only as points ('pp').
    """
    ok_series = [r for r in analysis.get("series", []) if r.get("status") == "ok"]
    figures = {r["label"]: _series_figures(r) for r in ok_series}
    growth = [r["trend"]["headline_change_pct"] for r in ok_series] + [
        r["trend"]["relative"]["share_change_pct"] for r in ok_series if r["trend"].get("relative")]
    differences = [x - y for x in growth for y in growth]
    scores = {r["quality"]["confidence"] for r in ok_series}
    level = round(stats.INTERVAL_LEVEL * 100)
    verdict_words = {"GAINING GROUND": "outperforming its edition", "HOLDING GROUND": "tracking its edition",
                     "LOSING GROUND": "underperforming its edition"}

    problems: List[str] = []
    for sentence in re.split(r"(?<=[.!?;\n])\s+", text):
        mentioned = [r for r in ok_series if _mentions(r, sentence)]
        scope = [figures[mentioned[0]["label"]]] if len(mentioned) == 1 else list(figures.values())
        talks_range = bool(RANGE_WORDS.search(sentence))
        own = [v for points, bounds in scope for v in points + (bounds if talks_range else [])]
        for match in re.finditer(r"(?<![\w.])([+\-−]?)(\d+(?:[.,]\d+)?)\s*(%|pp\b|percentage points?|"
                                 r"п\.\s?п\.|в\.\s?п\.|відсоткових пунктів|процентних пунктів)", sentence, re.IGNORECASE):
            sign = match.group(1).replace("−", "-")
            value = float(match.group(2).replace(",", "."))
            signed = -value if sign == "-" else value
            following = sentence[match.end():match.end() + 25].lower()
            if value == level and re.match(r"\s*(ci|range|interval|confidence interval|діапазон|інтервал|довірч)", following):
                continue   # "90% range" names the interval, it is not a claim
            is_points = match.group(3) != "%"
            if is_points and any(abs(value - abs(k)) <= 1.5 for k in own):
                # Every change the tool reports is relative (%). Calling -45.5% "45.5 percentage
                # points" misstates it; only differences between two figures are points.
                problems.append(f"'{match.group(0)}' is a relative change in %, not percentage points; "
                                f"write '{match.group(1)}{match.group(2)}%'.")
                continue
            pool = differences if is_points else own
            ok = any(abs(signed - k) <= 1.5 for k in pool) if sign else any(abs(value - abs(k)) <= 1.5 for k in pool)
            if ok:
                continue
            where = f" for {mentioned[0]['label']}" if len(mentioned) == 1 else ""
            if not sign and value in scores:
                problems.append(f"'{match.group(0)}' looks like a confidence score written as a percentage; "
                                f"write it as {int(value)}/100.")
            else:
                problems.append(f"'{match.group(0)}' matches no figure{where} in this analysis; "
                                f"copy numbers from the digest.")
        problems += _direction_problems(sentence, mentioned, ok_series, analysis)
        said = [w for w in verdict_words if w in sentence.upper()]
        if len(said) == 1 and len(mentioned) == 1 and mentioned[0]["trend"].get("relative"):
            actual = mentioned[0]["trend"]["relative"]["vs_edition"]
            if verdict_words[said[0]] != actual:
                problems.append(f"'{said[0]}' is attached to {mentioned[0]['label']}, but its verdict is "
                                f"{VERDICT_LABEL[actual]}.")
    return problems


# Direction words, English and Ukrainian stems. Used to catch prose that contradicts
# the recommendation, e.g. "interest is stable" on a DEPRIORITISE call.
DIRECTION_WORDS = {
    "growth": ["grow", "rising", "increas", "gaining", "upward", "зроста", "росте", "зріс", "збільшу", "підвищ"],
    "steady": ["stable", "steady", "holding", "стабільн", "стійк", "тримається", "незмінн"],
    "decline": ["declin", "falling", "drop", "decreas", "losing", "падає", "падін", "знижу", "скороч", "спада", "втрача"],
}
NEGATIONS = ("not ", "no ", "n't ", "не ", "ні ", "без ", "rather than ")
PLATFORM_WORDS = re.compile(r"platform|edition|wikipedia (as a whole|overall|traffic)|платформ|редакці|видання в цілому|всієї",
                            re.IGNORECASE)
FORBIDDEN = {   # action -> direction words that contradict it
    "DEPRIORITISE": ["growth", "steady"],
    "PRIORITISE": ["decline", "steady"],
    "PROMISING": ["decline"],
    "STABLE": ["growth"],
}


def _direction_problems(sentence: str, mentioned: List[Dict[str, Any]], ok_series: List[Dict[str, Any]],
                        analysis: Dict[str, Any]) -> List[str]:
    """Flag direction words that contradict the recommendation for the edition a sentence is about."""
    decision = analysis.get("decision") or {}
    actions = {c["label"]: c["action"] for c in decision.get("calls", [])}
    if len(mentioned) == 1:
        subject = mentioned[0]["label"]
    elif not mentioned and len(ok_series) == 1:
        subject = ok_series[0]["label"]      # one edition: every sentence is about it
    else:
        return []
    action = actions.get(subject)
    if not action or PLATFORM_WORDS.search(sentence):
        return []   # sentences about the platform's own trend are allowed any direction
    lowered = " " + sentence.lower()
    for kind in FORBIDDEN.get(action, []):
        if any(_affirmed(lowered, stem) for stem in DIRECTION_WORDS[kind]):
            return [f"'{sentence.strip()[:70]}' describes {subject} as {kind}, but the recommendation is "
                    f"{action}. Rewrite it to match the RECOMMENDATION line."]
    return []


def _affirmed(text: str, stem: str) -> bool:
    """The stem occurs at least once without a negation just before it ('не зростає' is fine)."""
    at = text.find(stem)
    while at != -1:
        if not any(neg in text[max(0, at - 14):at] for neg in NEGATIONS):
            return True
        at = text.find(stem, at + 1)
    return False


RUN_LOG = "runs.jsonl"


def _run_summary(analysis: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for result in analysis.get("series", []):
        if result.get("status") != "ok":
            continue
        relative = result["trend"].get("relative") or {}
        out[result["label"]] = {
            "raw_pct": result["trend"]["headline_change_pct"],
            "share_pct": relative.get("share_change_pct"),
            "verdict": VERDICT_LABEL.get(relative.get("vs_edition"), "n/a"),
            "confidence": result["quality"]["confidence"],
            "median_monthly": result["volume"]["median_monthly"],
        }
    return out


def record_run(analysis: Dict[str, Any], out_dir: str, slug: str, files: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """Append this run to out_dir/runs.jsonl and return the previous run of the same
    topics and languages, if any, so follow-ups can say what changed."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, RUN_LOG)
    previous = None
    for record in read_runs(out_dir):
        if record.get("slug") == slug:
            previous = record
    record = {
        "at": datetime.now().isoformat(timespec="seconds"),
        "slug": slug,
        "period": analysis["period"],
        "weights": analysis.get("comparison", {}).get("weights"),
        "json": files.get("json"),
        "series": _run_summary(analysis),
    }
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return previous


def _seen_before(out_dir: str, slug: str, analysis: Dict[str, Any]) -> bool:
    """True if this exact analysis (same run name, same data window) was run before,
    so the agent has had the chance to read its results."""
    return any(r.get("slug") == slug and r.get("period", {}).get("to") == analysis["period"]["to"]
               for r in read_runs(out_dir))


def read_runs(out_dir: str) -> List[Dict[str, Any]]:
    path = os.path.join(out_dir, RUN_LOG)
    if not os.path.exists(path):
        return []
    runs = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            try:
                runs.append(json.loads(line))
            except ValueError:
                continue   # a half-written line must not break history
    return runs


def since_last_run(previous: Optional[Dict[str, Any]], analysis: Dict[str, Any]) -> List[str]:
    if not previous:
        return []
    now = _run_summary(analysis)
    same_period = previous.get("period", {}).get("to") == analysis["period"]["to"]
    lines = [f"SINCE_LAST_RUN {previous['at']} (data to {previous['period']['to']}"
             + (", same data window" if same_period else "") + "):"]
    for label, current in now.items():
        before = previous["series"].get(label)
        if not before:
            lines.append(f"    {label}: new in this run")
            continue
        change = ("unchanged" if before["verdict"] == current["verdict"]
                  else f"{before['verdict']} -> {current['verdict']}")
        share = (f"share {before['share_pct']:+.1f}% -> {current['share_pct']:+.1f}%"
                 if before.get("share_pct") is not None and current.get("share_pct") is not None else "")
        lines.append(f"    {label}: verdict {change}; {share}".rstrip("; "))
    for label in previous["series"]:
        if label not in now:
            lines.append(f"    {label}: not in this run")
    return lines


# ---------------------------------------------------------------------------
# output
# ---------------------------------------------------------------------------

def auto_findings(analysis: Dict[str, Any]) -> List[str]:
    """Factual sentences straight from the numbers, no interpretation added.

    The agent is expected to write the real narrative; these exist so a PDF is
    never empty and so the wording always carries the caveat with the number.
    """
    findings = []
    for row in analysis["comparison"].get("ranking", []):
        sentence = (
            f"{row['label']}: raw views {row['momentum_pct']:+.0f}% year over year, "
            f"{row['reach_median_monthly']:,} views/month median, "
            f"confidence {row['confidence']}/100"
        )
        if row.get("vs_edition"):
            sentence += (
                f" - share of edition traffic {row['relative_momentum_pct']:+.0f}% "
                f"({row['vs_edition']})"
            )
        if not row["significant"] and row["direction"] in ("unclear", "flat"):
            sentence += "; not statistically distinguishable from noise"
        findings.append(sentence + ".")
    for note in analysis.get("notes", [])[:2]:
        findings.append(note)
    return findings


def table_rows(analysis: Dict[str, Any]) -> List[List[str]]:
    rows = [["Language / article", "Views/mo", "Per million", "Raw change", "Share change", "vs edition", "Confidence"]]
    for result in analysis["series"]:
        if result.get("status") != "ok":
            rows.append([result["label"], "no data", "-", "-", "-", "-", "-"])
            continue
        per_million = result["volume"]["per_million_edition_views"]
        relative = result["trend"].get("relative")
        rows.append([
            result["label"],
            f"{result['volume']['median_monthly']:,}",
            f"{per_million:g}" if per_million is not None else "-",
            f"{result['trend']['headline_change_pct']:+.1f}%",
            f"{relative['share_change_pct']:+.1f}%" if relative else "-",
            # Short words keep this column from wrapping in a narrow table cell.
            {"outperforming its edition": "above",
             "underperforming its edition": "below",
             "tracking its edition": "tracks"}.get(relative["vs_edition"], "-") if relative else "-",
            f"{result['quality']['confidence']} ({result['quality']['confidence_band']})",
        ])
    return rows


def scorecard_rows(analysis: Dict[str, Any], memo: Optional[Dict[str, Any]] = None,
                   tr: Optional["i18n.Translator"] = None) -> List[List[str]]:
    """One row per edition for the memo, in the order of the recommendation."""
    tr = tr or i18n.Translator("en")
    memo = memo or analysis.get("decision") or {}
    rows = [[tr("score.edition"), tr("score.action"), tr("score.readers"),
             tr("score.share"), tr("score.months_up"), tr("score.confidence")]]
    by_label = {r["label"]: r for r in analysis["series"] if r.get("status") == "ok"}
    for call in memo.get("calls", []):
        result = by_label[call["label"]]
        relative = result["trend"].get("relative") or {}
        ci = relative.get("share_ci90_pct")
        share = (f"{relative['share_change_pct']:+.1f}%" + (f" ({ci[0]:+.0f}..{ci[1]:+.0f})" if ci else "")
                 if relative else "n/a")
        up = relative.get("months_up")
        rows.append([call["label"], call.get("action_label") or call["action"].replace("_", " "),
                     f"{result['volume']['median_monthly']:,}",
                     share, f"{up}" if up is not None else "-", f"{result['quality']['confidence']}/100"])
    for result in analysis["series"]:
        if result.get("status") != "ok":
            rows.append([result["label"], tr("score.no_data"), "-", "-", "-", "-"])
    return rows


def format_reply_report(
    analysis: Dict[str, Any],
    title: str,
    question: str,
    summary: str,
    findings: List[str],
    tr: "i18n.Translator",
) -> str:
    """The decision memo as Markdown: this is what the agent pastes into the reply."""
    memo = analysis.get("decision")
    if analysis.get("status") != "ok" or not memo:
        return ""
    period = analysis["period"]
    local = decide.decide(analysis, tr.lang) or memo
    lines = [
        f"# {title}",
        "",
        tr("memo.subtitle", start=period["from"], end=period["to"], today=date.today().isoformat()),
        "",
    ]
    if question:
        lines += [f"**{tr('memo.question')}** {question}", ""]
    lines += [
        f"## {tr('memo.recommendation', action=local.get('overall_action_label') or local['overall_action'])}",
        "",
        local["overall"],
        "",
    ]
    for note in ([summary] if summary else []) + list(findings):
        if note:
            lines += [f"**{tr('memo.analyst_note')}** {note}", ""]
    rows = scorecard_rows(analysis, local, tr)
    if len(rows) > 1:
        lines.append("| " + " | ".join(rows[0]) + " |")
        lines.append("| " + " | ".join("---" for _ in rows[0]) + " |")
        for row in rows[1:]:
            lines.append("| " + " | ".join(row) + " |")
        lines.append("")
    lead = local["calls"][0]
    lines += [f"## {tr('memo.why', label=lead['label'])}", ""]
    for i, step in enumerate(lead["evidence"], 1):
        lines.append(f"{i}. {step}")
    lines += ["", f"## {tr('memo.next')}", ""]
    for step in lead["next_steps"]:
        lines.append(f"- {step}")
    lines += ["", f"## {tr('memo.change')}", "", lead["would_change"], ""]
    lines += [f"## {tr('memo.trust')}", ""]
    for note in lead["trust"][:6]:
        lines.append(f"- **{tr('risk.' + note['risk'])}** {note['text']}")
    lines += ["", f"## {tr('memo.assumptions')}", ""]
    for item in assumptions(analysis, tr):
        lines.append(f"- {item}")
    lines += ["", f"*{tr('memo.footer')}*", ""]
    return "\n".join(lines)


def write_outputs(
    analysis: Dict[str, Any],
    out_dir: str,
    slug: str,
    title: str,
    question: str,
    findings: Optional[List[str]] = None,
    make_pdf: bool = False,
    summary: str = "",
    reproduce: str = "",
    report_lang: str = "en",
) -> Dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    files: Dict[str, str] = {}

    json_path = os.path.join(out_dir, f"{slug}.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(analysis, fh, ensure_ascii=False, indent=2)
    files["json"] = json_path

    csv_path = os.path.join(out_dir, f"{slug}.csv")
    with open(csv_path, "w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(["label", "project", "article", "month", "views", "edition_views_per_million"])
        for result in analysis["series"]:
            if result.get("status") != "ok":
                continue
            per_million = result["volume"]["per_million_edition_views"]
            for point in result["series"]:
                writer.writerow([result["label"], result.get("project", ""), result.get("title", ""),
                                 point["month"], point["views"], per_million if per_million is not None else ""])
    files["csv"] = csv_path

    tr = i18n.Translator(report_lang)
    memo_md = format_reply_report(analysis, title, question, summary, findings or [], tr)
    if memo_md:
        md_path = os.path.join(out_dir, f"{slug}.md")
        with open(md_path, "w", encoding="utf-8") as fh:
            fh.write(memo_md)
        files["report"] = md_path

    if not make_pdf or not analysis.get("decision"):
        return files

    import report  # imported late so --pdf is not required for the in-chat report

    # Same rules, same actions; only the words follow the reader's language.
    memo = decide.decide(analysis, tr.lang) if analysis.get("decision") else None
    share_chart = report.make_share_chart(analysis["series"], os.path.join(out_dir, f"{slug}_share.png"), tr)
    ok_series = [r for r in analysis["series"] if r.get("status") == "ok"]
    if len(ok_series) == 1:
        # One edition: a single range bar says little; topic-vs-platform says the most.
        range_chart = report.make_vs_platform_chart(ok_series[0], os.path.join(out_dir, f"{slug}_vs_platform.png"), tr)
    else:
        range_chart = (report.make_range_chart(analysis["series"], memo["calls"],
                                               os.path.join(out_dir, f"{slug}_range.png"), tr) if memo else None)
    if not share_chart:   # no edition baseline: fall back to raw views
        share_chart = report.make_chart(
            analysis["series"],
            f"Monthly Wikipedia pageviews, {analysis['period']['from']} to {analysis['period']['to']}",
            os.path.join(out_dir, f"{slug}_trend.png"))
    for key, path in (("chart", share_chart), ("range_chart", range_chart)):
        if path:
            files[key] = path

    period = analysis["period"]
    built = report.build_memo(
        path=os.path.join(out_dir, f"{slug}.pdf"),
        title=title,
        subtitle=tr("memo.subtitle", start=period["from"], end=period["to"], today=date.today().isoformat()),
        question=question,
        memo=memo,
        scorecard=scorecard_rows(analysis, memo, tr),
        chart_paths=[c for c in (share_chart, range_chart) if c],
        assumptions=assumptions(analysis, tr),
        method_note=tr("memo.method_note"),
        analyst_notes=([summary] if summary else []) + list(findings or []),
        reproduce=reproduce,
        tr=tr,
    )
    files["pdf"] = built["path"]
    if built["pages"] > 1:
        files["pdf_pages"] = str(built["pages"])
    return files


def report_language(args) -> Tuple[str, str]:
    """(language the user wrote in, language the memo will use).

    Detected from the user's own words (--question, then --summary/--finding), so
    a small model does not have to remember a flag. --report-lang overrides it.
    """
    chosen = getattr(args, "report_lang", "auto") or "auto"
    if chosen != "auto":
        wanted = chosen.lower()
    else:
        wanted = i18n.detect_language(" ".join(filter(None, [getattr(args, "question", ""),
                                                             getattr(args, "summary", "")]
                                                      + list(getattr(args, "finding", None) or []))))
    return wanted, (wanted if wanted in i18n.SUPPORTED else "en")


def digest(analysis: Dict[str, Any], files: Dict[str, str], brief: bool = False,
           previous: Optional[Dict[str, Any]] = None, report_lang: str = "en", wanted_lang: str = "en") -> str:
    """Short text summary for the agent's context.

    Deliberately compact: the monthly series stays in the CSV, and only the numbers
    needed to write an answer are printed. Confidence reasons are included because
    the agent must be able to quote why a signal is weak.
    """
    period = analysis["period"]
    lines = [f"PERIOD {period['from']}..{period['to']}  (complete months only, bots excluded)"]

    if analysis["status"] != "ok":
        lines.append("RESULT no usable data")
        lines += [f"NOTE {n}" for n in analysis.get("notes", [])]
        return "\n".join(lines)

    for resolution in analysis.get("resolutions", []):
        if resolution["status"] == "resolved":
            titles = ", ".join(f"{k}={v}" for k, v in resolution["articles"].items())
            lines.append(f"RESOLVED '{resolution['topic']}' -> {resolution['qid']} ({titles})")

    for result in analysis["series"]:
        if result.get("status") != "ok":
            lines.append(f"- {result['label']}: NO DATA")
            continue
        trend, volume, quality = result["trend"], result["volume"], result["quality"]
        per_million = volume["per_million_edition_views"]
        lines.append(
            f"- {result['label']}: raw {trend['headline_change_pct']:+.1f}% {trend['headline_period']} "
            f"({trend['direction']}, p={trend['p_value']}), "
            f"median {volume['median_monthly']:,}/mo"
            + (f", {per_million:g}/M edition views" if per_million is not None else "")
            + f", confidence {quality['confidence']}/100 {quality['confidence_band']}"
        )
        relative = trend.get("relative")
        if relative:
            # One self-contained sentence, safe to quote on its own. Fast models
            # juggling several runs otherwise mix up percentages between them.
            lines.append(f"    verdict: {VERDICT_LABEL[relative['vs_edition']]} - {trend['interpretation']}")
        ranges = []
        if trend.get("ci90_pct"):
            ranges.append("raw {:+.0f}..{:+.0f}%".format(*trend["ci90_pct"]))
        if relative and relative.get("share_ci90_pct"):
            ranges.append("share {:+.0f}..{:+.0f}%".format(*relative["share_ci90_pct"]))
        if ranges:
            lines.append("    90% range: " + ", ".join(ranges))
        if not brief:
            for reason in quality["reasons"][:2]:
                lines.append(f"    why: {reason}")
            if quality["spike_months"]:
                by_calendar: Dict[str, int] = {}
                for month in quality["spike_months"]:
                    by_calendar[month[5:7]] = by_calendar.get(month[5:7], 0) + 1
                recurring = [i18n.MONTHS["en"][int(mm) - 1] for mm, n in by_calendar.items() if n > 1]
                note = (f" (recurring {' and '.join(recurring)} peak every year, not news)" if recurring
                        else " (one-off: likely news or an event)")
                lines.append(f"    spikes: {', '.join(quality['spike_months'][:4])}{note}")
            if quality["seasonality_strength"] and quality["seasonality_strength"] > 0.5:
                lines.append(
                    f"    seasonal: strength {quality['seasonality_strength']} "
                    f"- compare like months, not consecutive ones"
                )

    tiers = analysis["comparison"].get("tiers", {})
    for tier, labels in tiers.items():
        if labels:
            lines.append(f"TIER {tier}: {', '.join(labels)}")
    memo = analysis.get("decision")
    if memo and report_lang != "en":
        local = decide.decide(analysis, report_lang)
        lines.append(f"REPORT_LANGUAGE {report_lang}: the PDF memo is in this language. Reply to the user in it too.")
        lines.append(f"RECOMMENDATION_{report_lang.upper()} {local['overall_action_label']}: {local['overall']}")
    elif memo and wanted_lang != report_lang:
        lines.append(f"REPORT_LANGUAGE en: the user wrote in '{wanted_lang}', which has no memo translation yet "
                     f"(available: {', '.join(i18n.SUPPORTED)}). Tell the user the PDF is in English, and "
                     f"still reply to them in their language.")
    if memo:
        lines.append(f"RECOMMENDATION {memo['overall_action']}: {memo['overall']}")
        for call in memo["calls"]:
            lines.append(f"    {call['label']}: {call['action']} - next: {call['next_steps'][0]}")
            lines.append(f"      would change if: {call['would_change']}")
    gap = analysis["comparison"].get("separation")
    if gap:
        lines.append(f"SEPARATION {gap['statement']}")
    ranked = analysis["comparison"].get("priority", [])
    if len(ranked) > 1:
        weights = analysis["comparison"].get("weights", {})
        lines.append(
            "PRIORITY (weights " + ", ".join(f"{k}={v:g}" for k, v in weights.items())
            + "; score 0-100 from ranks within this comparison, not a probability): "
            + " > ".join(f"{r['label']} {r['priority_score']}" for r in ranked)
        )
    by_intensity = analysis["comparison"].get("by_intensity", [])
    if len(by_intensity) > 1:
        lines.append(f"BY_INTENSITY (per-capita interest): {' > '.join(by_intensity)}")

    for note in analysis.get("notes", []):
        lines.append(f"NOTE {note}")
    lines += since_last_run(previous, analysis)
    lines.append("ASSUMPTIONS")
    lines += [f"    - {a}" for a in assumptions(analysis)]
    for key, value in files.items():
        lines.append(f"FILE {key}: {value}")
    lines.append("CAVEAT Reading interest is not demand; treat tiers as research ordering only.")
    report_path = files.get("report")
    if report_path and os.path.exists(report_path) and not brief:
        with open(report_path, encoding="utf-8") as fh:
            body = fh.read().strip()
        if body:
            lines += ["", "BEGIN_REPLY_REPORT", body, "END_REPLY_REPORT"]
            lines.append("DELIVER the block above as the user's report (in the reply, or a Cursor canvas). "
                         "Copy it; do not rewrite the numbers.")
    if analysis.get("status") == "ok" and not files.get("pdf"):
        ask = i18n.Translator(report_lang)("ask.pdf")
        lines.append(f"ASK_PDF {ask}")
        lines.append("Ask that question separately after the report. Do not generate a PDF until they say yes. "
                     "If they say yes, rerun the same analyze command with --pdf.")
    return "\n".join(lines)


def _slug(topics: List[str], langs: List[str]) -> str:
    """Filename base naming every topic and language.

    If that is too long, it is shortened and a hash of the full list is appended,
    so two different runs can never overwrite each other's files.
    """
    base = "-".join(topics + langs)
    safe = "".join(c if c.isalnum() or c in "-_" else "-" for c in base.lower()).strip("-")
    slug = "wikitrends-" + safe
    if len(slug) > 70:
        digest_ = hashlib.sha1(base.encode("utf-8")).hexdigest()[:8]
        slug = slug[:61].rstrip("-") + "-" + digest_
    return slug if safe else "wikitrends"


def _parse_weights(value: Optional[str]) -> Optional[Dict[str, float]]:
    """'momentum=2,reach=1' -> {'momentum': 2.0, 'reach': 1.0}."""
    if not value:
        return None
    weights: Dict[str, float] = {}
    for part in value.split(","):
        key, _, number = part.partition("=")
        key = key.strip().lower()
        if key not in stats.DEFAULT_WEIGHTS:
            raise ValueError(f"unknown weight '{key}'; use reach, intensity, momentum")
        try:
            weights[key] = float(number)
        except ValueError:
            raise ValueError(f"weight for '{key}' must be a number, got '{number}'") from None
        if weights[key] < 0:
            raise ValueError(f"weight for '{key}' must not be negative")
    return weights


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------

def cmd_analyze(args) -> int:
    if getattr(args, "offline", False):
        os.environ["WIKITRENDS_OFFLINE"] = "1"
        wm_api.MISSES.clear()
    articles = _parse_articles(args.articles) if args.articles else None
    topics = args.topic or []
    langs = _split_langs(args.langs) if args.langs else []

    if articles:
        langs = langs or sorted({lang for lang, _ in articles})
    elif not topics or not langs:
        sys.stderr.write("Need --topic plus --langs, or --articles lang:Title,...\n")
        return 2

    try:
        weights = _parse_weights(getattr(args, "weights", None))
    except ValueError as exc:
        sys.stderr.write(f"--weights: {exc}\n")
        return 2

    try:
        analysis = run_analysis(
            topics=topics, langs=langs, articles=articles, months=args.months,
            window=_window(args), pivot=args.pivot, granularity=args.granularity,
            agent=args.agent, normalise_chart=args.normalise, weights=weights,
            save_fetch=True,
        )
    except ApiError as exc:
        if _looks_blocked(str(exc), exc.status) and not getattr(args, "offline", False):
            print(network_blocked_help(args, str(exc)))
            return EXIT_NETWORK_BLOCKED
        sys.stderr.write(f"Wikimedia API error: {exc}\n")
        return 4

    blocked_notes = [n for n in analysis.get("notes", []) if _looks_blocked(n)]
    if analysis["status"] != "ok" and blocked_notes and not getattr(args, "offline", False):
        print(network_blocked_help(args, blocked_notes[0]))
        return EXIT_NETWORK_BLOCKED

    slug = args.slug or _slug(topics, langs)
    if (args.summary or args.finding) and not _seen_before(args.out_dir, slug, analysis):
        print(digest(analysis, {}, brief=True))
        print("\nSUMMARY_BEFORE_DATA: --summary/--finding were given before this analysis had been run and read.")
        print("Read the RECOMMENDATION above, write your summary from it, then rerun the same command")
        print("(cached, about a second). The PDF will be built then.")
        record_run(analysis, args.out_dir, slug, {})
        return EXIT_SUMMARY_BEFORE_DATA
    problems = check_text(analysis, " ".join([args.summary or ""] + (args.finding or [])))
    blocked_pdf = bool(problems) and not args.allow_unchecked

    wanted, report_lang = report_language(args)
    tr = i18n.Translator(report_lang)
    ok_titles = [r["title"] for r in analysis["series"] if r.get("status") == "ok"]
    # One edition: name the topic by its article in that language ("Астрономія").
    shown_topic = ok_titles[0] if len(langs) == 1 and len(ok_titles) == 1 else (
        ", ".join(topics) if topics else ", ".join(langs))
    title = args.title or tr("memo.title", topics=shown_topic,
                             editions=tr.editions(langs, [decide.language_name(l) for l in langs]))
    analysis["assumptions"] = assumptions(analysis)
    files = write_outputs(
        analysis, args.out_dir, slug, title, args.question or "",
        findings=args.finding or None, make_pdf=bool(getattr(args, "pdf", False)) and not blocked_pdf,
        summary=args.summary or "", reproduce=_same_args(args, "analyze"), report_lang=report_lang,
    )
    if analysis.get("wikipedia_fetch"):
        files["wikipedia_fetch"] = analysis["wikipedia_fetch"]
    previous = record_run(analysis, args.out_dir, slug, files)

    if args.json:
        print(json.dumps(analysis, ensure_ascii=False, indent=2))
    else:
        print(digest(analysis, files, brief=args.brief, previous=previous,
                     report_lang=report_lang, wanted_lang=wanted))

    if problems:
        print("\nCHECK_FAILED in your --summary/--finding text:" if blocked_pdf else "\nCHECK warnings (--allow-unchecked):")
        for problem in problems:
            print(f"  - {problem}")
        if blocked_pdf:
            print("PDF NOT written. Fix the findings to match the digest and rerun (cached, ~1s).")
            return EXIT_CHECK_FAILED

    if getattr(args, "offline", False) and wm_api.MISSES:
        print(f"\nOFFLINE: {len(wm_api.MISSES)} needed response(s) are not cached, so the "
              f"analysis above is incomplete.\nRun the `plan` command with the same arguments "
              f"to get the list of URLs to fetch.")
        return 3
    return 0 if analysis["status"] == "ok" else 2


def cmd_check(args) -> int:
    """Verify an answer draft against a saved analysis before sending it."""
    with open(args.json, encoding="utf-8") as fh:
        analysis = json.load(fh)
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            text = fh.read()
    else:
        text = args.text or ""
    problems = check_text(analysis, text)
    if not problems:
        count = len(re.findall(r"\d+(?:[.,]\d+)?\s*%", text))
        print(f"CHECK_OK: {count} percentage(s) and all verdict labels match {os.path.basename(args.json)}.")
        return 0
    print("CHECK_FAILED:")
    for problem in problems:
        print(f"  - {problem}")
    return EXIT_CHECK_FAILED


def cmd_history(args) -> int:
    """List earlier runs so related questions can build on them instead of memory."""
    runs = read_runs(args.out_dir)[-args.limit:]
    if not runs:
        print(f"No runs recorded in {args.out_dir}/{RUN_LOG} yet.")
        return 0
    for record in runs:
        series = "; ".join(f"{label} {v['verdict']} share {v['share_pct']:+.1f}%" if v.get("share_pct") is not None
                           else f"{label} {v['verdict']}" for label, v in record["series"].items())
        print(f"{record['at']}  {record['slug']}  data to {record['period']['to']}")
        print(f"    {series}")
        print(f"    json: {record.get('json')}")
    return 0


def cmd_resolve(args) -> int:
    langs = _split_langs(args.langs)
    out = [resolve_topic(topic, langs, args.pivot) for topic in args.topic]
    if args.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0
    for resolution in out:
        if resolution["status"] != "resolved":
            print(f"{resolution['topic']}: UNRESOLVED - {resolution['reason']}")
            if resolution.get("candidates"):
                print("  candidates: " + ", ".join(c["title"] for c in resolution["candidates"][:5]))
            continue
        print(f"{resolution['topic']} -> {resolution['qid']} ({resolution['concept']}"
              f"{'; ' + resolution['description'] if resolution['description'] else ''})")
        for lang, title in resolution["articles"].items():
            print(f"  {lang}: {title}")
        for lang in resolution["missing_languages"]:
            print(f"  {lang}: NO ARTICLE in this edition")
        if resolution["other_candidates"]:
            print("  other possible concepts: " + ", ".join(resolution["other_candidates"]))
    return 0 if all(r["status"] == "resolved" for r in out) else 2


def cmd_plan(args) -> int:
    """List the URLs an analysis still needs, for sandboxes with no network.

    Rather than rebuilding every URL by hand, this runs the real pipeline with the
    network switched off and collects whatever the cache could not serve. So the
    plan can never drift out of step with what `analyze` actually requests.

    Some URLs only become knowable once earlier ones are fetched (an article's
    Wikidata id has to be read before its translations can be looked up), so this
    is a loop: plan, fetch, ingest, repeat until it reports READY.
    """
    os.environ["WIKITRENDS_OFFLINE"] = "1"
    wm_api.MISSES.clear()

    articles = _parse_articles(args.articles) if args.articles else None
    topics = args.topic or []
    langs = _split_langs(args.langs) if args.langs else []
    if articles:
        langs = langs or sorted({lang for lang, _ in articles})
    elif not topics or not langs:
        sys.stderr.write("Need --topic plus --langs, or --articles lang:Title,...\n")
        return 2

    analysis = run_analysis(
        topics=topics, langs=langs, articles=articles, months=args.months,
        window=_window(args), pivot=args.pivot, granularity=args.granularity, agent=args.agent,
    )
    missing = list(wm_api.MISSES)

    if not missing:
        print("READY - everything this analysis needs is already cached.")
        print("Next: rerun the same arguments with `analyze --offline` to get the report.")
        return 0

    os.makedirs(args.out_dir, exist_ok=True)
    plan = [
        {"url": url, "save_as": f"{index:02d}-{wm_api.cache_key(url)[:8]}.json"}
        for index, url in enumerate(missing, 1)
    ]
    plan_path = os.path.join(args.out_dir, "fetch-plan.json")
    with open(plan_path, "w", encoding="utf-8") as fh:
        json.dump(plan, fh, ensure_ascii=False, indent=2)

    print(f"FETCH {len(plan)} URL(s). Save each response body as raw JSON, unmodified,")
    print(f"into {args.out_dir}/ using the given filename:")
    for entry in plan:
        print(f"  {entry['save_as']}  <-  {entry['url']}")
    print(f"\nThen run: wikitrends.py ingest --dir {args.out_dir}")
    print("After ingest, run this same plan command again. Repeat until it prints READY.")
    if analysis["status"] != "ok" and not articles:
        print("Tip: passing --articles lang:Title (instead of --topic) needs only one round.")
    return 3


def cmd_ingest(args) -> int:
    """Load responses fetched elsewhere into the cache."""
    plan_path = os.path.join(args.dir, "fetch-plan.json")
    if not os.path.exists(plan_path):
        sys.stderr.write(f"No fetch-plan.json in {args.dir}. Run the plan command first.\n")
        return 2
    with open(plan_path, encoding="utf-8") as fh:
        plan = json.load(fh)

    stored, missing, broken = 0, [], []
    for entry in plan:
        path = os.path.join(args.dir, entry["save_as"])
        if not os.path.exists(path):
            missing.append(entry["save_as"])
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                payload = json.load(fh)
        except (ValueError, OSError) as exc:
            broken.append(f"{entry['save_as']} ({exc})")
            continue
        wm_api.cache_store(entry["url"], payload)
        stored += 1

    print(f"ingested {stored} of {len(plan)} planned response(s)")
    for name in missing:
        print(f"  still missing: {name}")
    for name in broken:
        print(f"  not valid JSON: {name}")
    if broken:
        print("Save the raw response body exactly as returned, with no surrounding text.")
    return 0 if stored and not broken else 2


def cmd_cache(args) -> int:
    if args.clear:
        print(f"cleared {wm_api.cache_clear()} cached responses")
    stats_info = wm_api.cache_stats()
    print(f"cache dir={stats_info['dir']} entries={stats_info['entries']} "
          f"size={stats_info['bytes'] / 1024:.0f}KB ttl={wm_api.CACHE_TTL_SECONDS // 3600}h")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wikitrends",
        description="Analyse Wikipedia reading interest by topic and language edition.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  wikitrends.py analyze --topic astronomy --langs uk --months 36\n"
            "  wikitrends.py analyze --topic 'intermittent fasting' --langs pl,cs --months 24\n"
            "  wikitrends.py analyze --topic 'English language' --langs uk,pl,cs,de --normalise\n"
            "  wikitrends.py resolve --topic 'machine learning' --langs uk,pl,cs\n"
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("analyze", help="full pipeline: resolve, fetch, analyse, chart, PDF")
    run.add_argument("--topic", action="append", help="topic phrase; repeat to compare topics")
    run.add_argument("--langs", help="comma-separated language codes, e.g. uk,pl,cs")
    run.add_argument("--articles", help="explicit titles, e.g. 'uk:Астрономія,pl:Astronomia'")
    run.add_argument("--months", type=int, default=DEFAULT_MONTHS,
                     help=f"months of history, ending last complete month (default {DEFAULT_MONTHS})")
    run.add_argument("--since", help="start month YYYY-MM (overrides --months)")
    run.add_argument("--until", help="end month YYYY-MM")
    run.add_argument("--pivot", default="en", help="language used to identify the concept (default en)")
    run.add_argument("--granularity", default="monthly", choices=["monthly", "daily"])
    run.add_argument("--agent", default="user", choices=["user", "all-agents", "spider"],
                     help="'user' excludes bots (default and recommended)")
    run.add_argument("--out-dir", default="wikitrends-out", help="where files are written")
    run.add_argument("--slug", help="base filename")
    run.add_argument("--title", help="PDF title")
    run.add_argument("--question", default="", help="the user's question, printed on the PDF")
    run.add_argument("--finding", action="append",
                     help="your own finding line for the PDF; repeat. Overrides auto findings.")
    run.add_argument("--weights",
                     help="priority weights, e.g. 'momentum=2' (keys: reach, intensity, momentum; default 1 each)")
    run.add_argument("--report-lang", default="auto",
                     help=f"language of the PDF memo: auto (from --question, default) or one of {', '.join(i18n.SUPPORTED)}")
    run.add_argument("--summary",
                     help="your one- or two-sentence bottom line for the PDF's decision box (claim-checked)")
    run.add_argument("--allow-unchecked", action="store_true",
                     help="build the PDF even if a --finding number matches no computed figure")
    run.add_argument("--normalise", action="store_true",
                     help="plot views per million edition views (fair across edition sizes)")
    run.add_argument("--offline", action="store_true",
                     help="use only cached data, never the network (see the plan command)")
    run.add_argument("--pdf", action="store_true",
                     help="also write the one-page PDF (off by default; offer it after the in-chat report)")
    run.add_argument("--no-pdf", action="store_true", help="deprecated: PDF is already off unless --pdf is set")
    run.add_argument("--brief", action="store_true", help="shortest possible stdout")
    run.add_argument("--json", action="store_true", help="print full JSON instead of the digest")
    run.set_defaults(func=cmd_analyze)

    plan = sub.add_parser(
        "plan", help="list URLs still needed (for sandboxes with no network access)")
    for name, kwargs in (
        ("--topic", {"action": "append"}), ("--langs", {}), ("--articles", {}),
        ("--months", {"type": int, "default": DEFAULT_MONTHS}),
        ("--since", {}), ("--until", {}), ("--pivot", {"default": "en"}),
        ("--granularity", {"default": "monthly", "choices": ["monthly", "daily"]}),
        ("--agent", {"default": "user", "choices": ["user", "all-agents", "spider"]}),
        ("--out-dir", {"default": "wikitrends-fetch"}),
    ):
        plan.add_argument(name, **kwargs)
    plan.set_defaults(func=cmd_plan)

    ingest = sub.add_parser("ingest", help="load responses fetched elsewhere into the cache")
    ingest.add_argument("--dir", default="wikitrends-fetch",
                        help="directory holding fetch-plan.json and the saved responses")
    ingest.set_defaults(func=cmd_ingest)

    res = sub.add_parser("resolve", help="topic phrase -> article title per language")
    res.add_argument("--topic", action="append", required=True)
    res.add_argument("--langs", required=True)
    res.add_argument("--pivot", default="en")
    res.add_argument("--json", action="store_true")
    res.set_defaults(func=cmd_resolve)

    chk = sub.add_parser("check", help="verify an answer draft against a saved analysis JSON")
    chk.add_argument("--json", required=True, help="the FILE json path printed by analyze")
    chk.add_argument("--text", help="the draft answer text")
    chk.add_argument("--file", help="or a file containing the draft")
    chk.set_defaults(func=cmd_check)

    hist = sub.add_parser("history", help="list earlier runs recorded in the output directory")
    hist.add_argument("--out-dir", default="wikitrends-out")
    hist.add_argument("--limit", type=int, default=10)
    hist.set_defaults(func=cmd_history)

    cache = sub.add_parser("cache", help="inspect or clear the response cache")
    cache.add_argument("--clear", action="store_true")
    cache.set_defaults(func=cmd_cache)
    return parser


EXIT_CHECK_FAILED = 6
EXIT_SUMMARY_BEFORE_DATA = 7
BLOCKED_MARKERS = ("Network failure", "host_not_allowed", "Tunnel connection failed",
                   "Connection refused", "Name or service not known", "nodename nor servname")
EXIT_NETWORK_BLOCKED = 5


def _looks_blocked(error: str, status: Optional[int] = None) -> bool:
    """True when the failure means 'this sandbox cannot reach Wikimedia', not a bad request."""
    return status in (403, 407) or any(marker in error for marker in BLOCKED_MARKERS)


def _same_args(args, command: str) -> str:
    """Rebuild the user's request as another subcommand, so the agent can copy it verbatim."""
    parts = ["python3 scripts/wikitrends.py", command]
    for topic in getattr(args, "topic", None) or []:
        parts += ["--topic", shlex.quote(topic)]
    if getattr(args, "articles", None):
        parts += ["--articles", shlex.quote(args.articles)]
    if getattr(args, "langs", None):
        parts += ["--langs", shlex.quote(args.langs)]
    if getattr(args, "since", None):
        parts += ["--since", args.since] + (["--until", args.until] if args.until else [])
    elif getattr(args, "months", None):
        parts += ["--months", str(args.months)]
    if getattr(args, "pivot", "en") != "en":
        parts += ["--pivot", args.pivot]
    return " ".join(parts)


def network_blocked_help(args, error: str) -> str:
    """Printed instead of a bare error, so the agent switches to the offline flow
    rather than telling the user the analysis is impossible."""
    plan = _same_args(args, "plan") + " --out-dir fetch"
    analyze = _same_args(args, "analyze") + " --offline"
    return "\n".join([
        "NETWORK_BLOCKED: this environment cannot reach Wikimedia directly.",
        f"  ({error[:160]})",
        "This is expected in sandboxes and is NOT a reason to stop. Do not describe what the",
        "results might be. Continue with the no-network flow now:",
        f"  1. {plan}",
        "  2. Fetch every URL it lists with your own web-fetch tool. Save each response body,",
        "     raw and unmodified, into fetch/ under the filename it gives.",
        "  3. python3 scripts/wikitrends.py ingest --dir fetch",
        "  4. Repeat 1-3 until plan prints READY, then run:",
        f"     {analyze}",
        "If you have no web-fetch tool either, tell the user to allow wikimedia.org,",
        "wikipedia.org and www.wikidata.org in the code-execution network settings.",
    ])


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except ApiError as exc:
        if _looks_blocked(str(exc), exc.status) and args.func in (cmd_analyze, cmd_resolve):
            print(network_blocked_help(args, str(exc)))
            return EXIT_NETWORK_BLOCKED
        sys.stderr.write(f"Wikimedia API error: {exc}\n")
        return 4


if __name__ == "__main__":
    sys.exit(main())
