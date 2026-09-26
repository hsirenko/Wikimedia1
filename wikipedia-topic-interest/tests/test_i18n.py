#!/usr/bin/env python3
"""Report language: complete translations, correct detection, and a memo with no leftovers."""

import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
sys.path.insert(0, HERE)

import i18n  # noqa: E402


@pytest.mark.parametrize("lang", [l for l in i18n.SUPPORTED if l != "en"])
def test_every_language_has_every_key_with_the_same_placeholders(lang):
    english, other = i18n.CATALOG["en"], i18n.CATALOG[lang]
    assert set(other) == set(english), set(english) ^ set(other)
    for key, template in english.items():
        assert i18n.placeholders(other[key]) == i18n.placeholders(template), key
    assert len(i18n.MONTHS[lang]) == 12


@pytest.mark.parametrize("text, lang", [
    ("Чи зростає інтерес до астрономії в україномовній Wikipedia?", "uk"),
    ("Is interest in astronomy growing in Ukrainian Wikipedia?", "en"),
    ("Czy rośnie zainteresowanie astronomią w polskiej Wikipedii?", "pl"),
    ("Wie entwickelt sich das Interesse an Astronomie?", "de"),
    ("Растет ли интерес к астрономии?", "ru"),
    ("", "en"),
])
def test_language_is_detected_from_the_users_words(text, lang):
    assert i18n.detect_language(text) == lang


def test_ukrainian_grammar_for_editions_and_months():
    tr = i18n.Translator("uk")
    assert tr.edition("uk", "Ukrainian") == "в українській Вікіпедії"
    assert tr.editions(["uk", "pl"], ["Ukrainian", "Polish"]) == "у Вікіпедії: українська, польська"
    assert tr.month("09") == "вересні"


def test_unsupported_language_falls_back_to_english():
    assert i18n.Translator("pl").lang == "en"


# --- the whole pipeline in Ukrainian ---------------------------------------

import wikitrends  # noqa: E402
import wm_api  # noqa: E402
from test_pipeline import MONTHS, fake_get_json  # noqa: E402


@pytest.fixture
def offline(monkeypatch, tmp_path):
    monkeypatch.setattr(wm_api, "_get_json", fake_get_json)
    monkeypatch.setenv("WIKITRENDS_NO_CACHE", "1")
    monkeypatch.chdir(tmp_path)


def test_ukrainian_question_gives_a_ukrainian_memo_and_digest(offline, capsys):
    question = "Чи варто додавати курс з астрономії для українськомовних користувачів?"
    code = wikitrends.main(["analyze", "--topic", "astronomy", "--langs", "uk,pl", "--months", str(MONTHS),
                            "--out-dir", "u", "--question", question])
    out = capsys.readouterr().out
    assert code == 0
    assert "REPORT_LANGUAGE uk" in out and "RECOMMENDATION_UK" in out
    assert "RECOMMENDATION " in out          # the English line stays, for the agent's own reasoning

    import decide
    analysis = wikitrends.run_analysis(topics=["astronomy"], langs=["uk", "pl"], months=MONTHS)
    memo = decide.decide(analysis, "uk")
    text = " ".join([memo["overall"]] + [line for c in memo["calls"] for line in
                    c["evidence"] + c["next_steps"] + [c["would_change"]] + [n["text"] for n in c["trust"]]])
    for english in ("Interest in", "Readers:", "Platform:", "Re-run", "Deprioritise", "Best candidate",
                    "views a month", "Counts one article"):
        assert english not in text, english
    assert memo["overall_action"] in decide.ACTIONS       # the action code itself never changes


def test_explicit_report_language_overrides_detection(offline, capsys):
    wikitrends.main(["analyze", "--topic", "astronomy", "--langs", "uk", "--months", str(MONTHS), "--no-pdf",
                     "--out-dir", "e", "--question", "Чи зростає інтерес?", "--report-lang", "en"])
    assert "REPORT_LANGUAGE" not in capsys.readouterr().out


def test_unsupported_user_language_is_reported_to_the_agent(offline, capsys):
    wikitrends.main(["analyze", "--topic", "astronomy", "--langs", "uk", "--months", str(MONTHS), "--no-pdf",
                     "--out-dir", "p", "--question", "Czy rośnie zainteresowanie astronomią?"])
    out = capsys.readouterr().out
    assert "REPORT_LANGUAGE en" in out and "'pl'" in out and "reply to them in their language" in out
