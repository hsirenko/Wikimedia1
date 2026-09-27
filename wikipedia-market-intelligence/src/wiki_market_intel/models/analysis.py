"""The machine-readable result of one analysis (spec §26, §29)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from wiki_market_intel.models.metrics import (
    Demand, Formula, Growth, Localization, MissingMetric, MonthlyPoint, PeriodRef, Seasonality, Signals,
)
from wiki_market_intel.models.topic import TopicResolution


class SourceRecord(BaseModel):
    """One API response the numbers came from, as stored in data/raw."""

    endpoint: str
    url: str
    retrieved_at: str
    raw_path: str


class Metadata(BaseModel):
    topic: str
    language: str
    project: str
    period_start: str
    period_end: str
    generated_at: str
    data_retrieved_at: str | None
    source: str = "Wikimedia"
    api: str
    access: str
    agent: str
    software_version: str


class TopicSection(BaseModel):
    canonical_name: str | None
    wikidata_id: str | None
    article_title: str
    article_id: str | None
    resolution_confidence: float
    resolution: TopicResolution


class Quality(BaseModel):
    coverage: float | None = None                # months with data / months expected
    missing_data: list[str] = Field(default_factory=list)
    missing_metrics: list[MissingMetric] = Field(default_factory=list)
    api_errors: list[str] = Field(default_factory=list)
    topic_resolution_confidence: float | None = None
    language_mapping_confidence: float | None = None
    anomaly_count: int | None = None
    country_data_available: bool = False
    unique_devices_available: bool = False
    project_denominator_available: bool = False
    quality_level: Literal["HIGH", "MEDIUM", "LOW"] = "LOW"
    quality_reasons: list[str] = Field(default_factory=list)


class Ecosystem(BaseModel):
    related_topics: list[dict] = Field(default_factory=list)


class AnalysisResult(BaseModel):
    metadata: Metadata
    topic: TopicSection
    periods: list[PeriodRef]
    demand: Demand
    growth: Growth
    seasonality: Seasonality
    localization: Localization = Field(default_factory=Localization)
    anomalies: list[dict] = Field(default_factory=list)
    ecosystem: Ecosystem = Field(default_factory=Ecosystem)
    quality: Quality
    signals: Signals = Field(default_factory=Signals)
    observations: list[str] = Field(default_factory=list)
    monthly: list[MonthlyPoint] = Field(default_factory=list)
    formulas: list[Formula] = Field(default_factory=list)
    sources: list[SourceRecord] = Field(default_factory=list)

    @property
    def summary(self) -> list[str]:
        """3-5 factual observations (spec §24.1, §38)."""
        return self.observations
