"""Portfolio report (spec §36-§37), in the report language."""

from __future__ import annotations

from jinja2 import Environment, StrictUndefined

from wiki_market_intel.analytics import portfolio as portfolio_kpis
from wiki_market_intel.analytics import recommend
from wiki_market_intel.analytics import signals as signal_kpis
from wiki_market_intel.reporting import breakdown
from wiki_market_intel.i18n import Translator
from wiki_market_intel.models.analysis import PortfolioResult

TEMPLATE = """\
# {{ t("pf_title", name=p.metadata.name) }}

_{{ t("pf_meta", topics=topics, editions=editions, start=p.metadata.period_start, end=p.metadata.period_end, generated=p.metadata.generated_at) }}_

## {{ t("rec_title") }}

**{{ rec_lines[0] }}**

{% for line in rec_lines[1:-1] -%}
- {{ line }}
{% endfor %}
{{ rec_lines[-1] }}

_{{ rec_rule }}_

## {{ t("graph_title") }}

{% if chart %}![{{ t("pf_alt") }}]({{ chart }})
{% endif %}
{% if p.demand_threshold is not none %}{{ t("pf_split", threshold=num(p.demand_threshold)) }}
{% endif %}
{{ t("matrix_labels") }}

## {{ t("observations") }}

{% for o in observations -%}
- {{ o }}
{% endfor %}
## {{ t("kpi_title") }}

{% for line in kpi_lines -%}
- {{ line }}
{% endfor %}
{{ t("pf_matrix_intro") }}

| {{ t("pf_col_topic") }} |{% if has_categories %} {{ t("pf_col_category") }} |{% endif %} {{ t("col_edition") }} | {{ t("col_views") }} | {{ t("col_yoy") }} | {{ t("col_cagr") }} | {{ t("col_3m") }} | {{ t("momentum") }} | {{ t("col_aff") }} | {{ t("col_quadrant") }} |
|---|{% if has_categories %}---|{% endif %}---|---:|---:|---:|---:|---|---:|---|
{% for r in shown -%}
| {{ r.canonical_topic or r.topic }} |{% if has_categories %} {{ r.category or "" }} |{% endif %} {{ r.project }} | {{ num(r.annual_views) }} | {{ rate(r.yoy_growth) }} | {{ rate(r.three_year_cagr) }} | {{ rate(r.three_month_growth) }} | {{ t("momentum." ~ r.momentum) if r.momentum else t("na") }} | {{ dec(r.topic_affinity) }} | {{ t("quadrant." ~ r.quadrant) if r.quadrant else t("na") }} |
{% endfor %}
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
    rec = p.recommendation or recommend.of_portfolio(p)
    return env.from_string(TEMPLATE).render(
        rec_lines=recommend.sentences(rec, tr), rec_rule=recommend.rule_text(rec, tr),
        kpi_lines=breakdown.multi_lines(breakdown.portfolio_units(p), tr),
        p=p, chart=chart, shown=shown, hidden=[r for r in p.rows if r.excluded_by],
        has_categories=any(t.category for t in p.metadata.topics),
        topics=", ".join(t.topic for t in p.metadata.topics),
        editions=", ".join(f"{l}.wikipedia" for l in p.metadata.languages),
        observations=portfolio_kpis.observations(p.rows, tr), filters_text=_filters_text(p, tr))
