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

from wiki_market_intel.analytics import portfolio as portfolio_kpis
from wiki_market_intel.analytics import recommend
from wiki_market_intel.analytics import signals as signal_kpis
from wiki_market_intel.analytics.summary import compact, pct
from wiki_market_intel.config import Settings
from wiki_market_intel.data.cache import JsonFileCache
from wiki_market_intel.errors import AmbiguousTopicError, ApiError, ArticleMissingError, TopicNotFoundError
from wiki_market_intel.analytics.summary import comparison_observations, observations_from_spans
from wiki_market_intel.i18n import SUPPORTED, Translator, resolve_report_language
from wiki_market_intel.reporting import breakdown, generator, markdown
from wiki_market_intel.service import (
    analyze, analyze_cluster, build_services, compare_languages, portfolio, resolve_topic,
)
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


def cmd_cluster(args: argparse.Namespace, settings: Settings) -> int:
    args.cluster = True
    return cmd_analyze(args, settings)


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
        run = analyze_cluster if getattr(args, "cluster", False) else analyze
        extra = {"max_related": args.max_related} if getattr(args, "cluster", False) else {}
        result = run(topic, language, args.period or params.get("period", "3y"),
                         start=args.start or params.get("start"), end=args.end or params.get("end"),
                         question=question, report_language=report_lang, services=services, **extra)
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
    print(f"{result.topic.canonical_name} | {result.metadata.project} '{result.topic.article_title}' | "
          f"{result.metadata.period_start}..{result.metadata.period_end}")
    _decision_request(question)
    _answer_blocks(result.recommendation, _analysis_kpi_lines(result, Translator("en")))
    print("  OBSERVATIONS:")
    for observation in result.observations:
        print(f"  - {observation}")
    if result.ecosystem.computed:
        eco = result.ecosystem
        c = eco.concentration
        print(f"  RELATED: {len(eco.related_topics)} topics measured. The whole {result.metadata.project} changed "
              f"{pct(eco.edition_yoy)} year over year. Concentration (topic + typed relations, {c.articles} "
              f"articles): the largest article, {c.largest}, holds {pct(c.top_1, False)}; the top 5 hold "
              f"{pct(c.top_5, False)}.")
        from wiki_market_intel.analytics.ecosystem import quote_ready
        print("  RELATED TOPICS BY SIGNAL (part 3 of your reply, after the KPI breakdown: give these sentences as "
              "written, translated if needed; groups are descriptive):")
        for line in quote_ready(eco.related_topics, eco.edition_yoy, result.metadata.project):
            print(f"    {line}")
        print("  DETAIL TABLE. Signals are adjacent interest signals (descriptive), not ranked opportunities. "
              "* = found by text similarity only, not a stated relationship.")
        for x in eco.related_topics:
            size = f"{x.relative_size:.2f}x" if x.relative_size is not None else "n/a"
            if x.share_adjusted_yoy is None:
                versus = "no comparison with the edition"
            else:
                side = "better" if x.share_adjusted_yoy > 0 else "worse"
                versus = f"{side} than its edition by {abs(x.share_adjusted_yoy) * 100:.1f}%"
            mark = "*" if x.relationship == "similar_content" else " "
            print(f"    {mark}{x.title[:34]:34} {x.relationship:15} {compact(x.annual_views):>7} ({size:>6} the topic) "
                  f"YoY {pct(x.yoy_growth):>7}, {versus}; signal: {x.signal or 'n/a'}")
    for a in result.anomalies:
        print(f"  ANOMALY {a.date}: {a.actual:,} views vs {a.expected:,} expected ({pct(a.change_vs_baseline)}, "
              f"{a.severity}{', provisional' if a.provisional else ''}); cause unknown")
    if report_lang != "en":
        print(f"REPORT_LANGUAGE {report_lang}: report.md and the chart are in this language. "
              f"Reply to the user in it too. The same observations in {report_lang}:")
        tr = Translator(report_lang)
        for observation in observations_from_spans(result.demand, result.growth, result.seasonality,
                                                   markdown._spans(result), tr):
            print(f"  - {observation}")
        _answer_blocks(result.recommendation, _analysis_kpi_lines(result, tr), tr)
    elif wanted != "en":
        print(f"REPORT_LANGUAGE en: the user wrote in '{wanted}', which has no report translation yet "
              f"(available: {', '.join(SUPPORTED)}). Tell the user the report is in English, "
              f"and reply to them in their language.")
    print(f"Wrote {files.json}\n      {files.markdown}\n      {files.html}" + (f"\n      {files.chart}" if files.chart else "")
          + (f"\n      {files.eco_chart}" if files.eco_chart else ""))
    _pdf_offer(files.directory)
    return 0


def _plain(text: str) -> str:
    return text.replace("**", "")


def _answer_blocks(rec, kpi_lines: list[str], tr=None) -> None:
    """RECOMMENDATION then KPI BREAKDOWN: the first two parts of the agent's reply."""
    tr = tr or Translator("en")
    head = "" if tr.lang == "en" else f" in {tr.lang}"
    print(f"  RECOMMENDATION{head} (part 1 of your reply: give it first, as written, translated if needed; "
          f"evidence-based next steps, not a go/no-go):")
    for line in recommend.sentences(rec, tr):
        print(f"    {line}")
    print(f"  KPI BREAKDOWN{head} (part 2 of your reply: one item per KPI, as written):")
    for line in kpi_lines:
        print(f"    - {_plain(line)}")


def _analysis_kpi_lines(result, tr) -> list[str]:
    reasons = {m.metric: m for m in result.quality.missing_metrics}

    def missing(metric: str) -> str:
        m = reasons.get(metric)
        return tr("sig_missing", reason=m.reason.rstrip(".")) if m else tr("na")

    q = result.quality.quality_reasons if tr.lang == "en" else markdown._quality_reasons(result, tr)
    return [f"{kpi}: {value}. {reading}".rstrip(". ") + "." if reading else f"{kpi}: {value}."
            for kpi, value, reading in breakdown.analysis_rows(result, tr, missing, q)]


def _decision_request(question: str | None) -> None:
    """A question that asks the data to decide ("should we launch", "top 3", "best") gets an opener."""
    phrase = portfolio_kpis.ranking_phrase(question)
    if phrase:
        print(f"  DECISION REQUEST: the user asked {phrase}. Start your reply with this sentence (translated if "
              f"needed), then give the RECOMMENDATION and the KPI BREAKDOWN. Write no verdict of your own:")
        print(f"    {portfolio_kpis.RANKING_OPENER.format(phrase=phrase)}")


def _pdf_offer(folder) -> None:
    print(f"PDF_OFFER folder: {folder}  (if the user says yes, run the pdf command on this folder)")
    print("REPLY CHECKLIST, in this order:")
    print("  1. RECOMMENDATION, as written (after the DECISION REQUEST sentence, if one was printed)")
    print("  2. KPI BREAKDOWN, one item per KPI")
    print("  3. details the user asked for, the limits, and where the report files are")
    print("  4. END YOUR REPLY WITH THIS QUESTION (translated if needed): "
          "\"Would you like this report as a PDF? I can create it for you.\"")


def _print_signals(result) -> None:
    sig = result.signals
    print("  SIGNALS (five separate readings; never combined into a score or a buy/invest verdict):")
    for name in signal_kpis.SIGNAL_NAMES:
        label = getattr(sig, name)
        if label:
            print(f"    {name.replace('_', ' ')}: {label.replace('_', ' ')}. {sig.evidence.get(name, '')}".rstrip())
        else:
            reason = next((m.reason for m in result.quality.missing_metrics if m.metric == f"signals.{name}"), "")
            print(f"    {name.replace('_', ' ')}: n/a. {reason}".rstrip())


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
    _decision_request(args.question)
    _answer_blocks(result.recommendation, breakdown.multi_lines(breakdown.comparison_units(result), Translator("en")))
    print("  DETAIL TABLE:")
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
    print("  SIGNALS per edition (use these labels as written; they are separate readings, not a score):")
    print(f"    {signal_kpis.NO_VERDICT}")
    for analysis in result.analyses.values():
        print(f"    - {signal_kpis.brief(analysis)}")
    for note in result.notes:
        print(f"  NOTE {note}")
    if report_lang != "en":
        print(f"REPORT_LANGUAGE {report_lang}: report.md and the charts are in this language. "
              f"Reply to the user in it too. The same observations in {report_lang}:")
        for observation in comparison_observations(result.rows, Translator(report_lang)):
            print(f"  - {observation}")
        _answer_blocks(result.recommendation,
                       breakdown.multi_lines(breakdown.comparison_units(result), Translator(report_lang)),
                       Translator(report_lang))
    elif wanted != "en":
        print(f"REPORT_LANGUAGE en: the user wrote in '{wanted}', which has no report translation yet "
              f"(available: {', '.join(SUPPORTED)}). Tell the user the report is in English, "
              f"and reply to them in their language.")
    print(f"Wrote {files.json}\n      {files.markdown}\n      {files.html}" + "".join(f"\n      {c}" for c in files.charts))
    _pdf_offer(files.directory)
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


def _list_arg(value: str | None, key: str) -> list:
    """A comma list, or a YAML file holding a list or {key: [...]} (spec §36: topics.yaml, languages.yaml)."""
    if not value:
        return []
    path = Path(value)
    if value.endswith((".yaml", ".yml")) or path.is_file():
        data = yaml.safe_load(path.read_text("utf-8"))
        items = data.get(key, []) if isinstance(data, dict) else data
        if not isinstance(items, list):
            raise ValueError(f"{value}: expected a list of {key}, or '{key}:' with a list")
        return items
    return [v.strip() for v in value.split(",") if v.strip()]


def _percent(value: str | None) -> float | None:
    """'5', '5%' or '-10%' -> 0.05 / -0.10."""
    if value is None:
        return None
    return float(value.strip().rstrip("%")) / 100


def cmd_portfolio(args: argparse.Namespace, settings: Settings) -> int:
    topics = _list_arg(args.topics, "topics")
    languages = [str(l) for l in _list_arg(args.languages, "languages")]
    categories = [c.strip() for c in (args.category or "").split(",") if c.strip()]
    wanted, report_lang = resolve_report_language(args.question, args.report_lang)
    services = build_services(settings, use_cache=not args.no_cache)
    try:
        result = portfolio(topics, languages, args.period or "3y", start=args.start, end=args.end,
                           question=args.question, report_language=report_lang, min_views=args.min_views,
                           min_growth=_percent(args.min_growth), categories=categories, name=args.name,
                           services=services)
    finally:
        services.http.close()
    files = generator.write_portfolio(result, settings.reports_dir)
    if args.json:
        print(result.model_dump_json(indent=2))
        return 0
    print(f"Portfolio '{result.metadata.name}' | {len(result.metadata.topics)} topics x "
          f"{len(result.metadata.languages)} editions | {result.metadata.period_start}..{result.metadata.period_end}")
    _decision_request(args.question)
    _answer_blocks(result.recommendation, breakdown.multi_lines(breakdown.portfolio_units(result), Translator("en")))
    print("  DETAIL TABLE:")
    print(f"  {'topic':<22}{'edition':<15}{'views 12M':>10}{'YoY':>9}{'3M':>9}  {'momentum':<13}{'affinity':>9}  quadrant")
    for r in result.visible:
        print(f"  {(r.canonical_topic or r.topic)[:21]:<22}{r.project:<15}{compact(r.annual_views):>10}"
              f"{pct(r.yoy_growth):>9}{pct(r.three_month_growth):>9}  {(r.momentum or 'n/a'):<13}"
              f"{(f'{r.topic_affinity:.2f}' if r.topic_affinity is not None else 'n/a'):>9}  {r.quadrant or 'n/a'}")
    hidden = [r for r in result.rows if r.excluded_by]
    if hidden:
        print(f"  HIDDEN ({len(hidden)} rows, kept in portfolio.json): " + "; ".join(
            f"{r.topic} {r.language}: {r.excluded_by}" + (f" ({r.reason})" if r.reason else "") for r in hidden))
    if result.demand_threshold is not None:
        print(f"  Quadrant split: YoY > 0%; demand >= the median of all measured pairs "
              f"({result.demand_threshold:,.0f} views, before filters).")
    for observation in result.observations:
        print(f"  - {observation}")
    print("  QUADRANTS (descriptive groups, for reference; the RECOMMENDATION above sets what to validate first):")
    for line in portfolio_kpis.ready_answer(result.rows):
        print(f"    {line}")
    for note in result.notes:
        print(f"  NOTE {note}")
    if report_lang != "en":
        print(f"REPORT_LANGUAGE {report_lang}: report.md, report.html and the chart are in this language. "
              f"Reply to the user in it too. The same observations in {report_lang}:")
        for observation in portfolio_kpis.observations(result.rows, Translator(report_lang)):
            print(f"  - {observation}")
        _answer_blocks(result.recommendation,
                       breakdown.multi_lines(breakdown.portfolio_units(result), Translator(report_lang)),
                       Translator(report_lang))
    elif wanted != "en":
        print(f"REPORT_LANGUAGE en: the user wrote in '{wanted}', which has no report translation yet "
              f"(available: {', '.join(SUPPORTED)}). Tell the user the report is in English, "
              f"and reply to them in their language.")
    print(f"Wrote {files.json}\n      {files.markdown}\n      {files.html}" + "".join(f"\n      {c}" for c in files.charts))
    _pdf_offer(files.directory)
    return 0


def cmd_pdf(args: argparse.Namespace, settings: Settings) -> int:
    """report folder / report.md / result JSON -> report.pdf next to report.md."""
    path = Path(args.path)
    folder = path if path.is_dir() else path.parent
    md = folder / "report.md"
    if not md.is_file():
        print(f"error: no report.md in {folder}", file=sys.stderr)
        return 2
    lang = "en"
    for name in ("analysis.json", "comparison.json", "portfolio.json"):
        if (folder / name).is_file():
            lang = json.loads((folder / name).read_text("utf-8")).get("metadata", {}).get("report_language", "en")
            break
    try:
        from wiki_market_intel.reporting import pdf
        out = pdf.write(md, lang)
    except ImportError:
        print("error: PDF output needs the reportlab library: pip install reportlab", file=sys.stderr)
        return 2
    print(f"Wrote {out}")
    return 0


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

    cl = sub.add_parser("cluster", help="analyze plus the topic ecosystem: related topics and concentration")
    for flag in ("--topic", "--language", "--question", "--period", "--start", "--end", "--input"):
        cl.add_argument(flag)
    cl.add_argument("--report-lang", default="auto")
    cl.add_argument("--max-related", type=int, default=20, help="how many related concepts to measure (default 20)")
    cl.add_argument("--no-cache", action="store_true")
    cl.add_argument("--json", action="store_true")
    cl.set_defaults(func=cmd_cluster)

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

    pf = sub.add_parser("portfolio", help="many topics x many language editions: matrix, chart, signals")
    pf.add_argument("--topics", required=True,
                    help="comma-separated topics, or a YAML file: a list, or 'topics:' with items "
                         "'name' or {topic: name, category: label}")
    pf.add_argument("--languages", required=True, help="comma-separated edition codes, or a YAML file (a list)")
    pf.add_argument("--name", help="portfolio name, used for the report folder (default: portfolio)")
    pf.add_argument("--period", help="e.g. 3y, 18m (default 3y)")
    pf.add_argument("--start")
    pf.add_argument("--end")
    pf.add_argument("--min-views", type=int, help="hide pairs with fewer views in the last 12 months")
    pf.add_argument("--min-growth", help="hide pairs with lower YoY, in percent: 5 or -10 "
                                         "(with a %% sign, write --min-growth=-10%%)")
    pf.add_argument("--category", help="show only these categories (comma-separated, from the topics file)")
    pf.add_argument("--question", help="the user's request in their own words; the report is written in its language")
    pf.add_argument("--report-lang", default="auto", help=f"auto (default) or one of {', '.join(SUPPORTED)}")
    pf.add_argument("--no-cache", action="store_true")
    pf.add_argument("--json", action="store_true")
    pf.set_defaults(func=cmd_portfolio)

    t = sub.add_parser("topic", help="resolve a topic to Wikipedia articles, without fetching pageviews")
    t.add_argument("--topic", required=True)
    t.add_argument("--languages", help="comma-separated, e.g. en,de,fr")
    t.set_defaults(func=cmd_topic)

    c = sub.add_parser("cache", help="manage the response cache")
    c.add_argument("action", choices=["clear"])
    c.set_defaults(func=cmd_cache)

    pd = sub.add_parser("pdf", help="turn a saved report into report.pdf (A4, charts included)")
    pd.add_argument("path", help="a report folder, its report.md, or its analysis/comparison/portfolio JSON")
    pd.set_defaults(func=cmd_pdf)

    v = sub.add_parser("validate", help="check saved analysis.json / comparison.json / portfolio.json: schema "
                                        "and recomputed KPIs")
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
