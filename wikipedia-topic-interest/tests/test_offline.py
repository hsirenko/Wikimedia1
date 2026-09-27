#!/usr/bin/env python3
"""
Tests for the no-network bridge: plan -> fetch elsewhere -> ingest -> analyze --offline.

This path exists for sandboxes that cannot reach wikimedia.org (Claude's code
execution container, for one). The agent's own web tool does the fetching; the
skill only does arithmetic.

Nothing here touches the network. Offline mode raises before any socket is opened,
and the "fetched" file contents are generated from the same fake API that
test_pipeline.py uses, so the whole round trip is exercised deterministically.
"""

import json
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import wikitrends  # noqa: E402
import wm_api  # noqa: E402
from test_pipeline import MONTHS, fake_get_json  # noqa: E402

MAX_ROUNDS = 6


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch, tmp_path):
    """A private cache per test, and no leaked offline flag between tests."""
    monkeypatch.setenv("WIKITRENDS_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("WIKITRENDS_NO_CACHE", raising=False)
    monkeypatch.delenv("WIKITRENDS_OFFLINE", raising=False)
    monkeypatch.setenv("WIKITRENDS_NO_ASSETS", "1")
    wm_api.MISSES.clear()
    monkeypatch.chdir(tmp_path)
    yield
    wm_api.MISSES.clear()


def serve(plan_dir):
    """Stand in for the agent's web tool: write each planned URL's body to disk."""
    with open(os.path.join(plan_dir, "fetch-plan.json"), encoding="utf-8") as fh:
        plan = json.load(fh)
    for entry in plan:
        status, payload = fake_get_json(entry["url"])
        with open(os.path.join(plan_dir, entry["save_as"]), "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
    return [entry["url"] for entry in plan]


def plan_args(extra=()):
    return ["plan", "--topic", "astronomy", "--langs", "uk,pl",
            "--months", str(MONTHS), "--out-dir", "fetch"] + list(extra)


def analyze_args(extra=()):
    return ["analyze", "--topic", "astronomy", "--langs", "uk,pl",
            "--months", str(MONTHS), "--offline", "--no-pdf",
            "--out-dir", "out", "--brief"] + list(extra)


# --------------------------------------------------------------------------
# offline mode refuses to invent data
# --------------------------------------------------------------------------

def test_offline_with_empty_cache_reports_incomplete_rather_than_guessing(capsys):
    code = wikitrends.main(analyze_args())
    output = capsys.readouterr().out
    assert code == 3                      # distinct from "no data exists"
    assert "OFFLINE" in output
    assert "not cached" in output
    assert wm_api.MISSES                  # and it recorded what it needed


def test_offline_never_opens_a_socket(monkeypatch):
    """Belt and braces: make any real request explode, then run offline."""
    def explode(*args, **kwargs):
        raise AssertionError("offline mode attempted a network request")

    monkeypatch.setattr(wm_api.urllib.request, "urlopen", explode)
    monkeypatch.setenv("WIKITRENDS_OFFLINE", "1")
    analysis = wikitrends.run_analysis(topics=["astronomy"], langs=["uk"], months=MONTHS)
    assert analysis["status"] == "no_data"


# --------------------------------------------------------------------------
# plan
# --------------------------------------------------------------------------

def test_plan_lists_urls_and_writes_a_manifest(capsys):
    code = wikitrends.main(plan_args())
    output = capsys.readouterr().out
    assert code == 3                      # 3 means "work still to do"
    assert "FETCH" in output

    with open("fetch/fetch-plan.json", encoding="utf-8") as fh:
        plan = json.load(fh)
    assert plan
    for entry in plan:
        assert entry["url"].startswith("https://")
        assert entry["save_as"].endswith(".json")
        assert entry["save_as"] in output  # the agent is told the exact filename
    # Filenames must be unique or responses would overwrite each other.
    assert len({e["save_as"] for e in plan} ) == len(plan)


def test_plan_asks_for_the_title_lookup_first():
    wikitrends.main(plan_args())
    with open("fetch/fetch-plan.json", encoding="utf-8") as fh:
        urls = [e["url"] for e in json.load(fh)]
    assert any("action=query" in u for u in urls)
    # Pageview URLs are not knowable yet - the article titles are still unknown.
    assert not any("per-article" in u for u in urls)


def test_plan_reports_ready_once_everything_is_cached(capsys):
    for _ in range(MAX_ROUNDS):
        if wikitrends.main(plan_args()) == 0:
            break
        serve("fetch")
        wikitrends.main(["ingest", "--dir", "fetch"])
    else:
        pytest.fail("plan never reached READY")

    capsys.readouterr()
    assert wikitrends.main(plan_args()) == 0
    assert "READY" in capsys.readouterr().out


def test_explicit_articles_need_only_one_round(capsys):
    """Skipping concept resolution removes the dependency between rounds."""
    args = ["plan", "--articles", "uk:Астрономія,pl:Astronomia",
            "--months", str(MONTHS), "--out-dir", "fetch"]
    assert wikitrends.main(args) == 3
    capsys.readouterr()

    serve("fetch")
    wikitrends.main(["ingest", "--dir", "fetch"])
    capsys.readouterr()

    assert wikitrends.main(args) == 0
    assert "READY" in capsys.readouterr().out


# --------------------------------------------------------------------------
# ingest
# --------------------------------------------------------------------------

def test_ingest_without_a_plan_fails_clearly(capsys):
    os.makedirs("empty", exist_ok=True)
    assert wikitrends.main(["ingest", "--dir", "empty"]) == 2
    assert "No fetch-plan.json" in capsys.readouterr().err


def test_ingest_reports_files_the_agent_did_not_save(capsys):
    wikitrends.main(plan_args())
    capsys.readouterr()
    assert wikitrends.main(["ingest", "--dir", "fetch"]) == 2
    assert "still missing" in capsys.readouterr().out


def test_ingest_rejects_a_body_that_is_not_json(capsys):
    wikitrends.main(plan_args())
    with open("fetch/fetch-plan.json", encoding="utf-8") as fh:
        plan = json.load(fh)
    # A web tool that returns prose or a truncated body must not poison the cache.
    with open(os.path.join("fetch", plan[0]["save_as"]), "w", encoding="utf-8") as fh:
        fh.write("Here is the JSON you asked for: {items: ...")
    capsys.readouterr()

    assert wikitrends.main(["ingest", "--dir", "fetch"]) == 2
    output = capsys.readouterr().out
    assert "not valid JSON" in output
    assert "raw response body exactly" in output


def test_ingest_makes_data_available_to_later_commands(capsys):
    wikitrends.main(plan_args())
    urls = serve("fetch")
    capsys.readouterr()
    wikitrends.main(["ingest", "--dir", "fetch"])

    # Reading through the normal path must now succeed with the network still off.
    os.environ["WIKITRENDS_OFFLINE"] = "1"
    status, payload = wm_api._get_json(urls[0])
    assert status == 200
    assert payload


def test_cache_store_round_trips():
    url = "https://example.org/probe"
    wm_api.cache_store(url, {"hello": "world"})
    os.environ["WIKITRENDS_OFFLINE"] = "1"
    assert wm_api._get_json(url) == (200, {"hello": "world"})


# --------------------------------------------------------------------------
# the whole bridge
# --------------------------------------------------------------------------

def test_full_offline_bridge_produces_the_same_analysis(capsys):
    """plan -> fetch -> ingest, repeated, then a complete offline analysis."""
    rounds = 0
    for _ in range(MAX_ROUNDS):
        if wikitrends.main(plan_args()) == 0:
            break
        rounds += 1
        serve("fetch")
        wikitrends.main(["ingest", "--dir", "fetch"])
    else:
        pytest.fail("plan never reached READY")
    capsys.readouterr()

    assert wikitrends.main(analyze_args()) == 0
    output = capsys.readouterr().out
    assert "PERIOD" in output
    assert "verdict:" in output
    assert "OFFLINE" not in output          # nothing was left unfetched
    assert rounds <= 3                      # title lookup, sitelinks, pageviews

    # And it must agree with what the online path computes from the same responses.
    os.environ["WIKITRENDS_OFFLINE"] = "1"
    analysis = wikitrends.run_analysis(topics=["astronomy"], langs=["uk", "pl"], months=MONTHS)
    assert analysis["status"] == "ok"
    assert {r["label"] for r in analysis["series"]} == {"uk: Астрономія", "pl: Astronomia"}
    assert analysis["comparison"]["ranking"][0]["label"] == "uk: Астрономія"


def test_offline_analysis_still_writes_json_and_csv():
    for _ in range(MAX_ROUNDS):
        if wikitrends.main(plan_args()) == 0:
            break
        serve("fetch")
        wikitrends.main(["ingest", "--dir", "fetch"])

    assert wikitrends.main(analyze_args()) == 0
    written = os.listdir("out")
    assert any(f.endswith(".json") for f in written)
    assert any(f.endswith(".csv") for f in written)


# --------------------------------------------------------------------------
# blocked network: the CLI must hand the agent the offline flow, not a dead end
# --------------------------------------------------------------------------

def _blocked(url, user_agent=None):
    raise wm_api.ApiError(f"Network failure for {url}: [Errno 111] Connection refused")


def test_blocked_network_prints_the_offline_commands(monkeypatch, capsys):
    """Seen on Claude.ai: a bare error made the model give up and describe hypothetical results."""
    monkeypatch.setattr(wm_api, "_get_json", _blocked)
    code = wikitrends.main(["analyze", "--topic", "astronomy", "--langs", "uk", "--months", "24", "--no-pdf"])
    out = capsys.readouterr().out
    assert code == wikitrends.EXIT_NETWORK_BLOCKED
    assert out.startswith("NETWORK_BLOCKED")
    assert "python3 scripts/wikitrends.py plan --topic astronomy --langs uk --months 24 --out-dir fetch" in out
    assert "python3 scripts/wikitrends.py analyze --topic astronomy --langs uk --months 24 --offline" in out


def test_blocked_network_with_explicit_articles_is_not_reported_as_no_data(monkeypatch, capsys):
    """With --articles each failed request became a note, so the run ended as 'no usable data'."""
    monkeypatch.setattr(wm_api, "_get_json", _blocked)
    code = wikitrends.main(["analyze", "--articles", "uk:Астрономія", "--no-pdf"])
    out = capsys.readouterr().out
    assert code == wikitrends.EXIT_NETWORK_BLOCKED
    assert "--articles 'uk:Астрономія'" in out   # shell-quoted, safe to paste
    assert "no usable data" not in out


def test_resolve_on_a_blocked_network_also_points_to_the_offline_flow(monkeypatch, capsys):
    monkeypatch.setattr(wm_api, "_get_json", _blocked)
    assert wikitrends.main(["resolve", "--topic", "astronomy", "--langs", "uk"]) == wikitrends.EXIT_NETWORK_BLOCKED
    assert "NETWORK_BLOCKED" in capsys.readouterr().out


def test_a_real_api_error_is_not_mistaken_for_a_blocked_network(monkeypatch, capsys):
    def bad_request(url, user_agent=None):
        raise wm_api.ApiError(f"HTTP 400 for {url}: invalid title", 400)
    monkeypatch.setattr(wm_api, "_get_json", bad_request)
    code = wikitrends.main(["analyze", "--topic", "astronomy", "--langs", "uk", "--no-pdf"])
    captured = capsys.readouterr()
    assert code == 4
    assert "NETWORK_BLOCKED" not in captured.out
    assert "HTTP 400" in captured.err
