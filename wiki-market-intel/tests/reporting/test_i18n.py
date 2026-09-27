"""Report language follows the user's request; the JSON stays English."""

import re

import pytest

from wiki_market_intel import analyze, i18n
from wiki_market_intel.reporting import generator, markdown
from wiki_market_intel.validate import validate_file
from tests.reporting.test_end_to_end import run_cli  # noqa: F401  (fixture)

UK_QUESTION = "Як змінюється інтерес до медитації в німецькомовній Вікіпедії?"


@pytest.mark.parametrize("lang", [l for l in i18n.SUPPORTED if l != "en"])
def test_every_language_has_every_key_with_the_same_placeholders(lang):
    english, other = i18n.CATALOG["en"], i18n.CATALOG[lang]
    assert set(other) == set(english), set(english) ^ set(other)
    for key, template in english.items():
        assert i18n.placeholders(other[key]) == i18n.placeholders(template), key
    assert len(i18n.MONTHS[lang]) == len(i18n.MONTHS_IN[lang]) == 12


@pytest.mark.parametrize("text, lang", [
    (UK_QUESTION, "uk"), ("How is interest in meditation changing?", "en"),
    ("Czy rośnie zainteresowanie medytacją?", "pl"), ("Wie entwickelt sich das Interesse an Meditation?", "de"),
    (None, "en"), ("", "en"),
])
def test_language_is_detected_from_the_users_words(text, lang):
    assert i18n.detect_language(text) == lang


def test_unsupported_language_falls_back_to_english():
    assert i18n.resolve_report_language("Czy rośnie zainteresowanie medytacją?") == ("pl", "en")
    assert i18n.resolve_report_language(UK_QUESTION, "en") == ("en", "en")


def test_ukrainian_number_formatting():
    tr = i18n.Translator("uk")
    assert tr.number(56910) == "56 910"
    assert tr.percent(-0.172) == "−17,2%"
    assert tr.compact(56910) == "56,9 тис."
    assert tr.month("January") == "Січень" and tr.month("January", in_form=True) == "січні"


@pytest.fixture
def uk_result(services):
    return analyze("meditation", "de", "3y", question=UK_QUESTION, services=services)


def test_ukrainian_question_gives_a_ukrainian_report(uk_result):
    assert uk_result.metadata.report_language == "uk" and uk_result.metadata.question == UK_QUESTION
    text = markdown.render(uk_result, "charts/trend.png", "uk")
    assert text.startswith("# Звіт ринкової аналітики на основі Вікіпедії")
    numbers = [int(n) for n in re.findall(r"^## (\d+)\.", text, re.M)]
    assert numbers == list(range(1, 5))                       # Recommendation, Graph, Observations, KPI
    assert "−17,2%" in text and "пік — січень (1,29×), спад — липень" in text
    for english in ("Annual views", "Key Observations", "What the data", "Topic Definition", "increased",
                    "decreased", "unsupported", "not implemented", "Quality level", "n/a"):
        assert english not in text, english


def test_json_stays_english_and_valid_whatever_the_report_language(uk_result, tmp_path):
    files = generator.write(uk_result, tmp_path)
    assert "Звіт ринкової аналітики" in files.markdown.read_text("utf-8")
    assert uk_result.observations[1].startswith("Pageviews decreased")     # canonical record in English
    assert validate_file(files.json) == []


def test_english_is_the_default(services):
    r = analyze("meditation", "de", "3y", services=services)
    assert r.metadata.report_language == "en"
    assert markdown.render(r, None).startswith("# Wikipedia Market Intelligence Report")


def test_cli_tells_the_agent_which_language_to_reply_in(run_cli, settings, capsys):  # noqa: F811
    assert run_cli("analyze", "--topic", "meditation", "--language", "de", "--question", UK_QUESTION) == 0
    out = capsys.readouterr().out
    assert "REPORT_LANGUAGE uk" in out and "Reply to the user in it" in out
    assert "Перегляди зменшилися на 17,2%" in out
    report = next(settings.reports_dir.rglob("report.md")).read_text("utf-8")
    assert report.startswith("# Звіт ринкової аналітики")


def test_cli_reports_an_untranslated_user_language(run_cli, capsys):  # noqa: F811
    run_cli("analyze", "--topic", "meditation", "--language", "de", "--question", "Czy rośnie zainteresowanie medytacją?")
    out = capsys.readouterr().out
    assert "REPORT_LANGUAGE en" in out and "'pl'" in out and "reply to them in their language" in out


def test_report_language_can_be_forced(run_cli, settings, capsys):  # noqa: F811
    run_cli("analyze", "--topic", "meditation", "--language", "de", "--question", UK_QUESTION,
            "--report-lang", "en")
    assert "REPORT_LANGUAGE" not in capsys.readouterr().out
    assert next(settings.reports_dir.rglob("report.md")).read_text("utf-8").startswith("# Wikipedia Market")
