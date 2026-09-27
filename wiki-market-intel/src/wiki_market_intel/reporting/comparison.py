"""Language comparison report (spec §14-§18, §23, §24.6-§24.7), in the report language."""

from __future__ import annotations

from jinja2 import Environment, StrictUndefined

from wiki_market_intel.analytics import recommend
from wiki_market_intel.analytics import signals as signal_kpis
from wiki_market_intel.reporting import breakdown
from wiki_market_intel.analytics.summary import comparison_observations
from wiki_market_intel.i18n import Translator
from wiki_market_intel.models.analysis import ComparisonResult

TEMPLATE = """\
# {{ t("cmp_title", topic=c.resolution.canonical_topic or c.metadata.topic) }}

_{{ t("cmp_meta", editions=editions, start=c.metadata.period_start, end=c.metadata.period_end, generated=c.metadata.generated_at) }}_

## {{ t("rec_title") }}

**{{ rec_lines[0] }}**

{% for line in rec_lines[1:-1] -%}
- {{ line }}
{% endfor %}
{{ rec_lines[-1] }}

_{{ rec_rule }}_

## {{ t("graph_title") }}

{% if matrix %}![{{ t("matrix_alt") }}]({{ matrix }})
{% endif %}
{% if penetration %}![{{ t("pen_alt") }}]({{ penetration }})
{% endif %}
{{ t("matrix_intro") }} {{ t("matrix_split", threshold=num(c.demand_threshold)) }}
{{ t("matrix_labels") }}

## {{ t("observations") }}

{% for o in observations -%}
- {{ o }}
{% endfor %}
{% for n in notes -%}
- {{ n }}
{% endfor %}
## {{ t("kpi_title") }}

{% for line in kpi_lines -%}
- {{ line }}
{% endfor %}
| {{ t("col_edition") }} | {{ t("col_article") }} | {{ t("col_views") }} | {{ t("col_yoy") }} | {{ t("col_cagr") }} | {{ t("col_share") }} | {{ t("col_pen") }} | {{ t("col_aff") }} | {{ t("col_quadrant") }} | {{ t("col_anomalies") }} |
|---|---|---:|---:|---:|---:|---:|---:|---|---|
{% for r in c.rows -%}
{% set a = c.analyses.get(r.language) -%}
{% if r.status != "ok" -%}
| {{ r.project }} | {{ t("row." ~ r.status) }} | | | | | | | | |
{% else -%}
| {{ r.project }} | {{ c.resolution.articles[r.language].title if c.resolution.articles.get(r.language) else t("na") }} | {{ num(r.annual_views) }} | {{ rate(r.yoy_growth) }} | {{ rate(r.three_year_cagr) }} | {{ rate(r.topic_share, False) }} | {{ per_m(r.topic_penetration) }} | {{ dec(r.topic_affinity) }} | {{ t("quadrant." ~ r.quadrant) if r.quadrant else t("na") }} | {% if a and a.anomalies %}{% for x in a.anomalies %}{{ x.date }} {{ rate(x.change_vs_baseline) }}{% if not loop.last %}; {% endif %}{% endfor %}{% elif a %}0{% else %}{{ t("na") }}{% endif %} |
{% endif -%}
{% endfor %}
{{ t("def_aff") }}
{{ t("sig_intro") }}
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
    rec = c.recommendation or recommend.of_comparison(c)
    return env.from_string(TEMPLATE).render(
        c=c, matrix=matrix, penetration=penetration, notes=_notes(c, tr),
        rec_lines=recommend.sentences(rec, tr), rec_rule=recommend.rule_text(rec, tr),
        kpi_lines=breakdown.multi_lines(breakdown.comparison_units(c), tr),
        editions=", ".join(f"{l}.wikipedia" for l in c.metadata.languages),
        observations=comparison_observations(c.rows, tr))
