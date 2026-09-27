#!/usr/bin/env python3
"""
End-to-end tests for the CLI with the network stubbed out.

These cover the wiring that unit tests miss - resolution, label building, the
stdout digest, CSV/JSON output and the PDF - and they are deterministic, so they
work offline and in CI.
"""

import csv
import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import wikitrends  # noqa: E402
import wm_api  # noqa: E402


# --------------------------------------------------------------------------
# a fake Wikimedia, driven off the request URL
# --------------------------------------------------------------------------

EDITION_TOTALS = {"uk": 80_000_000, "pl": 200_000_000}
# uk holds its share; pl loses share. Both fall in raw terms.
SHAPES = {"uk": lambda i: 1000, "pl": lambda i: int(1500 * (0.97 ** i))}
MONTHS = 30


def _months(count):
    out, year, month = [], 2024, 1
    for _ in range(count):
        out.append((year, month))
        month += 1
        if month == 13:
            year, month = year + 1, 1
    return out


def fake_get_json(url, user_agent=None):
    """Enough of the API surface to exercise the whole pipeline."""
    if "wbgetentities" in url:
        return 200, {"entities": {"Q333": {"sitelinks": {
            "ukwiki": {"site": "ukwiki", "title": "Астрономія"},
            "plwiki": {"site": "plwiki", "title": "Astronomia"},
        }}}}
    if "action=query" in url and "titles=" in url:
        return 200, {"query": {"pages": [{
            "title": "Astronomy", "pageprops": {
                "wikibase_item": "Q333", "wikibase-shortdesc": "Study of the sky"}}]}}
    if "generator=search" in url:
        # The search fallback, used when an exact title match misses.
        return 200, {"query": {"pages": [
            {"title": "Astronomy", "index": 1,
             "pageprops": {"wikibase_item": "Q333", "wikibase-shortdesc": "Study of the sky"}},
            {"title": "Astronomer", "index": 2,
             "pageprops": {"wikibase_item": "Q11063", "wikibase-shortdesc": "Scientist"}},
        ]}}
    if "/aggregate/" in url:
        lang = url.split("/aggregate/")[1].split(".wikipedia")[0]
        if lang not in EDITION_TOTALS:
            return 404, {"detail": "project not loaded"}
        items = [{"timestamp": f"{y}{m:02d}0100", "views": EDITION_TOTALS[lang]}
                 for y, m in _months(MONTHS)]
        return 200, {"items": items}
    if "/per-article/" in url:
        lang = url.split("/per-article/")[1].split(".wikipedia")[0]
        if lang not in SHAPES:
            return 404, {"detail": "not found"}
        items = [{"timestamp": f"{y}{m:02d}0100", "views": SHAPES[lang](i)}
                 for i, (y, m) in enumerate(_months(MONTHS))]
        return 200, {"items": items}
    raise AssertionError(f"unexpected URL in test: {url}")


@pytest.fixture(autouse=True)
def stub_network(monkeypatch, tmp_path):
    monkeypatch.setattr(wm_api, "_get_json", fake_get_json)
    monkeypatch.setenv("WIKITRENDS_NO_CACHE", "1")
    monkeypatch.setenv("WIKITRENDS_NO_ASSETS", "1")
    monkeypatch.chdir(tmp_path)


# --------------------------------------------------------------------------
# resolution
# --------------------------------------------------------------------------

def test_resolution_maps_a_topic_to_titles_per_language():
    resolution = wm_api.resolve_topic("astronomy", ["uk", "pl"])
    assert resolution["status"] == "resolved"
    assert resolution["qid"] == "Q333"
    assert resolution["articles"] == {"uk": "Астрономія", "pl": "Astronomia"}
    assert resolution["missing_languages"] == []


def test_language_without_a_sitelink_is_reported_missing_not_guessed():
    resolution = wm_api.resolve_topic("astronomy", ["uk", "cs"])
    assert resolution["missing_languages"] == ["cs"]
    assert "cs" not in resolution["articles"]


def test_missing_language_becomes_a_visible_note_not_a_silent_omission():
    analysis = wikitrends.run_analysis(topics=["astronomy"], langs=["uk", "cs"], months=MONTHS)
    note = next(n for n in analysis["notes"] if n.startswith("cs.wikipedia"))
    assert "never created an article" in note
    # Must be unmistakable that the article is absent, not that the lookup failed.
    assert "not a failed title lookup" in note


# --------------------------------------------------------------------------
# pipeline
# --------------------------------------------------------------------------

def test_run_analysis_produces_one_analysed_series_per_language():
    analysis = wikitrends.run_analysis(topics=["astronomy"], langs=["uk", "pl"], months=MONTHS)
    assert analysis["status"] == "ok"
    assert {r["label"] for r in analysis["series"]} == {"uk: Астрономія", "pl: Astronomia"}
    assert all(r["status"] == "ok" for r in analysis["series"])


def test_share_holding_language_outranks_share_losing_one():
    """uk keeps its share of a flat edition; pl loses share. uk must rank first."""
    analysis = wikitrends.run_analysis(topics=["astronomy"], langs=["uk", "pl"], months=MONTHS)
    ranking = analysis["comparison"]["ranking"]
    assert ranking[0]["label"] == "uk: Астрономія"
    assert ranking[0]["vs_edition"] == "tracking its edition"
    assert ranking[-1]["vs_edition"] == "underperforming its edition"


def test_explicit_articles_skip_resolution_and_use_lang_title_labels():
    analysis = wikitrends.run_analysis(
        topics=[], langs=["uk", "pl"], articles=[("uk", "Астрономія"), ("pl", "Astronomia")],
        months=MONTHS,
    )
    assert analysis["resolutions"] == []
    assert {r["label"] for r in analysis["series"]} == {"uk: Астрономія", "pl: Astronomia"}


def test_one_failing_edition_does_not_sink_the_whole_analysis(monkeypatch):
    """A bad language code should cost you that language, not the whole report."""
    def flaky(url, user_agent=None):
        if "pl.wikipedia" in url:
            raise wm_api.ApiError("HTTP 400 for pl.wikipedia", 400)
        return fake_get_json(url, user_agent)

    monkeypatch.setattr(wm_api, "_get_json", flaky)
    analysis = wikitrends.run_analysis(topics=["astronomy"], langs=["uk", "pl"], months=MONTHS)

    assert analysis["status"] == "ok"
    labels = {r["label"]: r["status"] for r in analysis["series"]}
    assert labels["uk: Астрономія"] == "ok"
    assert labels["pl: Astronomia"] == "no_data"
    assert any("pl.wikipedia" in note for note in analysis["notes"])


def test_multiple_topics_get_topic_tagged_labels():
    analysis = wikitrends.run_analysis(topics=["astronomy", "chemistry"], langs=["uk"], months=MONTHS)
    assert {r["label"] for r in analysis["series"]} == {"astronomy [uk]", "chemistry [uk]"}


# --------------------------------------------------------------------------
# outputs
# --------------------------------------------------------------------------

def test_digest_is_compact_and_carries_the_numbers_that_matter():
    analysis = wikitrends.run_analysis(topics=["astronomy"], langs=["uk", "pl"], months=MONTHS)
    text = wikitrends.digest(analysis, {"pdf": "x.pdf"})

    assert "PERIOD" in text and "TIER" in text and "CAVEAT" in text
    # Each series needs a verdict that can be quoted without cross-referencing
    # another line: fast models running several analyses otherwise swap figures.
    for line in [l for l in text.splitlines() if l.strip().startswith("verdict:")]:
        assert any(word in line for word in ("GAINING GROUND", "HOLDING GROUND", "LOSING GROUND"))
        assert "%" in line
    assert text.count("verdict:") == 2

    # Small models pay for every token: the monthly series belongs in the CSV.
    assert len(text.splitlines()) < 40
    assert "2024-01" not in text


def test_csv_contains_every_monthly_observation():
    analysis = wikitrends.run_analysis(topics=["astronomy"], langs=["uk", "pl"], months=MONTHS)
    files = wikitrends.write_outputs(analysis, "out", "t", "T", "q", make_pdf=False)
    with open(files["csv"], encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 2 * MONTHS
    assert {row["label"] for row in rows} == {"uk: Астрономія", "pl: Astronomia"}


def test_json_output_round_trips():
    analysis = wikitrends.run_analysis(topics=["astronomy"], langs=["uk"], months=MONTHS)
    files = wikitrends.write_outputs(analysis, "out", "t", "T", "q", make_pdf=False)
    with open(files["json"], encoding="utf-8") as fh:
        loaded = json.load(fh)
    assert loaded["series"][0]["label"] == "uk: Астрономія"


def test_no_pdf_needs_no_third_party_libraries():
    """The fetch-and-analyse path must run on a bare Python install."""
    files = wikitrends.write_outputs(
        wikitrends.run_analysis(topics=["astronomy"], langs=["uk"], months=MONTHS),
        "out", "t", "T", "q", make_pdf=False,
    )
    assert "pdf" not in files
    assert set(files) == {"json", "csv", "report"}


def test_auto_findings_always_pair_a_number_with_its_confidence():
    analysis = wikitrends.run_analysis(topics=["astronomy"], langs=["uk", "pl"], months=MONTHS)
    for finding in wikitrends.auto_findings(analysis):
        if finding.startswith(("uk:", "pl:")):
            assert "confidence" in finding


def test_pdf_is_a_single_page():
    analysis = wikitrends.run_analysis(topics=["astronomy"], langs=["uk", "pl"], months=MONTHS)
    files = wikitrends.write_outputs(analysis, "out", "t", "Report", "q", make_pdf=True)
    assert os.path.getsize(files["pdf"]) > 1000
    assert "pdf_pages" not in files  # set only when it could not be compressed to one


def test_analyze_saves_wikipedia_fetch_under_assets(monkeypatch, tmp_path, capsys):
    folder = tmp_path / "assets"
    monkeypatch.delenv("WIKITRENDS_NO_ASSETS", raising=False)
    monkeypatch.setenv("WIKITRENDS_ASSETS_DIR", str(folder))
    code = wikitrends.main([
        "analyze", "--topic", "astronomy", "--langs", "uk",
        "--months", str(MONTHS), "--no-pdf", "--out-dir", "cli-out", "--brief",
    ])
    assert code == 0
    files = list(folder.glob("astronomy_*.json"))
    assert len(files) == 1
    name = files[0].name
    assert name.startswith("astronomy_")
    assert name.endswith(".json")
    saved = json.loads(files[0].read_text(encoding="utf-8"))
    assert saved["topics"] == ["astronomy"]
    assert saved["languages"] == ["uk"]
    assert saved["articles"][0]["title"] == "Астрономія"
    assert saved["articles"][0]["points"]
    assert "uk.wikipedia" in saved["edition_totals"]
    assert "FILE wikipedia_fetch:" in capsys.readouterr().out


def test_analyze_writes_a_reply_report_and_asks_about_pdf(capsys):
    code = wikitrends.main([
        "analyze", "--topic", "astronomy", "--langs", "uk,pl",
        "--months", str(MONTHS), "--out-dir", "reply-out",
    ])
    out = capsys.readouterr().out
    assert code == 0
    assert "BEGIN_REPLY_REPORT" in out and "END_REPLY_REPORT" in out
    assert "ASK_PDF" in out
    assert out.index("END_REPLY_REPORT") < out.index("ASK_PDF")
    assert "Would you also like a one-page PDF of this report?" in out
    assert "FILE report:" in out
    assert "FILE pdf:" not in out
    assert os.path.exists("reply-out/wikitrends-astronomy-uk-pl.md")
    assert not os.path.exists("reply-out/wikitrends-astronomy-uk-pl.pdf")


def test_pdf_flag_writes_the_pdf(capsys):
    code = wikitrends.main([
        "analyze", "--topic", "astronomy", "--langs", "uk",
        "--months", str(MONTHS), "--out-dir", "pdf-out", "--pdf",
    ])
    assert code == 0
    out = capsys.readouterr().out
    assert "FILE pdf:" in out
    assert "ASK_PDF" not in out
    assert os.path.exists("pdf-out/wikitrends-astronomy-uk.pdf")


def test_cli_exits_zero_and_writes_files(capsys):
    code = wikitrends.main([
        "analyze", "--topic", "astronomy", "--langs", "uk,pl",
        "--months", str(MONTHS), "--no-pdf", "--out-dir", "cli-out", "--brief",
    ])
    assert code == 0
    assert "TIER" in capsys.readouterr().out
    assert os.path.isdir("cli-out")


def test_cli_rejects_a_call_with_no_topic_or_articles():
    assert wikitrends.main(["analyze", "--langs", "uk"]) == 2


def test_cli_reports_no_data_with_exit_code_two(capsys):
    code = wikitrends.main([
        "analyze", "--articles", "cs:Nonexistent", "--no-pdf", "--out-dir", "o",
    ])
    assert code == 2
    assert "no usable data" in capsys.readouterr().out


def test_window_flags_override_the_month_count():
    parser = wikitrends.build_parser()
    args = parser.parse_args(["analyze", "--topic", "x", "--langs", "uk",
                              "--since", "2024-01", "--until", "2024-06"])
    start, end, start_month, end_month = wikitrends._window(args)
    assert (start, end) == ("20240101", "20240630")
    assert (start_month, end_month) == ("2024-01", "2024-06")


# --------------------------------------------------------------------------
# regressions from Haiku 4.5 end-to-end runs
# --------------------------------------------------------------------------

def test_every_verdict_carries_the_share_figure_and_every_headline_its_period():
    analysis = wikitrends.run_analysis(topics=["astronomy"], langs=["uk", "pl"], months=MONTHS)
    lines = wikitrends.digest(analysis, {}).splitlines()

    headlines = [l for l in lines if l.startswith("- ") and "raw " in l]
    verdicts = [l for l in lines if l.strip().startswith("verdict:")]
    assert len(headlines) == len(verdicts) == 2
    assert all("year over year" in l for l in headlines)
    # Holding (uk) and losing (pl) verdicts both state the share change.
    assert all("share of edition traffic" in l for l in verdicts)


def test_cli_weights_are_applied_and_printed(capsys):
    code = wikitrends.main([
        "analyze", "--topic", "astronomy", "--langs", "uk,pl", "--months", str(MONTHS),
        "--no-pdf", "--out-dir", "w", "--weights", "momentum=2",
    ])
    out = capsys.readouterr().out
    assert code == 0
    assert "PRIORITY (weights reach=1, intensity=1, momentum=2;" in out
    assert "not a probability" in out
    with open(os.path.join("w", "wikitrends-astronomy-uk-pl.json"), encoding="utf-8") as fh:
        assert json.load(fh)["comparison"]["weights"]["momentum"] == 2


@pytest.mark.parametrize("bad", ["growth=2", "momentum=two", "reach=-1"])
def test_cli_rejects_bad_weights(bad, capsys):
    code = wikitrends.main(["analyze", "--topic", "astronomy", "--langs", "uk",
                            "--no-pdf", "--weights", bad])
    assert code == 2
    assert "--weights" in capsys.readouterr().err


def test_filenames_name_every_language_and_never_collide():
    """Five languages used to be cut to four, so the name hid Indonesian and two runs could collide."""
    assert wikitrends._slug(["English language"], ["uk", "pl", "tr", "vi", "id"]) == \
        "wikitrends-english-language-uk-pl-tr-vi-id"

    many = ["uk", "pl", "cs", "de", "es", "fr", "it", "pt", "tr", "vi", "id", "ja", "ko"]
    long_a = wikitrends._slug(["English language"], many)
    long_b = wikitrends._slug(["English language"], many[:-1] + ["zh"])
    assert len(long_a) <= 70 and len(long_b) <= 70
    assert long_a != long_b


# --------------------------------------------------------------------------
# checking conclusions, stating assumptions, follow-up runs
# --------------------------------------------------------------------------

def _analysis():
    return wikitrends.run_analysis(topics=["astronomy"], langs=["uk", "pl"], months=MONTHS)


def test_digest_states_assumptions_ranges_and_separation():
    analysis = _analysis()
    text = wikitrends.digest(analysis, {})
    assert "ASSUMPTIONS" in text and "Wikidata Q333" in text and "humans only" in text
    assert "90% range: raw" in text
    assert text.count("SEPARATION") == 1


def test_check_accepts_a_faithful_draft():
    analysis = _analysis()
    uk = next(r for r in analysis["series"] if r["lang"] == "uk")
    pl = next(r for r in analysis["series"] if r["lang"] == "pl")
    draft = (f"Ukrainian is HOLDING GROUND, raw {uk['trend']['headline_change_pct']:+.1f}%, "
             f"confidence {uk['quality']['confidence']}/100. "
             f"Polish is LOSING GROUND: share {pl['trend']['relative']['share_change_pct']:+.1f}%.")
    assert wikitrends.check_text(analysis, draft) == []


@pytest.mark.parametrize("draft, expected", [
    ("Polish grows +55%.", "matches no figure for pl"),                   # invented number
    ("Polish is HOLDING GROUND.", "its verdict is LOSING GROUND"),        # wrong verdict, by name
    ("Польська аудиторія: GAINING GROUND.", "its verdict is LOSING GROUND"),  # Ukrainian name
])
def test_check_catches_common_mistakes(draft, expected):
    problems = wikitrends.check_text(_analysis(), draft)
    assert any(expected in p for p in problems), problems


def test_check_does_not_accept_a_number_borrowed_from_another_edition():
    analysis = _analysis()
    pl_share = next(r for r in analysis["series"] if r["lang"] == "pl")["trend"]["relative"]["share_change_pct"]
    problems = wikitrends.check_text(analysis, f"Ukrainian share {pl_share:+.1f}%.")
    assert any("for uk" in p for p in problems)


def test_confidence_written_as_percent_is_flagged():
    analysis = _analysis()
    score = next(r for r in analysis["series"] if r["lang"] == "pl")["quality"]["confidence"]
    problems = wikitrends.check_text(analysis, f"Polish confidence is {score}%.")
    assert any(f"write it as {score}/100" in p for p in problems), problems


def _noisy_analysis():
    """A real-looking series, so the 90% range is wider than a point."""
    import random
    import analyze
    rng = random.Random(4)
    points = [{"month": f"{2024 + (i // 12)}-{i % 12 + 1:02d}", "views": int(1000 * (1.02 ** i) * rng.uniform(0.7, 1.3))}
              for i in range(30)]
    baseline = {p["month"]: 50_000_000 for p in points}
    result = analyze.analyze_series(points, baseline, label="uk: Астрономія")
    result.update(lang="uk", title="Астрономія")
    return {"series": [result]}


def test_check_accepts_range_bounds_only_when_talking_about_a_range():
    analysis = _noisy_analysis()
    trend = analysis["series"][0]["trend"]
    low, high = trend["ci90_pct"]
    assert high - trend["headline_change_pct"] > 5          # the test needs a real range
    assert wikitrends.check_text(analysis, f"Ukrainian raw 90% range {low:+.0f}..{high:+.0f}%.") == []
    assert wikitrends.check_text(analysis, f"Ukrainian grows {high:+.0f}%.") != []


def test_wrong_finding_blocks_the_pdf_but_keeps_the_data(capsys):
    _first_look("f")
    code = wikitrends.main(["analyze", "--topic", "astronomy", "--langs", "uk,pl", "--months", str(MONTHS),
                            "--out-dir", "f", "--finding", "Polish grows +55%."])
    out = capsys.readouterr().out
    assert code == wikitrends.EXIT_CHECK_FAILED
    assert "CHECK_FAILED" in out and "PDF NOT written" in out
    files = os.listdir("f")
    assert not any(name.endswith(".pdf") and os.path.getmtime(os.path.join("f", name)) > STAMP["t"] for name in files)
    assert any(name.endswith(".json") for name in files)


def test_check_command_reads_the_saved_json(capsys):
    wikitrends.main(["analyze", "--topic", "astronomy", "--langs", "uk,pl", "--months", str(MONTHS),
                     "--no-pdf", "--out-dir", "c"])
    capsys.readouterr()
    path = os.path.join("c", "wikitrends-astronomy-uk-pl.json")
    assert wikitrends.main(["check", "--json", path, "--text", "Polish grows +55%."]) == wikitrends.EXIT_CHECK_FAILED
    assert "CHECK_FAILED" in capsys.readouterr().out


def test_rerun_reports_what_changed_and_history_lists_runs(capsys):
    args = ["analyze", "--topic", "astronomy", "--langs", "uk,pl", "--months", str(MONTHS), "--no-pdf", "--out-dir", "h"]
    wikitrends.main(args)
    first = capsys.readouterr().out
    assert "SINCE_LAST_RUN" not in first

    wikitrends.main(args)
    second = capsys.readouterr().out
    assert "SINCE_LAST_RUN" in second and "verdict unchanged" in second

    wikitrends.main(["history", "--out-dir", "h"])
    history = capsys.readouterr().out
    assert history.count("data to") == 2
    assert "LOSING GROUND" in history


def test_pdf_is_a_one_page_decision_memo(capsys):
    """The PDF leads with a recommendation, not a table of numbers."""
    _first_look("m")
    code = wikitrends.main(["analyze", "--topic", "astronomy", "--langs", "uk,pl", "--months", str(MONTHS),
                            "--out-dir", "m", "--pdf", "--summary", "Polish is LOSING GROUND."])
    out = capsys.readouterr().out
    assert code == 0
    assert "RECOMMENDATION" in out
    pdf = os.path.join("m", "wikitrends-astronomy-uk-pl.pdf")
    with open(pdf, "rb") as fh:
        data = fh.read()
    assert data.count(b"/Type /Page\n") + data.count(b"/Type /Page\r") + data.count(b"/Type /Page ") <= 1 or \
        wikitrends.report  # page count is asserted precisely in test_pdf_is_a_single_page
    with open(os.path.join("m", "wikitrends-astronomy-uk-pl.json"), encoding="utf-8") as fh:
        saved = json.load(fh)
    assert saved["decision"]["overall_action"] in decide_actions()


def decide_actions():
    import decide
    return list(decide.ACTIONS)


def test_wrong_summary_blocks_the_memo(capsys):
    _first_look("s")
    code = wikitrends.main(["analyze", "--topic", "astronomy", "--langs", "uk,pl", "--months", str(MONTHS),
                            "--out-dir", "s", "--summary", "Polish is GAINING GROUND."])
    assert code == wikitrends.EXIT_CHECK_FAILED
    assert "PDF NOT written" in capsys.readouterr().out


STAMP = {"t": 0.0}


def _first_look(out_dir):
    """Run the analysis once without a summary, as the agent must before writing one."""
    import time
    wikitrends.main(["analyze", "--topic", "astronomy", "--langs", "uk,pl", "--months", str(MONTHS),
                     "--no-pdf", "--out-dir", out_dir])
    STAMP["t"] = time.time()


def test_summary_before_seeing_the_data_is_refused(capsys):
    """Seen with Haiku: it wrote --summary in the first command, before any results existed."""
    code = wikitrends.main(["analyze", "--topic", "astronomy", "--langs", "uk,pl", "--months", str(MONTHS),
                            "--out-dir", "early", "--summary", "Interest is stable."])
    out = capsys.readouterr().out
    assert code == wikitrends.EXIT_SUMMARY_BEFORE_DATA
    assert "SUMMARY_BEFORE_DATA" in out and "RECOMMENDATION" in out
    assert not any(name.endswith(".pdf") for name in os.listdir("early"))

    # The same command again, now that the results were printed, is allowed to proceed to the check.
    code = wikitrends.main(["analyze", "--topic", "astronomy", "--langs", "uk,pl", "--months", str(MONTHS),
                            "--out-dir", "early", "--summary", "Polish is LOSING GROUND."])
    assert code == 0


@pytest.mark.parametrize("text, flagged", [
    ("Polish interest is growing.", True),               # contradicts DEPRIORITISE
    ("Polish readers show stable interest.", True),       # contradicts DEPRIORITISE
    ("Інтерес польських читачів зростає.", True),          # the same, in Ukrainian
    ("Polish interest is not growing; it is falling.", False),
    ("Інтерес польських читачів не зростає.", False),
    ("Polish Wikipedia as a whole is stable while the platform shrinks.", False),   # about the platform
])
def test_prose_that_contradicts_the_recommendation_is_flagged(text, flagged):
    analysis = _analysis()
    assert next(c for c in analysis["decision"]["calls"] if c["label"].startswith("pl"))["action"] == "DEPRIORITISE"
    problems = [p for p in wikitrends.check_text(analysis, text) if "recommendation is" in p]
    assert bool(problems) == flagged, problems


@pytest.mark.parametrize("text", [
    "Polish share fell 30.6 percentage points.",
    "Частка польської впала на 30,6 відсоткових пунктів.",
])
def test_relative_change_written_as_percentage_points_is_flagged(text):
    analysis = _analysis()
    pl = next(r for r in analysis["series"] if r["lang"] == "pl")
    assert abs(pl["trend"]["relative"]["share_change_pct"] + 30.6) < 1.5      # the figure is real...
    problems = wikitrends.check_text(analysis, text)
    assert any("not percentage points" in p for p in problems), problems   # ...the unit is not


def test_recurring_spikes_are_labelled_in_the_digest():
    analysis = _analysis()
    result = analysis["series"][0]
    result["quality"].update(spike_months=["2024-09", "2025-09"], spike_share_of_views=0.2)
    assert "recurring September peak every year, not news" in wikitrends.digest(analysis, {})
