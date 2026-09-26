#!/usr/bin/env python3
"""The decision rules: fixed, documented, and traceable to numbers. No network."""

import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts"))

import analyze  # noqa: E402
import decide  # noqa: E402


def months(count, year=2024):
    return [f"{year + (i // 12)}-{i % 12 + 1:02d}" for i in range(count)]


def result(growth, level=3000, noise=0.08, count=30, seed=1, edition=100_000_000, title="Astronomia", lang="pl"):
    rng = random.Random(seed)
    ms = months(count)
    points = [{"month": m, "views": max(1, int(level * growth ** i * (1 + rng.uniform(-noise, noise))))}
              for i, m in enumerate(ms)]
    baseline = {m: edition for m in ms}
    r = analyze.analyze_series(points, baseline, label=f"{lang}: {title}")
    r.update(lang=lang, title=title)
    return r


def test_rules_map_numbers_to_actions():
    assert decide.action_for(result(1.03)) == "PRIORITISE"           # clear, consistent gain
    assert decide.action_for(result(0.97)) == "DEPRIORITISE"         # clear, consistent loss
    assert decide.action_for(result(1.0)) == "STABLE"                # inside the flat band
    assert decide.action_for(result(1.03, level=40)) == "INSUFFICIENT_EVIDENCE"   # too few readers


def test_every_evidence_step_carries_a_number():
    call = decide.decide_series(result(0.97), "2026-06")
    assert len(call["evidence"]) >= 4
    for step in call["evidence"]:
        assert any(ch.isdigit() for ch in step), step
    assert "90% range" in call["headline"] and "/100" in call["headline"]


def test_decision_is_reproducible():
    a = decide.decide_series(result(0.97), "2026-06")
    b = decide.decide_series(result(0.97), "2026-06")
    assert a == b


def test_trust_notes_are_specific_to_the_run():
    small = decide.decide_series(result(1.0, level=300), "2026-06")
    texts = " ".join(n["text"] for n in small["trust"])
    assert "300" in texts or "Small audience" in texts
    assert "'Astronomia'" in texts                     # names the article actually counted
    assert small["trust"][0]["risk"] in ("high", "medium")   # highest risk first


def test_recurring_peaks_are_not_called_news():
    r = result(1.0)
    r["quality"].update(spike_months=["2024-09", "2025-09"], spike_share_of_views=0.2)
    texts = " ".join(n["text"] for n in decide.trust_notes(r))
    assert "Recurring September" in texts and "news" not in texts.split("not news")[0]


def test_every_call_has_next_steps_and_a_falsifier():
    for growth in (1.03, 0.97, 1.0):
        call = decide.decide_series(result(growth), "2026-06")
        assert call["next_steps"] and call["would_change"]


def test_overall_call_names_the_best_candidate_and_flags_a_tie():
    analysis = {
        "period": {"to": "2026-06"},
        "series": [result(1.03, seed=1, lang="pl", title="A"), result(1.029, seed=2, lang="cs", title="B"),
                   result(0.96, seed=3, lang="uk", title="C")],
    }
    analysis["comparison"] = analyze.compare(analysis["series"])
    memo = decide.decide(analysis)
    assert memo["overall"].startswith("Best candidate:")
    assert "Deprioritise: uk: C" in memo["overall"]
    # pl and cs grow at almost the same rate: whichever is picked, the tie must be stated.
    assert "within noise" in memo["overall"]
