#!/usr/bin/env python3
"""
Report language: every sentence the memo prints, in each supported language.

The memo is read by founders in their own language, so the language follows the
user's request (detected from --question, or set with --report-lang). Numbers,
rules and recommendations are identical in every language; only the words change.

To add a language: copy the "en" block, translate every value, keep every
{placeholder}, and add the code to SUPPORTED. tests/test_i18n.py checks that no
key or placeholder is missing.
"""

from __future__ import annotations

import re
import string
from typing import Any, Dict, Optional

SUPPORTED = ("en", "uk")

MONTHS = {
    "en": ["January", "February", "March", "April", "May", "June", "July", "August",
           "September", "October", "November", "December"],
    # Locative ("у вересні"), the form every Ukrainian sentence here needs.
    "uk": ["січні", "лютому", "березні", "квітні", "травні", "червні", "липні", "серпні",
           "вересні", "жовтні", "листопаді", "грудні"],
}

CATALOG: Dict[str, Dict[str, str]] = {
    "en": {
        # actions: label shown in the memo, short call, headline sentence
        "action.PRIORITISE": "PRIORITISE",
        "action.PROMISING": "PROMISING",
        "action.STABLE": "STABLE",
        "action.NO_CLEAR_SIGNAL": "NO CLEAR SIGNAL",
        "action.DEPRIORITISE": "DEPRIORITISE",
        "action.INSUFFICIENT_EVIDENCE": "INSUFFICIENT EVIDENCE",
        "short.PRIORITISE": "Validate demand now",
        "short.PROMISING": "Promising, not yet confirmed",
        "short.STABLE": "Steady audience, not a growth bet",
        "short.NO_CLEAR_SIGNAL": "No clear signal",
        "short.DEPRIORITISE": "Do not invest on this signal",
        "short.INSUFFICIENT_EVIDENCE": "Too little data to decide",
        "headline.PRIORITISE": "Interest in {what} is growing beyond platform movement",
        "headline.PROMISING": "Interest in {what} may be growing, but the range still includes no change",
        "headline.STABLE": "Interest in {what} is holding steady relative to the rest of the edition",
        "headline.NO_CLEAR_SIGNAL": "Interest in {what} moved, but not consistently enough to call a direction",
        "headline.DEPRIORITISE": "Interest in {what} is falling faster than the platform itself",
        "headline.INSUFFICIENT_EVIDENCE": "There is too little data on {what} to support a call",
        "headline.softening": ", though softening slightly (the whole range is below zero)",
        "headline.slight_gain": ", with a slight real gain (the whole range is above zero)",
        "headline.figures": "share of edition traffic {share} (90% range {range}), ",
        "headline.full": "{short}. {sentence}: {figures}confidence {confidence}/100.",
        "what": "'{title}' in {edition}",
        "range": "{low} to {high}",
        "range.none": "no range (under 24 months of data)",
        # evidence chain
        "ev.period.none": "trend estimate, under 24 months",
        "ev.period": "{recent} vs {previous}",
        "ev.readers": "Readers: views {raw} year over year ({period}), median {median} views a month.",
        "ev.platform": "Platform: all of {project} changed {edition} over the same months, which explains part of any raw change.",
        "ev.signal": "Topic-specific signal: share of edition traffic {share} (90% range {range}), so {meaning}.",
        "ev.meaning.below": "a real loss of attention, beyond the platform decline",
        "ev.meaning.above": "a real gain in attention, beyond platform movement",
        "ev.meaning.crosses": "direction not established: the range includes no change",
        "ev.meaning.unknown": "no range available",
        "ev.consistency": "Consistency: share beat the same month a year earlier in {up} of the last 12 months (trend test {p}).",
        "ev.no_baseline": "No edition-wide baseline was available, so the platform effect cannot be removed.",
        "ev.intensity": "Intensity: {per_million} views per million views of the whole edition.",
        "ev.timing": "Timing: strong yearly cycle (strength {strength}), peaking in {month}.",
        # next steps
        "next.rerun": "Re-run after {month} data is published (early next month); it takes about a second.",
        "next.timing": "If you go ahead, launch or advertise ahead of the {month} peak.",
        "next.PRIORITISE": "Test willingness to pay before building: a landing page or waitlist aimed at readers in {language}, with a success threshold agreed in advance.",
        "next.PROMISING": "Treat it as a hypothesis. Check search volume in {language} and run a small ad test before committing budget.",
        "next.STABLE.size": "Decide on size and fit rather than momentum: {median} readers a month.",
        "next.STABLE.size_intensity": "Decide on size and fit rather than momentum: {median} readers a month at {per_million} per million edition views.",
        "next.STABLE.search": "Compare with search-volume data in {language} before committing.",
        "next.NO_CLEAR_SIGNAL": "Do not act on direction. Widen the window (--months 36) or add related articles to get a clearer signal.",
        "next.DEPRIORITISE.1": "Do not invest on the strength of this signal. If there are strategic reasons to proceed, require independent evidence (search trends, competitor revenue).",
        "next.DEPRIORITISE.2": "Check whether adjacent topics absorbed the interest before dropping the theme.",
        "next.DEPRIORITISE.3": "Re-check in three months.",
        "next.INSUFFICIENT_EVIDENCE": "Widen the question: a broader article, a larger language edition, or English Wikipedia as a benchmark.",
        # what would change the call
        "change.PRIORITISE": "Downgrade if a later run's range includes zero, or if the growth turns out to sit in one-off spike months.",
        "change.PROMISING": "Upgrade to PRIORITISE when the whole 90% range sits above zero; downgrade if it drops below.",
        "change.STABLE": "Becomes a growth signal if the share grows more than 10% year over year with the whole range above zero.",
        "change.NO_CLEAR_SIGNAL": "A direction needs both a move of over 10% and consistency across months (p<0.05).",
        "change.DEPRIORITISE": "Reconsider if the topic's share of {project} stops falling: a later run whose range includes zero.",
        "change.INSUFFICIENT_EVIDENCE": "More history (24+ months) or a larger audience (500+ views a month).",
        # trust notes
        "trust.very_small": "Very small audience ({median} views a month): changes this small are mostly noise.",
        "trust.small": "Small audience ({median} views a month): 50 readers more or less move a month by about {pct}.",
        "trust.ok": "Audience of {median} views a month is large enough to measure.",
        "trust.crosses": "Direction not established: the 90% range includes no change.",
        "trust.established.below": "Direction established: the whole 90% range is below zero.",
        "trust.established.above": "Direction established: the whole 90% range is above zero.",
        "trust.volatile": "Large month-to-month swings ({pct} variation): single months mean little; this report uses 12-month totals.",
        "trust.recurring": "Recurring {months} peaks ({dates}) hold {pct} of views: a yearly cycle, not news. The 12-month comparison already cancels it.",
        "trust.recurring.join": " and ",
        "trust.one_off": "One-off spike months {dates} hold {pct} of all views: likely news or events, not lasting interest.",
        "trust.one_article": "Counts one article ('{title}'). Readers of related articles, and of other language editions such as English, are not included.",
        "trust.curiosity": "Views measure curiosity, not willingness to pay: confirm demand before building.",
        "risk.high": "HIGH", "risk.medium": "MED", "risk.low": "LOW",
        # overall call with several editions
        "overall.best": "Best candidate: {label}. {headline}",
        "overall.ties": " Its lead over {labels} is within noise; treat them as equal candidates.",
        "overall.clear": " Its lead over the other candidates is outside the 90% ranges.",
        "overall.dropped": " Deprioritise: {labels}.",
        "overall.thin": " Not enough data: {labels}.",
        # memo page
        "memo.title": "Decision memo: {topics} in {editions}",
        "memo.subtitle": "Decision memo · Wikipedia pageviews {start} to {end}, humans only · generated {today} · source: Wikimedia Pageviews API",
        "memo.question": "Question:",
        "memo.recommendation": "RECOMMENDATION: {action}",
        "memo.analyst_note": "Analyst note:",
        "memo.why": "Why: the evidence for {label}",
        "memo.next": "What to do next",
        "memo.change": "What would change this call",
        "memo.trust": "How far to trust this",
        "memo.assumptions": "Assumptions behind the numbers",
        "memo.method": "Method.",
        "memo.rules": "Decision rules are fixed and published in references/ANALYSIS_METHODS.md; the same data always gives the same recommendation.",
        "memo.reproduce": "Reproduce:",
        "memo.footer": "Wikipedia reading interest is a research signal, not proof of demand.",
        "ask.pdf": "Would you also like a one-page PDF of this report?",
        "memo.method_note": "Direction comes from a Mann-Kendall trend test over all months (not first-vs-last); magnitude from a Theil-Sen slope and a year-over-year comparison of 12-month blocks, which cancels seasonality. Spike months are flagged via a median-absolute-deviation outlier test. Cross-edition figures are normalised to views per million edition views. Ranges are 90% intervals from resampling paired months; overlapping ranges mean two editions are not clearly different.",
        "score.edition": "Edition / article", "score.action": "Recommendation", "score.readers": "Readers / month",
        "score.share": "Share change (90% range)", "score.months_up": "Months up (of 12)",
        "score.confidence": "Confidence", "score.no_data": "NO DATA",
        "edition.one": "{name} Wikipedia",
        "edition.many": "{names} Wikipedia",
        # charts
        "chart.share": "Share of edition traffic (views per million), 3-month average",
        "chart.vs": "Topic vs the whole edition (index: first 12 months = 100, 3-month average)",
        "chart.vs.edition": "all of {project}",
        "chart.vs.topic": "'{title}' readers",
        "chart.range": "Change in share, last 12 vs previous 12 months\n(bar = estimate, whisker = 90% range)",
        # assumptions
        "assume.articles": "One article per edition, matched to the same concept via Wikidata ({source}). Related articles and redirects are not counted.",
        "assume.source": "'{topic}' = Wikidata {qid}",
        "assume.articles_given": "Articles were given explicitly (--articles); no concept matching was done.",
        "assume.traffic": "Traffic: humans only (bots and spiders excluded), all devices, complete months {start}..{end}.",
        "assume.growth": "Growth = last 12 months vs the 12 before (seasonality cancels), with a 90% interval from resampling months. 'Flat' means within ±{band}%; a trend also needs p<{p}.",
        "assume.share": "Editions are compared on share of their own traffic (views per million edition views), because total Wikipedia traffic is falling at different rates in different languages.",
    },
    "uk": {
        "action.PRIORITISE": "ПРІОРИТЕТ",
        "action.PROMISING": "ПЕРСПЕКТИВНО",
        "action.STABLE": "СТАБІЛЬНО",
        "action.NO_CLEAR_SIGNAL": "НЕМАЄ ЧІТКОГО СИГНАЛУ",
        "action.DEPRIORITISE": "НЕ ПРІОРИТЕТ",
        "action.INSUFFICIENT_EVIDENCE": "ЗАМАЛО ДАНИХ",
        "short.PRIORITISE": "Перевіряйте попит уже зараз",
        "short.PROMISING": "Перспективно, але ще не підтверджено",
        "short.STABLE": "Стабільна аудиторія, але не ставка на зростання",
        "short.NO_CLEAR_SIGNAL": "Чіткого сигналу немає",
        "short.DEPRIORITISE": "Не інвестуйте на підставі цього сигналу",
        "short.INSUFFICIENT_EVIDENCE": "Замало даних для рішення",
        "headline.PRIORITISE": "Інтерес до {what} зростає понад загальний рух платформи",
        "headline.PROMISING": "Інтерес до {what}, можливо, зростає, але діапазон усе ще включає нуль",
        "headline.STABLE": "Інтерес до {what} тримається на рівні решти розділу",
        "headline.NO_CLEAR_SIGNAL": "Інтерес до {what} змінився, але недостатньо послідовно, щоб визначити напрям",
        "headline.DEPRIORITISE": "Інтерес до {what} падає швидше, ніж сама платформа",
        "headline.INSUFFICIENT_EVIDENCE": "Даних щодо {what} замало для висновку",
        "headline.softening": ", хоча трохи слабшає (увесь діапазон нижче нуля)",
        "headline.slight_gain": ", з невеликим реальним приростом (увесь діапазон вище нуля)",
        "headline.figures": "частка трафіку розділу {share} (90% діапазон {range}), ",
        "headline.full": "{short}. {sentence}: {figures}впевненість {confidence}/100.",
        "what": "статті «{title}» {edition}",
        "range": "від {low} до {high}",
        "range.none": "діапазону немає (менше 24 місяців даних)",
        "ev.period.none": "оцінка тренду, менше 24 місяців",
        "ev.period": "{recent} проти {previous}",
        "ev.readers": "Читачі: перегляди {raw} рік до року ({period}), медіана {median} переглядів на місяць.",
        "ev.platform": "Платформа: весь {project} змінився на {edition} за ті самі місяці, що пояснює частину зміни переглядів.",
        "ev.signal": "Сигнал саме теми: частка трафіку розділу {share} (90% діапазон {range}), тобто {meaning}.",
        "ev.meaning.below": "реальна втрата уваги, більша за спад платформи",
        "ev.meaning.above": "реальне зростання уваги, понад рух платформи",
        "ev.meaning.crosses": "напрям не встановлено: діапазон включає нуль",
        "ev.meaning.unknown": "діапазону немає",
        "ev.consistency": "Послідовність: частка перевищила той самий місяць минулого року в {up} з останніх 12 місяців (тест тренду {p}).",
        "ev.no_baseline": "Даних про весь розділ немає, тому вплив платформи неможливо відокремити.",
        "ev.intensity": "Інтенсивність: {per_million} переглядів на мільйон переглядів усього розділу.",
        "ev.timing": "Сезонність: сильний річний цикл (сила {strength}), пік у {month}.",
        "next.rerun": "Перезапустіть після публікації даних за {month} (на початку наступного місяця); це займає близько секунди.",
        "next.timing": "Якщо вирішите рухатися далі, запускайте продукт або рекламу перед піком у {month}.",
        "next.PRIORITISE": "Перевірте готовність платити до початку розробки: лендинг або лист очікування для аудиторії, яка читає {language}, з наперед узгодженим порогом успіху.",
        "next.PROMISING": "Сприймайте це як гіпотезу. Перевірте обсяг пошукових запитів {language} і проведіть невеликий рекламний тест, перш ніж виділяти бюджет.",
        "next.STABLE.size": "Вирішуйте за розміром аудиторії та відповідністю продукту, а не за динамікою: {median} читачів на місяць.",
        "next.STABLE.size_intensity": "Вирішуйте за розміром аудиторії та відповідністю продукту, а не за динамікою: {median} читачів на місяць, {per_million} на мільйон переглядів розділу.",
        "next.STABLE.search": "Порівняйте з даними про пошукові запити {language}, перш ніж ухвалювати рішення.",
        "next.NO_CLEAR_SIGNAL": "Не спирайтеся на напрям. Розширте період (--months 36) або додайте пов'язані статті, щоб отримати чіткіший сигнал.",
        "next.DEPRIORITISE.1": "Не інвестуйте на підставі цього сигналу. Якщо є стратегічні причини продовжувати, вимагайте незалежних доказів (пошукові тренди, виручка конкурентів).",
        "next.DEPRIORITISE.2": "Перевірте, чи не перейшов інтерес до суміжних тем, перш ніж відмовлятися від напряму.",
        "next.DEPRIORITISE.3": "Перевірте знову через три місяці.",
        "next.INSUFFICIENT_EVIDENCE": "Розширте питання: ширша стаття, більший мовний розділ або англійська Вікіпедія як орієнтир.",
        "change.PRIORITISE": "Знизити оцінку, якщо в наступному запуску діапазон включатиме нуль або зростання виявиться зосередженим в одноразових сплесках.",
        "change.PROMISING": "Підвищити до «ПРІОРИТЕТ», коли весь 90% діапазон буде вище нуля; знизити, якщо він опуститься нижче.",
        "change.STABLE": "Стане сигналом зростання, якщо частка зросте більш ніж на 10% рік до року і весь діапазон буде вище нуля.",
        "change.NO_CLEAR_SIGNAL": "Для напряму потрібні і зміна понад 10%, і послідовність за місяцями (p<0.05).",
        "change.DEPRIORITISE": "Переглянути, якщо частка теми в {project} перестане падати: наступний запуск, у якому діапазон включатиме нуль.",
        "change.INSUFFICIENT_EVIDENCE": "Довша історія (24+ місяці) або більша аудиторія (500+ переглядів на місяць).",
        "trust.very_small": "Дуже мала аудиторія ({median} переглядів на місяць): такі малі зміни здебільшого є шумом.",
        "trust.small": "Мала аудиторія ({median} переглядів на місяць): 50 читачів більше чи менше змінюють місячне значення приблизно на {pct}.",
        "trust.ok": "Аудиторії {median} переглядів на місяць достатньо для вимірювання.",
        "trust.crosses": "Напрям не встановлено: 90% діапазон включає нуль.",
        "trust.established.below": "Напрям встановлено: увесь 90% діапазон нижче нуля.",
        "trust.established.above": "Напрям встановлено: увесь 90% діапазон вище нуля.",
        "trust.volatile": "Великі коливання від місяця до місяця ({pct} варіації): окремі місяці мало що означають; звіт спирається на 12-місячні суми.",
        "trust.recurring": "Щорічні піки у {months} ({dates}) дають {pct} переглядів: це річний цикл, а не новини. Порівняння 12-місячних періодів уже його нівелює.",
        "trust.recurring.join": " і ",
        "trust.one_off": "Одноразові сплески {dates} дають {pct} усіх переглядів: імовірно, новини чи події, а не стійкий інтерес.",
        "trust.one_article": "Враховано одну статтю («{title}»). Читачі пов'язаних статей та інших мовних розділів, зокрема англійського, не враховані.",
        "trust.curiosity": "Перегляди показують цікавість, а не готовність платити: підтвердьте попит, перш ніж будувати продукт.",
        "risk.high": "ВИСОКИЙ", "risk.medium": "СЕРЕДНІЙ", "risk.low": "НИЗЬКИЙ",
        "overall.best": "Найкращий кандидат: {label}. {headline}",
        "overall.ties": " Його перевага над {labels} у межах шуму; вважайте їх рівноцінними кандидатами.",
        "overall.clear": " Його перевага над іншими кандидатами виходить за межі 90% діапазонів.",
        "overall.dropped": " Не пріоритет: {labels}.",
        "overall.thin": " Замало даних: {labels}.",
        "memo.title": "Аналітична записка: {topics} {editions}",
        "memo.subtitle": "Аналітична записка · перегляди Вікіпедії з {start} по {end}, лише люди · створено {today} · джерело: Wikimedia Pageviews API",
        "memo.question": "Питання:",
        "memo.recommendation": "РЕКОМЕНДАЦІЯ: {action}",
        "memo.analyst_note": "Примітка аналітика:",
        "memo.why": "Чому: докази для {label}",
        "memo.next": "Що робити далі",
        "memo.change": "Що змінило б цей висновок",
        "memo.trust": "Наскільки цьому можна довіряти",
        "memo.assumptions": "Припущення, на яких ґрунтуються цифри",
        "memo.method": "Метод.",
        "memo.rules": "Правила ухвалення рішень фіксовані й описані в references/ANALYSIS_METHODS.md; ті самі дані завжди дають ту саму рекомендацію.",
        "memo.reproduce": "Відтворити:",
        "memo.footer": "Інтерес читачів Вікіпедії — це сигнал для дослідження, а не доказ попиту.",
        "ask.pdf": "Чи згенерувати також односторінковий PDF цього звіту?",
        "memo.method_note": "Напрям визначено тестом тренду Манна–Кендалла за всі місяці (а не порівнянням першого й останнього); величину — нахилом Тейла–Сена та порівнянням 12-місячних періодів рік до року, що нівелює сезонність. Сплески виявлено тестом викидів на основі медіанного абсолютного відхилення. Показники різних розділів нормалізовано до переглядів на мільйон переглядів розділу. Діапазони — 90% інтервали, отримані повторною вибіркою парних місяців; якщо діапазони перекриваються, розділи не відрізняються чітко.",
        "score.edition": "Розділ / стаття", "score.action": "Рекомендація", "score.readers": "Читачів на місяць",
        "score.share": "Зміна частки (90% діапазон)", "score.months_up": "Місяців зростання (з 12)",
        "score.confidence": "Впевненість", "score.no_data": "НЕМАЄ ДАНИХ",
        "edition.one": "в {name} Вікіпедії",
        "edition.many": "у Вікіпедії: {names}",
        "chart.share": "Частка трафіку розділу (переглядів на мільйон), ковзне середнє за 3 місяці",
        "chart.vs": "Тема проти всього розділу (індекс: перші 12 місяців = 100, середнє за 3 місяці)",
        "chart.vs.edition": "увесь {project}",
        "chart.vs.topic": "читачі «{title}»",
        "chart.range": "Зміна частки: останні 12 проти попередніх 12 місяців\n(стовпчик — оцінка, вуса — 90% діапазон)",
        "assume.articles": "Одна стаття на розділ, зіставлена за тим самим поняттям через Wikidata ({source}). Пов'язані статті та перенаправлення не враховано.",
        "assume.source": "«{topic}» = Wikidata {qid}",
        "assume.articles_given": "Статті задано явно (--articles); зіставлення понять не виконувалося.",
        "assume.traffic": "Трафік: лише люди (боти й пошукові роботи виключені), усі пристрої, повні місяці {start}..{end}.",
        "assume.growth": "Зростання = останні 12 місяців проти попередніх 12 (сезонність нівелюється), з 90% інтервалом, отриманим повторною вибіркою місяців. «Стабільно» означає в межах ±{band}%; для тренду також потрібно p<{p}.",
        "assume.share": "Розділи порівнюються за часткою їхнього власного трафіку (переглядів на мільйон переглядів розділу), бо загальний трафік Вікіпедії падає різними темпами в різних мовах.",
    },
}

# Ukrainian adjective stems for editions ("українськ" -> "українській" / "українська").
UK_STEMS = {
    "en": "англійськ", "de": "німецьк", "fr": "французьк", "es": "іспанськ", "pt": "португальськ",
    "it": "італійськ", "nl": "нідерландськ", "pl": "польськ", "cs": "чеськ", "sk": "словацьк",
    "uk": "українськ", "ru": "російськ", "tr": "турецьк", "ro": "румунськ", "hu": "угорськ",
    "sv": "шведськ", "fi": "фінськ", "da": "данськ", "no": "норвезьк", "el": "грецьк",
    "bg": "болгарськ", "hr": "хорватськ", "sr": "сербськ", "ar": "арабськ", "fa": "перськ",
    "id": "індонезійськ", "vi": "в'єтнамськ", "th": "тайськ", "ja": "японськ", "ko": "корейськ",
    "zh": "китайськ",
}


class Translator:
    """tr("key", **values) -> sentence in the report language, English if missing."""

    def __init__(self, lang: str = "en"):
        self.lang = lang if lang in SUPPORTED else "en"

    def __call__(self, key: str, **values: Any) -> str:
        template = CATALOG[self.lang].get(key, CATALOG["en"][key])
        return template.format(**values)

    def month(self, mm: Optional[str]) -> Optional[str]:
        return MONTHS[self.lang][int(mm) - 1] if mm else None

    def edition(self, code: str, english_name: str) -> str:
        """'Ukrainian Wikipedia' / 'в українській Вікіпедії'."""
        if self.lang == "uk":
            stem = UK_STEMS.get(code)
            return self("edition.one", name=f"{stem}ій") if stem else f"у Вікіпедії ({code})"
        return self("edition.one", name=english_name)

    def language(self, code: str, english_name: str) -> str:
        """The language itself, as used in 'search volume in Turkish' / 'запити турецькою мовою'."""
        if self.lang == "uk":
            stem = UK_STEMS.get(code)
            return f"{stem}ою мовою" if stem else f"мовою «{code}»"
        return english_name

    def editions(self, codes, english_names) -> str:
        if len(codes) == 1:
            return self.edition(codes[0], english_names[0])
        if self.lang == "uk":
            names = ", ".join(f"{UK_STEMS[c]}а" if c in UK_STEMS else c for c in codes)
            return self("edition.many", names=names)
        return self("edition.many", names=", ".join(english_names))


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


def detect_language(text: str) -> str:
    """Best guess at the language of a user's request. Returns a code, not only supported ones."""
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


def placeholders(template: str) -> set:
    return {name for _, name, _, _ in string.Formatter().parse(template) if name}
