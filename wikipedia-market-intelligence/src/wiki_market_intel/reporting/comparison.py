"""Language comparison report (spec §14-§18, §23, §24.6-§24.7), in the report language."""

from __future__ import annotations

from jinja2 import Environment, StrictUndefined

from wiki_market_intel.analytics import signals as signal_kpis
from wiki_market_intel.analytics.summary import comparison_observations
from wiki_market_intel.i18n import Translator
from wiki_market_intel.models.analysis import ComparisonResult

TEMPLATE = """\
# {{ t("cmp_title", topic=c.resolution.canonical_topic or c.metadata.topic) }}

_{{ t("cmp_meta", editions=editions, start=c.metadata.period_start, end=c.metadata.period_end, generated=c.metadata.generated_at) }}_

## {{ t("c1") }}

{% for o in observations -%}
- {{ o }}
{% endfor %}
## {{ t("c2") }}

| | |
|---|---|
| {{ t("canonical") }} | {{ c.resolution.canonical_topic or t("na") }} |
| {{ t("wikidata") }} | {{ c.resolution.wikidata_id or t("no_wikidata") }} |
| {{ t("method") }} | {{ t("method." ~ c.resolution.method) }} |
| {{ t("confidence") }} | {{ dec(c.resolution.confidence) }} |

| {{ t("col_edition") }} | {{ t("col_article") }} | {{ t("col_page") }} |
|---|---|---:|
{% for lang in c.metadata.languages -%}
{% set a = c.resolution.articles.get(lang) -%}
| {{ lang }}.wikipedia | {{ a.title if a else t("row.no_article") }} | {{ a.page_id if a and a.page_id else "" }} |
{% endfor %}
## {{ t("c3") }}

| {{ t("col_edition") }} | {{ t("col_views") }} | {{ t("col_yoy") }} | {{ t("col_cagr") }} | {{ t("col_3m") }} | {{ t("col_unique") }} | {{ t("col_share") }} | {{ t("col_pen") }} | {{ t("col_aff") }} | {{ t("col_quadrant") }} |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
{% for r in c.rows -%}
{% if r.status != "ok" -%}
| {{ r.project }} | {{ t("row." ~ r.status) }} | | | | | | | | |
{% else -%}
| {{ r.project }} | {{ num(r.annual_views) }} | {{ rate(r.yoy_growth) }} | {{ rate(r.three_year_cagr) }} | {{ rate(r.three_month_growth) }} | {{ t("na") }} | {{ rate(r.topic_share, False) }} | {{ per_m(r.topic_penetration) }} | {{ dec(r.topic_affinity) }} | {{ t("quadrant." ~ r.quadrant) if r.quadrant else t("na") }} |
{% endif -%}
{% endfor %}
### {{ t("sig_title") }}

{{ t("sig_intro") }}

| {{ t("col_edition") }} |{% for n in sig_names %} {{ t("sig_name." ~ n) }} |{% endfor %}
|---|---|---|---|---|---|
{% for lang, a in c.analyses.items() -%}
| {{ a.metadata.project }} |{% for n in sig_names %}{% set v = a.signals[n] %} {{ t("sig." ~ n ~ "." ~ v) if v else t("na") }} |{% endfor %}
{% endfor %}
{{ t("sig_rules") }}

## {{ t("c4") }}

{% if matrix %}![{{ t("matrix_alt") }}]({{ matrix }})
{% endif %}
{{ t("matrix_intro") }} {{ t("matrix_split", threshold=num(c.demand_threshold)) }}

{% for q in ("investigate", "explore", "established", "watch") -%}
- **{{ t("quadrant." ~ q) }}**: {{ t("qdesc." ~ q) }}
{% endfor %}
{{ t("matrix_labels") }}

## {{ t("c5") }}

{% if penetration %}![{{ t("pen_alt") }}]({{ penetration }})

{% endif %}{{ t("pen_intro") }}

- {{ t("def_country") }}
{% for r in c.rows if r.status == "ok" -%}
- {{ t("cmp_ne_country", project=r.project) }}
{% endfor %}
## {{ t("c6") }}

- {{ t("def_share") }}
- {{ t("def_pen") }}
- {{ t("def_aff") }}
- {{ t("def_unique") }}

## {{ t("c7") }}

| {{ t("col_edition") }} | {{ t("col_status") }} | {{ t("col_coverage") }} | {{ t("col_quality") }} | {{ t("col_anomalies") }} |
|---|---|---:|---|---|
{% for r in c.rows -%}
{% set a = c.analyses.get(r.language) -%}
| {{ r.project }} | {{ t("row." ~ r.status) if r.status != "ok" else "OK" }} | {{ rate(a.quality.coverage, False) if a else t("na") }} | {{ t("level." ~ r.quality_level) if r.quality_level else t("na") }} | {% if a and a.anomalies %}{% for x in a.anomalies %}{{ x.date }} {{ rate(x.change_vs_baseline) }}{% if not loop.last %}; {% endif %}{% endfor %}{% elif a %}0{% else %}{{ t("na") }}{% endif %} |
{% endfor %}
{% if c.notes %}
### {{ t("notes") }}

{% for n in notes -%}
- {{ n }}
{% endfor %}{% endif %}
## {{ t("c8") }}

### {{ t("supports") }}

{% for o in observations -%}
- {{ o }}
{% endfor %}
### {{ t("not_establish") }}

- {{ t("ne1") }}
- {{ t("cmp_ne_rank") }}
- {{ t("ne3") }}
- {{ t("ne5") }}

### {{ t("validate") }}

- {{ t("q1") }}
- {{ t("q2") }}
- {{ t("q3") }}
- {{ t("q4") }}
- {{ t("q5") }}
"""


def _notes(c: ComparisonResult, tr: Translator) -> list[str]:
    """Comparison notes in the report language, rebuilt from the data (not the English JSON)."""
    if tr.lang == "en":
        return c.notes
    notes = []
    missing = [r.project for r in c.rows if r.status == "no_article"]
    if missing:
        notes.append(tr("missing_langs", langs=", ".join(missing)))
    return notes


def render(c: ComparisonResult, matrix: str | None, penetration: str | None, lang: str = "en") -> str:
    tr = Translator(lang)

    def num(value) -> str:
        return tr.number(value) if value is not None else tr("na")

    def rate(value, signed: bool = True) -> str:
        return tr.percent(value, signed) if value is not None else tr("na")

    def dec(value) -> str:
        return tr.decimal(value) if value is not None else tr("na")

    def per_m(value) -> str:
        return tr.decimal(value * 1_000_000, 1) if value is not None else tr("na")

    env = Environment(undefined=StrictUndefined, autoescape=False, trim_blocks=False)
    env.globals.update(t=tr, num=num, rate=rate, dec=dec, per_m=per_m, sig_names=signal_kpis.SIGNAL_NAMES)
    return env.from_string(TEMPLATE).render(
        c=c, matrix=matrix, penetration=penetration, notes=_notes(c, tr),
        editions=", ".join(f"{l}.wikipedia" for l in c.metadata.languages),
        observations=comparison_observations(c.rows, tr))
