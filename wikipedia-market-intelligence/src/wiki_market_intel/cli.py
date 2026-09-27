"""Command line: `wiki-market ...` or `python -m wiki_market_intel ...`.

Exit codes: 0 ok, 1 validation failed, 2 bad input, 3 topic needs review,
4 topic or article not found, 5 API error.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import yaml

from wiki_market_intel.analytics.summary import compact, pct
from wiki_market_intel.config import Settings
from wiki_market_intel.data.cache import JsonFileCache
from wiki_market_intel.errors import AmbiguousTopicError, ApiError, ArticleMissingError, TopicNotFoundError
from wiki_market_intel.analytics.summary import comparison_observations, observations_from_spans
from wiki_market_intel.i18n import SUPPORTED, Translator, resolve_report_language
from wiki_market_intel.reporting import generator, markdown
from wiki_market_intel.service import analyze, build_services, compare_languages, resolve_topic
from wiki_market_intel.validate import find_reports, validate_file


def _load_input(path: str) -> dict:
    """YAML input as in spec §4: topic, language, period (e.g. 3y) or period: {start, end}."""
    data = yaml.safe_load(Path(path).read_text("utf-8")) or {}
    period = data.get("period")
    out = {"topic": data.get("topic"), "language": data.get("language"), "question": data.get("question")}
    if isinstance(period, dict):
        out["start"], out["end"] = str(period.get("start")), str(period.get("end"))
    elif period:
        out["period"] = str(period)
    return out


def cmd_analyze(args: argparse.Namespace, settings: Settings) -> int:
    params = _load_input(args.input) if args.input else {}
    question = args.question or params.get("question")
    wanted, report_lang = resolve_report_language(question, args.report_lang)
    topic = args.topic or params.get("topic")
    language = args.language or params.get("language")
    if not topic or not language:
        print("error: --topic and --language are required (or --input file.yaml)", file=sys.stderr)
        return 2
    services = build_services(settings, use_cache=not args.no_cache)
    try:
        result = analyze(topic, language, args.period or params.get("period", "3y"),
                         start=args.start or params.get("start"), end=args.end or params.get("end"),
                         question=question, report_language=report_lang, services=services)
    except AmbiguousTopicError as exc:
        print(exc.resolution.review_message())
        first = exc.resolution.candidates[0]
        print(f"\nRerun with the exact article title or Wikidata ID, e.g. --topic '{first.title}'"
              + (f" or --topic {first.wikidata_id}" if first.wikidata_id else "") + ".")
        return 3
    except (TopicNotFoundError, ArticleMissingError) as exc:
        print(f"Not found: {exc}")
        for note in exc.resolution.notes:
            print(f"  - {note}")
        return 4
    except ApiError as exc:
        print(f"API error: {exc} ({exc.url})", file=sys.stderr)
        return 5
    finally:
        services.http.close()

    files = generator.write(result, settings.reports_dir)
    if args.json:
        print(result.model_dump_json(indent=2))
        return 0
    d, g, q = result.demand, result.growth, result.quality
    print(f"{result.topic.canonical_name} | {result.metadata.project} '{result.topic.article_title}' | "
          f"{result.metadata.period_start}..{result.metadata.period_end}")
    print(f"  annual views {compact(d.annual_views)} | YoY {pct(g.yoy)} | 3Y CAGR {pct(g.three_year_cagr)} | "
          f"3M {pct(g.last_three_month_growth)} ({g.momentum or 'n/a'}) | quality {q.quality_level}")
    for observation in result.observations:
        print(f"  - {observation}")
    if report_lang != "en":
        print(f"REPORT_LANGUAGE {report_lang}: report.md and the chart are in this language. "
              f"Reply to the user in it too. The same observations in {report_lang}:")
        tr = Translator(report_lang)
        for observation in observations_from_spans(result.demand, result.growth, result.seasonality,
                                                   markdown._spans(result), tr):
            print(f"  - {observation}")
    elif wanted != "en":
        print(f"REPORT_LANGUAGE en: the user wrote in '{wanted}', which has no report translation yet "
              f"(available: {', '.join(SUPPORTED)}). Tell the user the report is in English, "
              f"and reply to them in their language.")
    print(f"Wrote {files.json}\n      {files.markdown}" + (f"\n      {files.chart}" if files.chart else ""))
    return 0


def cmd_compare(args: argparse.Namespace, settings: Settings) -> int:
    languages = [l.strip() for l in (args.languages or "").split(",") if l.strip()]
    wanted, report_lang = resolve_report_language(args.question, args.report_lang)
    services = build_services(settings, use_cache=not args.no_cache)
    try:
        result = compare_languages(args.topic, languages, args.period or "3y", start=args.start, end=args.end,
                                   question=args.question, report_language=report_lang, services=services)
    except AmbiguousTopicError as exc:
        print(exc.resolution.review_message())
        first = exc.resolution.candidates[0]
        print(f"\nRerun with the exact article title or Wikidata ID, e.g. --topic '{first.title}'"
              + (f" or --topic {first.wikidata_id}" if first.wikidata_id else "") + ".")
        return 3
    except TopicNotFoundError as exc:
        print(f"Not found: {exc}")
        return 4
    except ApiError as exc:
        print(f"API error: {exc} ({exc.url})", file=sys.stderr)
        return 5
    finally:
        services.http.close()

    files = generator.write_comparison(result, settings.reports_dir)
    if args.json:
        print(result.model_dump_json(indent=2))
        return 0
    print(f"{result.resolution.canonical_topic} ({result.resolution.wikidata_id}) | "
          f"{result.metadata.period_start}..{result.metadata.period_end}")
    print(f"  {'edition':<14}{'views 12M':>10}{'YoY':>9}{'share':>8}{'pen./M':>9}{'affinity':>10}  quadrant")
    for r in result.rows:
        if r.status != "ok":
            print(f"  {r.project:<14}{r.status.replace('_', ' '):>10}")
            continue
        print(f"  {r.project:<14}{compact(r.annual_views):>10}{pct(r.yoy_growth):>9}"
              f"{pct(r.topic_share, False):>8}"
              f"{(f'{r.topic_penetration * 1e6:.1f}' if r.topic_penetration is not None else 'n/a'):>9}"
              f"{(f'{r.topic_affinity:.2f}' if r.topic_affinity is not None else 'n/a'):>10}  {r.quadrant or 'n/a'}")
    for observation in result.observations:
        print(f"  - {observation}")
    for note in result.notes:
        print(f"  NOTE {note}")
    if report_lang != "en":
        print(f"REPORT_LANGUAGE {report_lang}: report.md and the charts are in this language. "
              f"Reply to the user in it too. The same observations in {report_lang}:")
        for observation in comparison_observations(result.rows, Translator(report_lang)):
            print(f"  - {observation}")
    elif wanted != "en":
        print(f"REPORT_LANGUAGE en: the user wrote in '{wanted}', which has no report translation yet "
              f"(available: {', '.join(SUPPORTED)}). Tell the user the report is in English, "
              f"and reply to them in their language.")
    print(f"Wrote {files.json}\n      {files.markdown}" + "".join(f"\n      {c}" for c in files.charts))
    return 0


def cmd_topic(args: argparse.Namespace, settings: Settings) -> int:
    languages = [l.strip() for l in (args.languages or "en").split(",") if l.strip()]
    services = build_services(settings)
    try:
        resolution = resolve_topic(args.topic, languages, services)
    except ApiError as exc:
        print(f"API error: {exc}", file=sys.stderr)
        return 5
    finally:
        services.http.close()
    if resolution.status == "needs_review":
        print(resolution.review_message())
        return 3
    print(json.dumps(resolution.model_dump(), ensure_ascii=False, indent=2))
    return 0 if resolution.status == "resolved" else 4


def cmd_cache(args: argparse.Namespace, settings: Settings) -> int:
    removed = JsonFileCache(settings.cache_dir).clear()
    print(f"Cleared {removed} cached response(s) from {settings.cache_dir}. Raw responses in "
          f"{settings.raw_dir} are kept.")
    return 0


def cmd_validate(args: argparse.Namespace, settings: Settings) -> int:
    paths = find_reports(Path(args.path or settings.reports_dir))
    if not paths:
        print("No analysis.json files found.")
        return 1
    failed = 0
    for path in paths:
        problems = validate_file(path)
        print(f"{'OK  ' if not problems else 'FAIL'} {path}")
        for problem in problems:
            print(f"     {problem}")
        failed += bool(problems)
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wiki-market", description="Wikipedia market-intelligence engine")
    parser.add_argument("-v", "--verbose", action="store_true", help="log every HTTP request")
    sub = parser.add_subparsers(dest="command", required=True)

    a = sub.add_parser("analyze", help="one topic in one language edition")
    a.add_argument("--topic")
    a.add_argument("--language")
    a.add_argument("--period", help="e.g. 3y, 18m (default 3y), ending at the last complete month")
    a.add_argument("--start", help="YYYY-MM or YYYY-MM-DD (instead of --period)")
    a.add_argument("--end", help="YYYY-MM (inclusive) or YYYY-MM-DD (exclusive if the 1st)")
    a.add_argument("--input", help="YAML file with topic, language, period and optionally question")
    a.add_argument("--question", help="the user's request in their own words; the report is written in its language")
    a.add_argument("--report-lang", default="auto",
                   help=f"report language: auto (from --question, default) or one of {', '.join(SUPPORTED)}")
    a.add_argument("--no-cache", action="store_true", help="ignore cached responses")
    a.add_argument("--json", action="store_true", help="print the full JSON result")
    a.set_defaults(func=cmd_analyze)

    cp = sub.add_parser("compare", help="one topic across several language editions")
    cp.add_argument("--topic", required=True)
    cp.add_argument("--languages", required=True, help="comma-separated edition codes, e.g. en,de,fr,es,it")
    cp.add_argument("--period", help="e.g. 3y, 18m (default 3y)")
    cp.add_argument("--start", help="YYYY-MM or YYYY-MM-DD (instead of --period)")
    cp.add_argument("--end", help="YYYY-MM (inclusive) or YYYY-MM-DD (exclusive if the 1st)")
    cp.add_argument("--question", help="the user's request in their own words; the report is written in its language")
    cp.add_argument("--report-lang", default="auto", help=f"auto (default) or one of {', '.join(SUPPORTED)}")
    cp.add_argument("--no-cache", action="store_true")
    cp.add_argument("--json", action="store_true")
    cp.set_defaults(func=cmd_compare)

    t = sub.add_parser("topic", help="resolve a topic to Wikipedia articles, without fetching pageviews")
    t.add_argument("--topic", required=True)
    t.add_argument("--languages", help="comma-separated, e.g. en,de,fr")
    t.set_defaults(func=cmd_topic)

    c = sub.add_parser("cache", help="manage the response cache")
    c.add_argument("action", choices=["clear"])
    c.set_defaults(func=cmd_cache)

    v = sub.add_parser("validate", help="check saved analysis.json / comparison.json: schema and recomputed KPIs")
    v.add_argument("path", nargs="?", help="a file or directory (default: the reports directory)")
    v.set_defaults(func=cmd_validate)
    return parser


def main(argv: list[str] | None = None, settings: Settings | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(message)s")
    try:
        return args.func(args, settings or Settings())
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
