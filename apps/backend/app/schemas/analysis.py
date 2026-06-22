"""Pydantic models for the four semantic-analysis features:

  1. Skill Gap Analysis     — SkillGapResult
  2. Strengths & Weaknesses — upgrades SemanticMatchResult in-place (see semantic.py)
  3. AI Interview Questions — InterviewQuestionsResult
  4. LinkedIn Headlines     — LinkedInHeadlinesResult

All four are persisted on the resume record (mirroring how `semantic_match`,
`cover_letter`, and `outreach_message` are already stored) so results survive
page reloads without recomputation.
"""

from pydantic import BaseModel, Field


# ── 1. Skill Gap Analysis ──────────────────────────────────────────────────

class SkillGapItem(BaseModel):
    """A single missing or related skill, with context for why it matters."""

    skill: str = Field(description="The skill name as it appears in the JD")
    why_it_matters: str = Field(
        description="1-sentence explanation of why this skill matters for the role"
    )
    estimated_score_impact: str = Field(
        default="",
        description="Qualitative impact estimate, e.g. 'could raise Skills score by 5-10 pts'",
    )
    suggested_placement: str = Field(
        default="",
        description="Where this skill could realistically be added: "
        "'skills', 'projects', 'experience', or 'summary'",
    )


class RelatedSkillItem(BaseModel):
    """A skill the candidate already demonstrates that relates to a JD requirement."""

    jd_skill: str = Field(description="The skill/requirement from the JD")
    resume_evidence: str = Field(
        description="The related skill or experience already present in the resume"
    )
    explanation: str = Field(
        description="Why this existing experience is relevant to the JD skill"
    )


class SkillGapResult(BaseModel):
    """Complete skill gap analysis between a resume and a job description."""

    critical_missing: list[SkillGapItem] = Field(
        default_factory=list,
        description="Required skills with no evidence anywhere in the resume",
    )
    nice_to_have_missing: list[SkillGapItem] = Field(
        default_factory=list,
        description="Preferred (non-required) skills missing from the resume",
    )
    related_skills_demonstrated: list[RelatedSkillItem] = Field(
        default_factory=list,
        description="JD skills that are indirectly covered by existing resume content",
    )
    summary: str = Field(
        default="", description="1-2 sentence overview of the skill gap analysis"
    )


# ── 3. AI Interview Questions ──────────────────────────────────────────────

class InterviewQuestion(BaseModel):
    """A single interview question with context for why it would be asked."""

    question: str
    category: str = Field(
        description="One of: technical, project, behavioral, resume_specific, jd_specific"
    )
    difficulty: str = Field(description="One of: easy, medium, hard")
    rationale: str = Field(
        description="1-sentence explanation of why an interviewer would ask this, "
        "referencing the specific resume content or JD requirement it targets"
    )


class InterviewQuestionsResult(BaseModel):
    """Complete set of generated interview questions for a resume/JD pair."""

    technical: list[InterviewQuestion] = Field(default_factory=list)
    project: list[InterviewQuestion] = Field(default_factory=list)
    behavioral: list[InterviewQuestion] = Field(default_factory=list)
    resume_specific: list[InterviewQuestion] = Field(default_factory=list)
    jd_specific: list[InterviewQuestion] = Field(default_factory=list)


# ── 4. LinkedIn Headline Generator ─────────────────────────────────────────

class LinkedInHeadlines(BaseModel):
    """Four headline variants for different audiences/purposes."""

    professional: str = Field(description="Formal, role-focused headline")
    recruiter_friendly: str = Field(
        description="Keyword-dense headline optimised for recruiter search"
    )
    ats_friendly: str = Field(
        description="Headline using exact JD terminology for ATS/search matching"
    )
    personal_brand: str = Field(
        description="Distinctive headline that conveys personality and unique value"
    )
