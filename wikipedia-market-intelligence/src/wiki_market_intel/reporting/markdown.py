"""Markdown report in the fixed order of spec §24.

Every section always appears. When a metric is missing, the report shows why
(unsupported, insufficient data, not implemented yet) instead of a blank or a zero.
"""

from __future__ import annotations

from jinja2 import Environment, StrictUndefined

from wiki_market_intel.analytics.summary import compact, pct
from wiki_market_intel.models.analysis import AnalysisResult

TEMPLATE = """\
# Wikipedia Market Intelligence Report

## 1. Executive Decision Card

| | |
|---|---|
| Topic | {{ r.topic.canonical_name or r.metadata.topic }} |
| Language edition | {{ r.metadata.project }} (a language edition, not a country) |
| Analysis period | {{ r.metadata.period_start }} to {{ r.metadata.period_end }} |
| Annual views (last 12 months) | {{ num(r.demand.annual_views, "demand.annual_views") }} |
| Monthly average | {{ num(r.demand.monthly_average, "demand.annual_views") }} |
| Unique devices | {{ num(r.demand.unique_devices, "demand.unique_devices") }} |
| YoY | {{ rate(r.growth.yoy, "growth.yoy") }} |
| 3Y CAGR | {{ rate(r.growth.three_year_cagr, "growth.three_year_cagr") }} |
| Momentum | {{ r.growth.momentum or missing("growth.last_three_month_growth") }} |
| Seasonality | {% if r.seasonality.peak_month %}peak {{ r.seasonality.peak_month }}, trough {{ r.seasonality.trough_month }}{% else %}{{ missing("seasonality.peak_month") }}{% endif %} |
| Localization metrics | {{ missing("localization.topic_penetration") }} |
| Data quality | **{{ r.quality.quality_level }}** ({{ r.quality.quality_reasons | join("; ") }}) |

### Key observations

{% for o in r.observations -%}
- {{ o }}
{% else -%}
- No observation could be computed: see Data Quality.
{% endfor %}
## 2. Topic Definition

| | |
|---|---|
| Canonical topic | {{ r.topic.canonical_name or "n/a" }} |
| Wikidata ID | {{ r.topic.wikidata_id or "n/a (no Wikidata entity)" }} |
| Article used | {{ r.topic.article_title }} (page ID {{ r.topic.article_id or "n/a" }}) |
| Resolution method | {{ r.topic.resolution.method }} |
| Resolution confidence | {{ "%.2f" % r.topic.resolution_confidence }} |
| Language mappings | {% for lang, a in r.topic.resolution.articles.items() %}{{ lang }}: {{ a.title }}{% if not loop.last %}, {% endif %}{% endfor %} |
| Related topics | {{ missing("ecosystem.related_topics") }} |
{% for n in r.topic.resolution.notes %}
> {{ n }}
{% endfor %}
## 3. Demand

| KPI | Value |
|---|---:|
| Annual views (last 12 months) | {{ num(r.demand.annual_views, "demand.annual_views") }} |
| Monthly average | {{ num(r.demand.monthly_average, "demand.annual_views") }} |
| Daily average | {{ num(r.demand.daily_average, "demand.annual_views") }} |
| Views in the requested period | {{ num(r.demand.requested_period_views, "demand.requested_period_views") }} |
| Unique devices | {{ num(r.demand.unique_devices, "demand.unique_devices") }} |
| Views per unique device | {{ num(r.demand.views_per_unique_device, "demand.views_per_unique_device") }} |

{% if chart %}![Monthly pageviews]({{ chart }})
{% else %}_Trend chart unavailable: no months with data in the requested period._
{% endif %}
## 4. Growth

| KPI | Value |
|---|---:|
| YoY (last 12M vs previous 12M) | {{ rate(r.growth.yoy, "growth.yoy") }} |
| 3Y CAGR | {{ rate(r.growth.three_year_cagr, "growth.three_year_cagr") }} |
| Last 3M vs previous 3M | {{ rate(r.growth.last_three_month_growth, "growth.last_three_month_growth") }} |
| Previous 3M vs the 3M before | {{ rate(r.growth.previous_three_month_growth, "growth.previous_three_month_growth") }} |
| Acceleration | {% if r.growth.acceleration is not none %}{{ "%+.1f" % (r.growth.acceleration * 100) }} pp ({{ r.growth.momentum }}){% else %}n/a{% endif %} |
| Requested period vs previous equivalent period | {{ rate(r.growth.period_over_period, "growth.period_over_period") }} |

These are historical measurements, not forecasts. A growth chart is planned for a later milestone; the Demand chart shows the trend.

## 5. Seasonality

| KPI | Value |
|---|---:|
| Peak month | {{ r.seasonality.peak_month or missing("seasonality.peak_month") }} |
| Trough month | {{ r.seasonality.trough_month or missing("seasonality.peak_month") }} |
| Peak / average | {{ ratio(r.seasonality.peak_to_average) }} |
| Trough / average | {{ ratio(r.seasonality.trough_to_average) }} |
| Volatility (coefficient of variation) | {{ ratio(r.seasonality.volatility) }} |

{% if r.seasonality.basis %}Basis: {{ r.seasonality.basis }}.{% endif %}

## 6. Language Opportunity

{{ missing("localization.topic_share") }}

## 7. Localization

| Metric | Value |
|---|---|
| Wikipedia topic penetration | {{ missing("localization.topic_penetration") }} |
| Topic affinity | {{ missing("localization.topic_affinity") }} |
| Country distribution | {{ missing("localization.country_distribution") }} |

A language edition is not a country: {{ r.metadata.project }} is read wherever that language is read.

## 8. Topic Ecosystem

{{ missing("ecosystem.related_topics") }}

## 9. Anomalies

{{ missing("anomalies") }}

## 10. Data Quality

| | |
|---|---|
| Source | Wikimedia Analytics API ({{ r.metadata.api }}), access={{ r.metadata.access }}, agent={{ r.metadata.agent }} |
| Data retrieved | {{ r.metadata.data_retrieved_at }} |
| Report generated | {{ r.metadata.generated_at }} (software {{ r.metadata.software_version }}) |
| Coverage | {{ "%.1f%%" % (r.quality.coverage * 100) if r.quality.coverage is not none else "n/a" }} |
| Missing data | {{ r.quality.missing_data | join("; ") if r.quality.missing_data else "none" }} |
| Topic resolution confidence | {{ "%.2f" % r.quality.topic_resolution_confidence }} |
| Unique devices available | {{ "yes" if r.quality.unique_devices_available else "no" }} |
| Country data available | {{ "yes" if r.quality.country_data_available else "no" }} |
| Project-level denominator available | {{ "yes" if r.quality.project_denominator_available else "no" }} |
| API errors | {{ r.quality.api_errors | join("; ") if r.quality.api_errors else "none" }} |
| Quality level | **{{ r.quality.quality_level }}**: {{ r.quality.quality_reasons | join("; ") }} |

Metrics not computed:

| Metric | Status | Reason |
|---|---|---|
{% for m in r.quality.missing_metrics -%}
| {{ m.metric }} | {{ m.status }} | {{ m.reason }} |
{% endfor %}
Raw responses: {% for s in r.sources %}`{{ s.raw_path }}`{% if not loop.last %}, {% endif %}{% endfor %}

## 11. Business Implications

### What the data supports

{% for o in r.observations -%}
- {{ o }}
{% endfor -%}
- These figures describe reader attention to one Wikipedia article in {{ r.metadata.project }}.

### What the data does NOT establish

- Revenue, market size (TAM) or willingness to pay: pageviews measure attention, not purchasing.
- Product-market fit, or that a product on this topic would succeed.
- Causes of any change: the data shows that traffic moved, not why.
- Country-level demand: {{ r.metadata.project }} readers are not one country's population.
- That readers of related articles, or of other language editions, share this trend.

### Questions requiring further validation

- Does search volume (e.g. Google Trends) show the same direction in this language?
- Is there App Store / Google Play demand for products on this topic in this language?
- What do competitors in this category earn, and how large is the addressable market?
- Will people pay? What do customer interviews and landing-page conversion rates show?
- What would customer acquisition cost, retention and monetization look like?
"""


def render(result: AnalysisResult, chart_path: str | None = None) -> str:
    reasons = {m.metric: m for m in result.quality.missing_metrics}

    def missing(metric: str) -> str:
        m = reasons.get(metric)
        return f"n/a ({m.status.replace('_', ' ')}: {m.reason})" if m else "n/a"

    def num(value, metric: str) -> str:
        if value is None:
            return missing(metric)
        return f"{value:,.0f}" if abs(value) >= 100 else f"{value:,.1f}"

    def rate(value, metric: str) -> str:
        return pct(value) if value is not None else missing(metric)

    def ratio(value) -> str:
        return f"{value:.2f}" if value is not None else "n/a"

    env = Environment(undefined=StrictUndefined, trim_blocks=False, lstrip_blocks=False, autoescape=False)
    env.globals.update(missing=missing, num=num, rate=rate, ratio=ratio, compact=compact)
    return env.from_string(TEMPLATE).render(r=result, chart=chart_path)
