"""Portfolio report (spec §36-§37), in the report language."""

from __future__ import annotations

from jinja2 import Environment, StrictUndefined

from wiki_market_intel.analytics import portfolio as portfolio_kpis
from wiki_market_intel.analytics import signals as signal_kpis
from wiki_market_intel.i18n import Translator
from wiki_market_intel.models.analysis import PortfolioResult

TEMPLATE = """\
# {{ t("pf_title", name=p.metadata.name) }}

_{{ t("pf_meta", topics=topics, editions=editions, start=p.metadata.period_start, end=p.metadata.period_end, generated=p.metadata.generated_at) }}_

## {{ t("p1") }}

{% for o in observations -%}
- {{ o }}
{% endfor %}
## {{ t("p2") }}

{{ t("pf_matrix_intro") }}

| {{ t("pf_col_topic") }} |{% if has_categories %} {{ t("pf_col_category") }} |{% endif %} {{ t("col_edition") }} | {{ t("col_views") }} | {{ t("col_yoy") }} | {{ t("col_cagr") }} | {{ t("col_3m") }} | {{ t("momentum") }} | {{ t("col_aff") }} | {{ t("col_quadrant") }} |
|---|{% if has_categories %}---|{% endif %}---|---:|---:|---:|---:|---|---:|---|
{% for r in shown -%}
| {{ r.canonical_topic or r.topic }} |{% if has_categories %} {{ r.category or "" }} |{% endif %} {{ r.project }} | {{ num(r.annual_views) }} | {{ rate(r.yoy_growth) }} | {{ rate(r.three_year_cagr) }} | {{ rate(r.three_month_growth) }} | {{ t("momentum." ~ r.momentum) if r.momentum else t("na") }} | {{ dec(r.topic_affinity) }} | {{ t("quadrant." ~ r.quadrant) if r.quadrant else t("na") }} |
{% endfor %}
{% if chart %}![{{ t("pf_alt") }}]({{ chart }})

{% endif -%}
{% if p.demand_threshold is not none %}{{ t("pf_split", threshold=num(p.demand_threshold)) }}
{% endif %}
{% for q in ("investigate", "explore", "established", "watch") -%}
- **{{ t("quadrant." ~ q) }}**: {{ t("qdesc." ~ q) }}
{% endfor %}
{{ t("matrix_labels") }}

## {{ t("p3") }}

{{ t("sig_intro") }}

| {{ t("pf_col_topic") }} | {{ t("col_edition") }} |{% for n in sig_names %} {{ t("sig_name." ~ n) }} |{% endfor %}
|---|---|---|---|---|---|---|
{% for r in shown -%}
| {{ r.canonical_topic or r.topic }} | {{ r.project }} |{% for n in sig_names %}{% set v = r.signals[n] if r.signals else none %} {{ t("sig." ~ n ~ "." ~ v) if v else t("na") }} |{% endfor %}
{% endfor %}
{{ t("sig_rules") }}

## {{ t("p4") }}

{{ filters_text }}

{% if hidden -%}
{{ t("pf_excluded_intro") }}

| {{ t("pf_col_topic") }} | {{ t("col_edition") }} | {{ t("pf_col_reason") }} |
|---|---|---|
{% for r in hidden -%}
| {{ r.canonical_topic or r.topic }} | {{ r.project }} | {{ t("pf_ex." ~ (r.excluded_by | replace(":", "."))) }} |
{% endfor %}
{% else -%}
{{ t("pf_no_excluded") }}
{% endif %}
{{ t("pf_country") }}

## {{ t("p5") }}

| {{ t("pf_col_topic") }} | {{ t("canonical") }} | {{ t("wikidata") }} | {{ t("pf_col_articles") }} |
|---|---|---|---|
{% for item in p.metadata.topics -%}
{% set c = p.comparisons.get(item.topic) -%}
{% set a = p.analyses.get(item.topic) -%}
{% if c -%}
| {{ item.topic }} | {{ c.resolution.canonical_topic or t("na") }} | {{ c.resolution.wikidata_id or t("no_wikidata") }} | {% for lang, art in c.resolution.articles.items() %}{{ lang }}: {{ art.title }}{% if not loop.last %}, {% endif %}{% endfor %} |
{% elif a -%}
| {{ item.topic }} | {{ a.topic.canonical_name or t("na") }} | {{ a.topic.wikidata_id or t("no_wikidata") }} | {{ a.metadata.language }}: {{ a.topic.article_title }} |
{% else -%}
| {{ item.topic }} | {{ t("na") }} | {{ t("na") }} | {{ t("na") }} |
{% endif -%}
{% endfor %}
## {{ t("p6") }}

| {{ t("pf_col_topic") }} | {{ t("col_edition") }} | {{ t("col_status") }} | {{ t("col_quality") }} | {{ t("col_anomalies") }} |
|---|---|---|---|---:|
{% for r in p.rows -%}
| {{ r.canonical_topic or r.topic }} | {{ r.project }} | {{ "OK" if r.status == "ok" else t("pf_ex.status." ~ r.status) }} | {{ t("level." ~ r.quality_level) if r.quality_level else t("na") }} | {{ r.anomaly_count if r.anomaly_count is not none else t("na") }} |
{% endfor %}
## {{ t("p7") }}

### {{ t("supports") }}

{% for o in observations -%}
- {{ o }}
{% endfor %}
### {{ t("not_establish") }}

- {{ t("ne1") }}
- {{ t("pf_ne_rank") }}
- {{ t("ne3") }}
- {{ t("pf_country") }}

### {{ t("validate") }}

- {{ t("q1") }}
- {{ t("q2") }}
- {{ t("q3") }}
- {{ t("q4") }}
- {{ t("q5") }}
"""


def _filters_text(p: PortfolioResult, tr: Translator) -> str:
    f = p.metadata.filters
    parts = []
    if f.min_views is not None:
        parts.append(tr("pf_f_min_views", n=tr.number(f.min_views)))
    if f.min_growth is not None:
        parts.append(tr("pf_f_min_growth", pct=tr.percent(f.min_growth)))
    if f.categories:
        parts.append(tr("pf_f_categories", names=", ".join(f.categories)))
    return tr("pf_filters", filters="; ".join(parts)) if parts else tr("pf_filters_none")


def render(p: PortfolioResult, chart: str | None, lang: str = "en") -> str:
    tr = Translator(lang)

    def num(value) -> str:
        return tr.number(value) if value is not None else tr("na")

    def rate(value) -> str:
        return tr.percent(value) if value is not None else tr("na")

    def dec(value) -> str:
        return tr.decimal(value) if value is not None else tr("na")

    env = Environment(undefined=StrictUndefined, autoescape=False)
    env.globals.update(t=tr, num=num, rate=rate, dec=dec, sig_names=signal_kpis.SIGNAL_NAMES)
    shown = p.visible
    return env.from_string(TEMPLATE).render(
        p=p, chart=chart, shown=shown, hidden=[r for r in p.rows if r.excluded_by],
        has_categories=any(t.category for t in p.metadata.topics),
        topics=", ".join(t.topic for t in p.metadata.topics),
        editions=", ".join(f"{l}.wikipedia" for l in p.metadata.languages),
        observations=portfolio_kpis.observations(p.rows, tr), filters_text=_filters_text(p, tr))
