"""Structured outputs exchanged between agents (validated pydantic models)."""
from typing import Literal

from pydantic import BaseModel, Field

Category = Literal["Amazon", "Shopify", "China Sourcing", "AI Automation", "Product Hunting",
                   "E-commerce News", "Business Case Studies", "Tutorials"]


class OpportunityScores(BaseModel):
    audience_interest: int = Field(description="0-10")
    recent_popularity: int
    engagement_signals: int
    search_demand: int
    content_originality: int
    educational_value: int
    audience_relevance: int


class Opportunity(BaseModel):
    title: str
    topic: str
    category: Category
    why_now: str
    proven_hook: str
    format: str
    content_gap: str
    source_urls: list[str]
    scores: OpportunityScores


class OpportunityList(BaseModel):
    opportunities: list[Opportunity]
    audience_questions: list[str]
    trending_subjects: list[str]
    hook_patterns: list[str]


class IdeaOut(BaseModel):
    title: str
    topic: str
    category: Category
    viral_hook: str
    target_audience: str
    talking_points: list[str]
    why_it_matters: str
    competitor_inspiration_urls: list[str]
    suggested_visuals: list[str]
    estimated_duration_s: int
    cta: str


class IdeaList(BaseModel):
    ideas: list[IdeaOut]


class Scene(BaseModel):
    start_s: float
    end_s: float
    purpose: Literal["hook", "problem", "value", "payoff", "cta"]
    spoken: str = Field(description="Roman Urdu spoken line (Latin script only), English e-commerce terms kept in English")
    broll_queries: list[str] = Field(description="2-3 concrete English stock-footage search queries matching this line")
    visual_direction: str
    sfx: str


class ScriptOut(BaseModel):
    title: str
    hook_variations: list[str]
    scenes: list[Scene]
    cta: str
    cta_keyword: str = Field(description="One word viewers comment, e.g. FBA")
    hook_title: str = Field(description="2-4 word on-screen hook headline")
    hook_subtitle: str = Field(description="3-5 word italic second line")
    keywords: list[str] = Field(description="4-6 key terms to show as on-screen callouts, exactly as spoken")
    fact_check_notes: list[str] = Field(description="Claims that the presenter should verify before publishing")


class BrollPick(BaseModel):
    sentence_id: int
    queries: list[str]
    label: str = Field(description="2-4 word on-screen label for a typographic graphic if no footage fits")
    prefer_graphic: bool


class BrollPlan(BaseModel):
    picks: list[BrollPick]


class CutChoice(BaseModel):
    keep_sentence_ids: list[int]
    reason: str


class PhraseFix(BaseModel):
    id: int
    words: list[str]


class SubtitleFix(BaseModel):
    phrases: list[PhraseFix]


class VisionQC(BaseModel):
    same_person_as_reference: bool
    identity_notes: str
    visible_third_party_watermark: bool
    watermark_notes: str
    visual_quality_ok: bool
    visual_notes: str
