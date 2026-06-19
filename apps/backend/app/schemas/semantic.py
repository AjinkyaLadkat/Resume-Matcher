"""Pydantic models for semantic resume–job matching results.

These models are additive to the existing schema; all fields are optional
from the perspective of the existing API contract so no breaking changes occur.
"""

from pydantic import BaseModel, Field


class SectionScore(BaseModel):
    """Semantic similarity score for a single resume section."""

    section: str = Field(
        description="Section name: experience, skills, projects, summary, education"
    )
    score: float = Field(
        ge=0.0, le=100.0, description="Semantic match score (0–100)"
    )
    weight: float = Field(
        ge=0.0, le=1.0, description="Weight of this section in the overall score"
    )
    contribution: float = Field(
        ge=0.0, le=100.0, description="Weighted contribution to the total score"
    )
    raw_similarity: float = Field(
        default=0.0, ge=-1.0, le=1.0, description="Raw cosine similarity value"
    )
    has_content: bool = Field(
        default=True, description="False when the section is absent from the resume"
    )


class SemanticMatchResult(BaseModel):
    """Complete semantic matching result between a resume and a job description.

    Produced by services/scorer.py and attached to ImproveResumeData
    as the `semantic_match` field. All list fields default to empty so
    partial results are still valid.
    """

    overall_score: float = Field(
        ge=0.0,
        le=100.0,
        description="Weighted semantic match score (0–100)",
    )
    section_scores: list[SectionScore] = Field(default_factory=list)
    fit_summary: str = Field(
        default="",
        description="LLM-generated 2–3 sentence fit summary",
    )
    strengths: list[str] = Field(
        default_factory=list,
        description="Key alignment strengths between resume and JD",
    )
    gaps: list[str] = Field(
        default_factory=list,
        description="Key gaps relative to required skills / responsibilities",
    )
    recommendation: str = Field(
        default="",
        description="One-sentence actionable recommendation",
    )
    scoring_method: str = Field(
        default="semantic_embedding_cosine",
        description="Identifier for the scoring algorithm used",
    )
