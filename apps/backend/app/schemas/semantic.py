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


class StrengthItem(BaseModel):
    """An evidence-based strength derived from semantic alignment.

    Unlike a generic strength string, this cites the actual resume content
    that supports the claim so the insight is verifiable, not vague.
    """

    strength: str = Field(description="The strength, stated specifically (not generic)")
    evidence: str = Field(
        description="The specific resume content (bullet, skill, project) that supports this"
    )
    relevance: str = Field(
        default="",
        description="Why this matters for the specific JD requirements",
    )


class WeaknessItem(BaseModel):
    """A JD-gap-based weakness, distinct from a missing skill.

    Captures structural/experience gaps (e.g. "no evidence of leading a team")
    as opposed to SkillGapResult's skill-specific gaps.
    """

    weakness: str = Field(description="The weakness, stated specifically (not generic)")
    jd_requirement: str = Field(
        description="The specific JD requirement or responsibility this weakness relates to"
    )
    weakness_type: str = Field(
        default="missing_evidence",
        description="One of: missing_experience, missing_evidence, weak_alignment",
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
    # Legacy plain-string fields — kept for backward compatibility with any
    # cached records or UI code that still reads list[str].
    strengths: list[str] = Field(
        default_factory=list,
        description="DEPRECATED: short strength phrases. Prefer strengths_detailed.",
    )
    gaps: list[str] = Field(
        default_factory=list,
        description="DEPRECATED: short gap phrases. Prefer weaknesses_detailed.",
    )
    # Structured, evidence-based replacements (feature #2: Strengths & Weaknesses)
    strengths_detailed: list[StrengthItem] = Field(
        default_factory=list,
        description="3-5 evidence-based strengths citing actual resume content",
    )
    weaknesses_detailed: list[WeaknessItem] = Field(
        default_factory=list,
        description="3-5 JD-gap-based weaknesses, distinct from skill-specific gaps",
    )
    recommendation: str = Field(
        default="",
        description="One-sentence actionable recommendation",
    )
    scoring_method: str = Field(
        default="semantic_embedding_cosine",
        description="Identifier for the scoring algorithm used",
    )
