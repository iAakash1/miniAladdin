"""
Research evidence model — the normalized output of every research-grade
provider (SEC filings, encyclopedic facts, web research).

The contract: nothing becomes a claim without evidence, and every piece of
evidence names its provider, its document and its date. Engines compose
these objects; the LLM narrates them; neither invents them.

    ResearchSource     where a fact came from (provider + document + url)
    ResearchEvidence   one citable excerpt/datum from a source
    ResearchClaim      a statement, with the evidence that supports it
    ResearchFinding    a deterministic, tone-carrying observation
    TimelineEvent      one dated event, for the unified company timeline
    GraphNode/Edge     knowledge-graph primitives (typed, sourced, dated)
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Tone = Literal["pos", "neg", "neutral"]

# Node/edge vocabularies are closed sets: an open string would let providers
# invent taxonomy and silently fragment the graph.
NodeType = Literal[
    "company", "person", "product", "brand", "industry", "country",
    "exchange", "subsidiary", "technology", "topic", "filing", "concept",
]
EdgeType = Literal[
    "ceo_of", "founded", "board_member_of", "competes_with", "supplies",
    "owns", "subsidiary_of", "parent_of", "acquired", "belongs_to",
    "headquartered_in", "listed_on", "produces", "uses", "mentions",
    "related_to",
]


class ResearchSource(BaseModel):
    provider: str                      # "sec", "wikidata", "apify.perplexity"
    title: str
    url: Optional[str] = None
    document_type: Optional[str] = None  # "10-K", "8-K", "wikidata-entity"
    published_at: Optional[str] = None   # ISO date when known


class ResearchEvidence(BaseModel):
    id: str
    source: ResearchSource
    excerpt: str                       # the actual supporting text/datum
    doc_section: Optional[str] = None


class ResearchClaim(BaseModel):
    id: str
    statement: str
    evidence: list[ResearchEvidence] = Field(default_factory=list)
    # 0..1 — derived from source authority and corroboration count, never
    # from a model's self-assessment.
    confidence: float = 0.5
    tone: Tone = "neutral"


class ResearchFinding(BaseModel):
    """A deterministic observation ready for display."""
    id: str
    label: str
    text: str
    tone: Tone = "neutral"
    evidence: list[ResearchEvidence] = Field(default_factory=list)


class TimelineEvent(BaseModel):
    id: str
    date: str                          # ISO
    kind: str                          # "filing", "earnings", "executive", …
    title: str
    detail: Optional[str] = None
    tone: Tone = "neutral"
    source: Optional[ResearchSource] = None


class GraphNode(BaseModel):
    id: str                            # "company:NVDA", "person:jensen-huang"
    type: NodeType
    label: str
    description: Optional[str] = None
    route: Optional[str] = None        # where the UI can navigate, when addressable
    metadata: dict[str, str] = Field(default_factory=dict)


class GraphEdge(BaseModel):
    source_id: str
    target_id: str
    type: EdgeType
    provider: str
    confidence: float = 0.7
    observed_at: str = Field(default_factory=lambda: datetime.utcnow().date().isoformat())


class KnowledgeBundle(BaseModel):
    """What every research provider returns: graph material + evidence.

    Providers never return prose. They return this, and engines merge
    bundles from many providers into one deduplicated view.
    """
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)
    findings: list[ResearchFinding] = Field(default_factory=list)
    claims: list[ResearchClaim] = Field(default_factory=list)
    events: list[TimelineEvent] = Field(default_factory=list)
