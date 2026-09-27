"""Topic resolution (spec §5, §31): explicit, and never silently choosing between concepts."""

def test_exact_match_maps_languages_through_wikidata(services):
    r = services.resolver.resolve("meditation", ["de"])
    assert r.status == "resolved" and r.method == "exact_title" and r.confidence == 0.98
    assert r.canonical_topic == "Meditation"          # the article title, not Wikidata's lowercase label
    assert r.wikidata_id == "Q108458"
    assert r.articles["de"].title == "Meditation" and r.articles["de"].page_id == 28837


def test_redirect_is_followed_and_noted(services):
    r = services.resolver.resolve("Mindfulness meditation", ["en"])
    assert r.status == "resolved" and r.method == "redirect" and r.confidence == 0.90
    assert r.canonical_topic == "Mindfulness"
    assert any("redirects to" in n for n in r.notes)


def test_missing_language_article_is_reported_not_guessed(services):
    r = services.resolver.resolve("Mindfulness", ["en", "de"])
    assert r.missing_languages == ["de"] and "de" not in r.articles
    assert any("No article in: de" in n for n in r.notes)


def test_disambiguation_page_requires_review(services):
    r = services.resolver.resolve("Mercury", ["en"])
    assert r.status == "needs_review" and not r.articles
    assert [c.title for c in r.candidates] == ["Mercury (planet)", "Mercury (element)"]
    message = r.review_message()
    assert message.startswith("Topic resolution requires review.")
    assert "1. Mercury (planet) (Q308) - Smallest planet" in message


def test_search_only_match_is_not_chosen_automatically(services):
    r = services.resolver.resolve("Meditaton", ["de"])       # a typo: search finds Meditation
    assert r.status == "needs_review" and r.candidates[0].title == "Meditation"


def test_unknown_topic_is_not_found(services):
    r = services.resolver.resolve("Qwxzzyq", ["de"])
    assert r.status == "not_found" and not r.candidates


def test_wikidata_id_input(services):
    r = services.resolver.resolve("Q108458", ["de", "en"])
    assert r.method == "wikidata_id" and r.confidence == 1.0
    assert set(r.articles) == {"de", "en"}


def test_article_without_wikidata_is_resolved_with_lower_confidence(services):
    r = services.resolver.resolve("Obscurium", ["en", "de"])
    assert r.method == "no_wikidata" and r.confidence == 0.70 and r.missing_languages == ["de"]
