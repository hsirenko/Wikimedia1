"""Report language: every sentence a human reads, in each supported language.

The report follows the language of the user's request (detected from `--question`,
or set with `--report-lang`). Only words change: KPIs, rules and the JSON result are
identical in every language, and the JSON stays in English as the canonical record.

To add a language: copy the "en" block, translate every value, keep every {placeholder},
add 12 month names (and their "in <month>" form), and add the code to SUPPORTED.
tests/reporting/test_i18n.py fails if any key or placeholder is missing.
"""

from __future__ import annotations

import re
import string
from typing import Any

SUPPORTED = ("en", "uk")

MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September",
           "October", "November", "December"],
    "uk": ["Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень", "Липень", "Серпень", "Вересень",
           "Жовтень", "Листопад", "Грудень"],
}
MONTHS_IN = {   # "in January" / "у січні"
    "en": MONTHS["en"],
    "uk": ["січні", "лютому", "березні", "квітні", "травні", "червні", "липні", "серпні", "вересні", "жовтні",
           "листопаді", "грудні"],
}

CATALOG: dict[str, dict[str, str]] = {
    "en": {
        "title": "Wikipedia Market Intelligence Report",
        "s1": "1. Executive Decision Card", "s2": "2. Topic Definition", "s3": "3. Demand", "s4": "4. Growth",
        "s5": "5. Seasonality", "s6": "6. Language Opportunity", "s7": "7. Localization", "s8": "8. Topic Ecosystem",
        "s9": "9. Anomalies", "s10": "10. Data Quality", "s11": "11. Business Implications",
        "topic": "Topic", "edition": "Language edition", "edition_note": "a language edition, not a country",
        "period": "Analysis period", "period_value": "{start} to {end}",
        "annual": "Annual views (last 12 months)", "monthly": "Monthly average", "daily": "Daily average",
        "requested_views": "Views in the requested period", "unique": "Unique devices",
        "per_device": "Views per unique device", "yoy": "YoY", "cagr": "3Y CAGR", "momentum": "Momentum",
        "seasonality": "Seasonality", "season_value": "peak {peak}, trough {trough}",
        "localization": "Localization metrics", "quality": "Data quality",
        "observations": "Key observations", "no_observations": "No observation could be computed: see Data Quality.",
        "canonical": "Canonical topic", "wikidata": "Wikidata ID", "no_wikidata": "n/a (no Wikidata entity)",
        "article": "Article used", "article_value": "{title} (page ID {id})", "method": "Resolution method",
        "confidence": "Resolution confidence", "mappings": "Language mappings", "related": "Related topics",
        "kpi": "KPI", "value": "Value", "metric": "Metric", "status": "Status", "reason": "Reason",
        "chart_alt": "Monthly pageviews", "no_chart": "Trend chart unavailable: no months with data in the requested period.",
        "g_yoy": "YoY (last 12M vs previous 12M)", "g_cagr": "3Y CAGR", "g_3m": "Last 3M vs previous 3M",
        "g_prev3m": "Previous 3M vs the 3M before", "g_accel": "Acceleration",
        "g_pop": "Requested period vs previous equivalent period", "pp": "pp",
        "growth_note": "These are historical measurements, not forecasts. A growth chart is planned for a later milestone; the Demand chart shows the trend.",
        "peak": "Peak month", "trough": "Trough month", "peak_avg": "Peak / average", "trough_avg": "Trough / average",
        "volatility": "Volatility (coefficient of variation)",
        "basis": "Basis: calendar-month means over {start}..{end} ({n} observation(s) per month).",
        "basis_single": "Basis: calendar-month means over {start}..{end} (a single year, so one unusual month can decide the peak).",
        "penetration": "Wikipedia topic penetration", "affinity": "Topic affinity", "countries": "Country distribution",
        "not_country": "A language edition is not a country: {project} is read wherever that language is read.",
        "source": "Source", "source_value": "Wikimedia Analytics API ({api}), access={access}, agent={agent}",
        "retrieved": "Data retrieved", "generated": "Report generated", "generated_value": "{at} (software {version})",
        "coverage": "Coverage", "missing_data": "Missing data", "resolution_conf": "Topic resolution confidence",
        "unique_avail": "Unique devices available", "country_avail": "Country data available",
        "denominator_avail": "Project-level denominator available", "api_errors": "API errors",
        "quality_level": "Quality level", "yes": "yes", "no": "no", "none": "none",
        "not_computed": "Metrics not computed:", "raw": "Raw responses:",
        "missing_month": "{month}: no pageviews returned (zero views or no data)",
        "supports": "What the data supports", "not_establish": "What the data does NOT establish",
        "validate": "Questions requiring further validation",
        "supports_tail": "These figures describe reader attention to one Wikipedia article in {project}.",
        "ne1": "Revenue, market size (TAM) or willingness to pay: pageviews measure attention, not purchasing.",
        "ne2": "Product-market fit, or that a product on this topic would succeed.",
        "ne3": "Causes of any change: the data shows that traffic moved, not why.",
        "ne4": "Country-level demand: {project} readers are not one country's population.",
        "ne5": "That readers of related articles, or of other language editions, share this trend.",
        "q1": "Does search volume (e.g. Google Trends) show the same direction in this language?",
        "q2": "Is there App Store / Google Play demand for products on this topic in this language?",
        "q3": "What do competitors in this category earn, and how large is the addressable market?",
        "q4": "Will people pay? What do customer interviews and landing-page conversion rates show?",
        "q5": "What would customer acquisition cost, retention and monetization look like?",
        # observations
        "obs_annual": "Annual pageviews ({span}) were {views} (about {monthly} a month).",
        "obs_yoy_up": "Pageviews increased {pct} year over year ({span} vs {prev}).",
        "obs_yoy_down": "Pageviews decreased {pct} year over year ({span} vs {prev}).",
        "obs_yoy_flat": "Pageviews did not change year over year ({span} vs {prev}).",
        "obs_cagr": "Three-year CAGR was {pct} (vs {span}).",
        "obs_3m": "The last 3 months were {pct} against the previous 3 months{tail}.",
        "obs_3m_tail": "; momentum {label}",
        "obs_season": "{peak} had the highest average monthly traffic ({peak_ratio}x the average) and {trough} the lowest ({trough_ratio}x).",
        # labels
        "momentum.accelerating": "accelerating", "momentum.stable": "stable", "momentum.decelerating": "decelerating",
        "level.HIGH": "HIGH", "level.MEDIUM": "MEDIUM", "level.LOW": "LOW",
        "method.exact_title": "exact title", "method.redirect": "redirect", "method.wikidata_id": "Wikidata ID",
        "method.no_wikidata": "article without Wikidata entity", "method.search": "search",
        "status.unsupported": "unsupported", "status.unavailable": "unavailable",
        "status.insufficient_data": "insufficient data", "status.not_implemented": "not implemented",
        "status.api_error": "API error", "na": "n/a",
        # quality reasons
        "qr.coverage": "coverage {pct} is below 98%", "qr.confidence": "topic resolution confidence {value} is below 0.90",
        "qr.short": "requested period is {months} months (under 24: seasonality not repeated)",
        "qr.api": "{n} API error(s)", "qr.ok": "full coverage, confident topic match, at least two years of data",
        # resolution notes
        "note.redirect": "'{query}' redirects to '{title}'.",
        "note.missing": "No article in: {langs} (Wikidata {qid} has no sitelink there).",
        "note.no_wikidata": "'{title}' has no Wikidata entity, so other languages cannot be matched.",
        # reasons for metrics that are not computed
        "reason.unique_devices": "Wikimedia publishes unique devices per project (whole language edition) only, never per article.",
        "reason.country": "Wikimedia publishes country-level pageviews per project (top-by-country), not per article, so a topic's country distribution cannot be measured.",
        "reason.anomalies": "Anomaly detection is planned for a later milestone.",
        "reason.topic_share": "Needs a multi-language comparison (planned: compare command).",
        "reason.topic_affinity": "Needs project-level denominators for every compared edition (planned).",
        "reason.topic_penetration": "Needs the edition-wide pageview total (planned).",
        "reason.related_topics": "Topic ecosystem analysis is planned for a later milestone.",
        "reason.signals": "Decision signals are planned for a later milestone.",
        "reason.insufficient": "some months needed for this metric have no data",
        "reason.season_months": "not every calendar month has data in the requested period",
    },
    "uk": {
        "title": "Звіт ринкової аналітики на основі Вікіпедії",
        "s1": "1. Картка для ухвалення рішення", "s2": "2. Визначення теми", "s3": "3. Попит", "s4": "4. Зростання",
        "s5": "5. Сезонність", "s6": "6. Можливості за мовами", "s7": "7. Локалізація", "s8": "8. Екосистема теми",
        "s9": "9. Аномалії", "s10": "10. Якість даних", "s11": "11. Висновки для бізнесу",
        "topic": "Тема", "edition": "Мовний розділ", "edition_note": "мовний розділ, а не країна",
        "period": "Період аналізу", "period_value": "з {start} по {end}",
        "annual": "Перегляди за рік (останні 12 місяців)", "monthly": "Середнє на місяць", "daily": "Середнє на день",
        "requested_views": "Перегляди за вибраний період", "unique": "Унікальні пристрої",
        "per_device": "Переглядів на унікальний пристрій", "yoy": "Рік до року", "cagr": "CAGR за 3 роки",
        "momentum": "Імпульс", "seasonality": "Сезонність", "season_value": "пік — {peak}, спад — {trough}",
        "localization": "Показники локалізації", "quality": "Якість даних",
        "observations": "Ключові спостереження", "no_observations": "Жодне спостереження не вдалося обчислити: див. «Якість даних».",
        "canonical": "Канонічна тема", "wikidata": "Ідентифікатор Wikidata", "no_wikidata": "н/д (немає сутності у Wikidata)",
        "article": "Використана стаття", "article_value": "{title} (ID сторінки {id})", "method": "Спосіб зіставлення",
        "confidence": "Впевненість зіставлення", "mappings": "Відповідники в мовах", "related": "Пов'язані теми",
        "kpi": "Показник", "value": "Значення", "metric": "Показник", "status": "Статус", "reason": "Причина",
        "chart_alt": "Перегляди за місяць", "no_chart": "Графік тренду недоступний: за вибраний період немає місяців із даними.",
        "g_yoy": "Рік до року (останні 12 міс. проти попередніх 12)", "g_cagr": "CAGR за 3 роки",
        "g_3m": "Останні 3 міс. проти попередніх 3", "g_prev3m": "Попередні 3 міс. проти 3 міс. перед ними",
        "g_accel": "Прискорення", "g_pop": "Вибраний період проти попереднього такого самого періоду", "pp": "в. п.",
        "growth_note": "Це історичні вимірювання, а не прогнози. Графік зростання заплановано на наступний етап; тренд видно на графіку в розділі «Попит».",
        "peak": "Місяць піку", "trough": "Місяць спаду", "peak_avg": "Пік / середнє", "trough_avg": "Спад / середнє",
        "volatility": "Волатильність (коефіцієнт варіації)",
        "basis": "Основа: середні значення за календарними місяцями за {start}..{end} (спостережень на місяць: {n}).",
        "basis_single": "Основа: середні значення за календарними місяцями за {start}..{end} (лише один рік, тож один незвичний місяць може визначити пік).",
        "penetration": "Проникнення теми у Вікіпедії", "affinity": "Спорідненість теми", "countries": "Розподіл за країнами",
        "not_country": "Мовний розділ — це не країна: {project} читають усюди, де читають цією мовою.",
        "source": "Джерело", "source_value": "Wikimedia Analytics API ({api}), access={access}, agent={agent}",
        "retrieved": "Дані отримано", "generated": "Звіт створено", "generated_value": "{at} (версія програми {version})",
        "coverage": "Покриття", "missing_data": "Відсутні дані", "resolution_conf": "Впевненість зіставлення теми",
        "unique_avail": "Дані про унікальні пристрої", "country_avail": "Дані за країнами",
        "denominator_avail": "Загальний трафік розділу", "api_errors": "Помилки API",
        "quality_level": "Рівень якості", "yes": "так", "no": "ні", "none": "немає",
        "not_computed": "Показники, які не обчислено:", "raw": "Необроблені відповіді:",
        "missing_month": "{month}: переглядів не повернуто (нуль переглядів або немає даних)",
        "supports": "Що дані підтверджують", "not_establish": "Чого дані НЕ встановлюють",
        "validate": "Питання, які потребують додаткової перевірки",
        "supports_tail": "Ці цифри описують увагу читачів до однієї статті Вікіпедії в розділі {project}.",
        "ne1": "Виручку, розмір ринку (TAM) чи готовність платити: перегляди вимірюють увагу, а не купівлі.",
        "ne2": "Відповідність продукту ринку чи те, що продукт на цю тему буде успішним.",
        "ne3": "Причини змін: дані показують, що трафік змінився, але не чому.",
        "ne4": "Попит на рівні країни: читачі {project} — це не населення однієї країни.",
        "ne5": "Що читачі пов'язаних статей чи інших мовних розділів мають такий самий тренд.",
        "q1": "Чи показує обсяг пошукових запитів (напр., Google Trends) той самий напрям цією мовою?",
        "q2": "Чи є попит у App Store / Google Play на продукти з цієї теми цією мовою?",
        "q3": "Скільки заробляють конкуренти в цій категорії та який розмір доступного ринку?",
        "q4": "Чи готові люди платити? Що показують інтерв'ю з клієнтами та конверсія лендингів?",
        "q5": "Якими будуть вартість залучення клієнта, утримання та монетизація?",
        "obs_annual": "Перегляди за рік ({span}) становили {views} (приблизно {monthly} на місяць).",
        "obs_yoy_up": "Перегляди зросли на {pct} рік до року ({span} проти {prev}).",
        "obs_yoy_down": "Перегляди зменшилися на {pct} рік до року ({span} проти {prev}).",
        "obs_yoy_flat": "Перегляди не змінилися рік до року ({span} проти {prev}).",
        "obs_cagr": "CAGR за три роки становив {pct} (порівняно з {span}).",
        "obs_3m": "Останні 3 місяці: {pct} порівняно з попередніми 3 місяцями{tail}.",
        "obs_3m_tail": "; імпульс {label}",
        "obs_season": "Найвищий середній місячний трафік — у {peak} ({peak_ratio}× середнього), найнижчий — у {trough} ({trough_ratio}×).",
        "momentum.accelerating": "прискорюється", "momentum.stable": "стабільний", "momentum.decelerating": "сповільнюється",
        "level.HIGH": "ВИСОКА", "level.MEDIUM": "СЕРЕДНЯ", "level.LOW": "НИЗЬКА",
        "method.exact_title": "точна назва", "method.redirect": "перенаправлення", "method.wikidata_id": "ідентифікатор Wikidata",
        "method.no_wikidata": "стаття без сутності у Wikidata", "method.search": "пошук",
        "status.unsupported": "не підтримується", "status.unavailable": "недоступно",
        "status.insufficient_data": "недостатньо даних", "status.not_implemented": "ще не реалізовано",
        "status.api_error": "помилка API", "na": "н/д",
        "qr.coverage": "покриття {pct} нижче 98%", "qr.confidence": "впевненість зіставлення теми {value} нижче 0,90",
        "qr.short": "вибраний період — {months} міс. (менше 24: сезонність не повторюється)",
        "qr.api": "помилок API: {n}", "qr.ok": "повне покриття, надійне зіставлення теми, щонайменше два роки даних",
        "note.redirect": "«{query}» перенаправляє на «{title}».",
        "note.missing": "Немає статті в розділах: {langs} (у Wikidata {qid} немає там посилання).",
        "note.no_wikidata": "«{title}» не має сутності у Wikidata, тому інші мови зіставити неможливо.",
        "reason.unique_devices": "Wikimedia публікує унікальні пристрої лише для всього мовного розділу, а не для окремої статті.",
        "reason.country": "Wikimedia публікує перегляди за країнами лише для всього розділу (top-by-country), а не для статті, тому розподіл теми за країнами виміряти неможливо.",
        "reason.anomalies": "Виявлення аномалій заплановано на наступний етап.",
        "reason.topic_share": "Потрібне порівняння кількох мов (заплановано: команда compare).",
        "reason.topic_affinity": "Потрібен загальний трафік кожного порівнюваного розділу (заплановано).",
        "reason.topic_penetration": "Потрібна загальна кількість переглядів розділу (заплановано).",
        "reason.related_topics": "Аналіз екосистеми теми заплановано на наступний етап.",
        "reason.signals": "Сигнали для ухвалення рішень заплановано на наступний етап.",
        "reason.insufficient": "для цього показника бракує даних за деякі місяці",
        "reason.season_months": "не всі календарні місяці мають дані у вибраному періоді",
    },
}

# Which catalog reason explains which not-computed metric.
REASON_KEYS = {
    "demand.unique_devices": "reason.unique_devices", "demand.views_per_unique_device": "reason.unique_devices",
    "localization.country_distribution": "reason.country", "anomalies": "reason.anomalies",
    "localization.topic_share": "reason.topic_share", "localization.topic_affinity": "reason.topic_affinity",
    "localization.topic_penetration": "reason.topic_penetration", "ecosystem.related_topics": "reason.related_topics",
    "signals": "reason.signals", "seasonality.peak_month": "reason.season_months",
}


class Translator:
    """tr("key", **values) in the report language; English when a key is missing."""

    def __init__(self, lang: str = "en"):
        self.lang = lang if lang in SUPPORTED else "en"

    def __call__(self, key: str, **values: Any) -> str:
        return CATALOG[self.lang].get(key, CATALOG["en"][key]).format(**values)

    def month(self, english_name: str | None, *, in_form: bool = False) -> str | None:
        if not english_name:
            return None
        index = MONTHS["en"].index(english_name)
        return (MONTHS_IN if in_form else MONTHS)[self.lang][index]

    # Numbers: 56,910 and -17.2% in English; 56 910 and −17,2% in Ukrainian.
    def number(self, value: float, decimals: int = 0) -> str:
        text = f"{value:,.{decimals}f}"
        if self.lang == "uk":
            text = text.replace(",", " ").replace(".", ",")
        return text

    def percent(self, fraction: float, signed: bool = True) -> str:
        text = f"{fraction * 100:+.1f}%" if signed else f"{fraction * 100:.1f}%"
        return text.replace(".", ",").replace("-", "−") if self.lang == "uk" else text

    def decimal(self, value: float, decimals: int = 2) -> str:
        text = f"{value:.{decimals}f}"
        return text.replace(".", ",") if self.lang == "uk" else text

    def compact(self, value: float) -> str:
        for threshold, suffix_en, suffix_uk in ((1e9, "B", " млрд"), (1e6, "M", " млн"), (1e3, "K", " тис.")):
            if abs(value) >= threshold:
                return f"{self.decimal(value / threshold, 1)}{suffix_uk if self.lang == 'uk' else suffix_en}"
        return self.number(value)


# ---------------------------------------------------------------------------
# detecting the user's language from their own words
# ---------------------------------------------------------------------------

LATIN_HINTS = {
    "pl": (r"[ąęłśżźćń]", r"\b(czy|jest|nie|oraz|jak)\b"),
    "cs": (r"[ěščřžůý]", r"\b(je|jak|zda|není|pro)\b"),
    "de": (r"[äöüß]", r"\b(und|ist|nicht|wie|der|die|das)\b"),
    "fr": (r"[éèêàçù]", r"\b(est|pour|les|des|une|dans)\b"),
    "es": (r"[ñ¿¡áéíóú]", r"\b(es|para|los|las|una|cómo)\b"),
    "pt": (r"[ãõçáéê]", r"\b(é|para|os|uma|como|não)\b"),
    "it": (r"[àèìòù]", r"\b(è|per|gli|una|come|non)\b"),
}


def detect_language(text: str | None) -> str:
    """Language code of the user's request. May return a code without a translation."""
    if not text or not text.strip():
        return "en"
    cyrillic = len(re.findall(r"[а-яА-ЯіїєґІЇЄҐ]", text))
    latin = len(re.findall(r"[A-Za-z]", text))
    if cyrillic > latin:
        return "uk" if re.search(r"[іїєґІЇЄҐ']", text) else "ru"
    lowered = text.lower()
    scores = {lang: len(re.findall(chars, lowered)) * 2 + len(re.findall(words, lowered))
              for lang, (chars, words) in LATIN_HINTS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] >= 2 else "en"


def resolve_report_language(question: str | None, requested: str = "auto") -> tuple[str, str]:
    """(language the user wrote in, language the report will use)."""
    wanted = detect_language(question) if requested == "auto" else requested.lower()
    return wanted, (wanted if wanted in SUPPORTED else "en")


def placeholders(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}
