#!/usr/bin/env python3
"""Score an agent's reply against the report it was based on.

    python evals/check_reply.py reply.txt --report <report folder>

Checks (all must pass, exit code 0; otherwise 1):
  recommendation_first  the recommendation (heading or its headline) comes before the KPI breakdown
  kpi_breakdown         at least 6 of the 8 KPIs are named
  pdf_offer_last        the last line offers a PDF
  no_verdict            no go/no-go or pick-a-winner wording
  no_causes             no guessed causes for changes
  numbers_grounded      every percentage and every number of 4+ digits in the reply is in report.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

KPI_LABELS = {
    "en": ["Demand", "year over year", "CAGR", "Momentum", "Season", "Localization", "Anomal", "Data quality"],
    "uk": ["Попит", "рік до року", "CAGR", "Динаміка", "Сезонн", "Локалізац", "Аномал", "Якість даних"],
}
REC_HEADINGS = ["recommendation", "рекомендац"]                     # matched case-insensitively
KPI_HEADINGS = ["kpi breakdown", "розбивка за показниками", "розбір kpi", "kpi"]
VERDICTS = ["don't launch", "do not launch", "you should launch", "go ahead and launch", "top pick", "winner",
            "no-go:", "не запускайте", "варто запускати", "найкращий вибір",
            # self-made priority rankings (the tool's own "Low priority on this evidence" is allowed)
            "highest priority", "top priority", "second priority", "secondary priority",
            "найвищий пріоритет", "вторинний пріоритет", "другий пріоритет", "першочерговий пріоритет"]
# Self-made orderings in other words ("в пріоритеті", "recommended research order", "Польща → Туреччина").
RANKING_PATTERNS = [re.compile(p) for p in (
    r"(?:повинн\w*|має|мають) бути в пріоритеті", r"рекомендован\w* послідовн\w*", r"порядок дослідження",
    r"recommended (?:research )?(?:order|sequence)", r"\w+ → \w+ → \w+", r"варто почати з",
    r"should start with", r"почніть з дослідження", r"пріоритет \d", r"priority \d")]
CAUSES = ["caused by", "due to the", "because of the", "is explained by", "спричинен", "через популярність"]
PDF_WORDS = ["pdf"]


def _norm_number(text: str) -> str:
    """'−17,2%' / '-17.2%' / '56 910' / '56,910' -> a comparable form."""
    text = text.replace("−", "-").replace(" ", "").replace(" ", "").replace(" ", "")
    if re.fullmatch(r"-?\d{1,3}(,\d{3})+", text):          # thousands separators
        return text.replace(",", "")
    return text.replace(",", ".")


def numbers(text: str) -> set[str]:
    found = set()
    for m in re.finditer(r"[-−+]?\d[\d   ,.]*\d%|[-−+]?\d%|\d{1,3}(?:[,   ]\d{3})+|\d{4,}", text):
        value = m.group(0).strip()
        norm = _norm_number(value)
        if re.fullmatch(r"(19|20)\d\d", norm):              # years
            continue
        found.add(norm.lstrip("+"))
    return found


def _value(norm: str) -> tuple[float, bool]:
    """A normalized number as (value, is_percent), so 130% and 130.0% compare equal."""
    return round(float(norm.rstrip("%")), 4), norm.endswith("%")


def check(reply: str, report_md: str, lang: str = "en") -> dict[str, dict]:
    results: dict[str, dict] = {}
    low = reply.lower()

    rec_at = min((low.find(h) for h in REC_HEADINGS if h in low), default=-1)
    kpi_at = min((low.find(h) for h in KPI_HEADINGS if h in low), default=-1)
    if kpi_at < 0:        # no heading: the first list item or table row that names a KPI
        offset = 0
        for line in reply.splitlines(keepends=True):
            item = line.lstrip()
            if item[:1] in "-•*|" and any(k.lower() in item.lower() for k in KPI_LABELS["en"] + KPI_LABELS["uk"]):
                kpi_at = offset
                break
            offset += len(line)
    results["recommendation_first"] = {"pass": rec_at >= 0 and (kpi_at < 0 or rec_at < kpi_at),
                                       "detail": f"recommendation at {rec_at}, KPI breakdown at {kpi_at}"}

    named = [k for k in KPI_LABELS.get(lang, KPI_LABELS["en"]) if k.lower() in low]
    results["kpi_breakdown"] = {"pass": len(named) >= 6, "detail": f"{len(named)}/8 KPIs named: {named}"}

    lines = [l.strip() for l in reply.strip().splitlines() if l.strip()]
    last = lines[-1] if lines else ""
    results["pdf_offer_last"] = {"pass": any(w in last.lower() for w in PDF_WORDS) and "?" in last,
                                 "detail": last[:120]}

    verdicts = [v for v in VERDICTS if v in low] + [m.group(0) for r in RANKING_PATTERNS for m in r.finditer(low)]
    results["no_verdict"] = {"pass": not verdicts, "detail": verdicts}
    causes = [c for c in CAUSES if c in low]
    results["no_causes"] = {"pass": not causes, "detail": causes}

    in_report = {_value(n) for n in numbers(report_md)}
    ungrounded = sorted(n for n in numbers(reply) if _value(n) not in in_report)   # "+130%" == "+130.0%"
    results["numbers_grounded"] = {"pass": not ungrounded, "detail": ungrounded[:20]}
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("reply", help="a text file with the agent's reply to the user")
    parser.add_argument("--report", required=True, help="the report folder the reply was based on")
    args = parser.parse_args(argv)
    folder = Path(args.report)
    report_md = (folder / "report.md").read_text("utf-8")
    lang = "en"
    for name in ("analysis.json", "comparison.json", "portfolio.json"):
        if (folder / name).is_file():
            lang = json.loads((folder / name).read_text("utf-8"))["metadata"].get("report_language", "en")
    results = check(Path(args.reply).read_text("utf-8"), report_md, lang)
    for name, r in results.items():
        print(f"{'PASS' if r['pass'] else 'FAIL'}  {name:22} {r['detail']}")
    return 0 if all(r["pass"] for r in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
