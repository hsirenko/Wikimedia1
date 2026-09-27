"""Topic resolution results (spec §5)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ArticleRef(BaseModel):
    """The exact page an analysis used. Preserved so results can be reproduced."""

    language: str
    title: str
    page_id: int | None = None


class TopicCandidate(BaseModel):
    title: str
    wikidata_id: str | None = None
    description: str | None = None
    page_id: int | None = None


class TopicResolution(BaseModel):
    query: str
    status: Literal["resolved", "needs_review", "not_found"]
    canonical_topic: str | None = None
    wikidata_id: str | None = None
    articles: dict[str, ArticleRef] = Field(default_factory=dict)
    missing_languages: list[str] = Field(default_factory=list)
    confidence: float = 0.0
    method: str = ""
    candidates: list[TopicCandidate] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    def review_message(self) -> str:
        """The message spec §5 asks for when the concept is ambiguous."""
        lines = ["Topic resolution requires review.", "Candidates:"]
        for index, candidate in enumerate(self.candidates, 1):
            detail = f" - {candidate.description}" if candidate.description else ""
            qid = f" ({candidate.wikidata_id})" if candidate.wikidata_id else ""
            lines.append(f"{index}. {candidate.title}{qid}{detail}")
        return "\n".join(lines)
