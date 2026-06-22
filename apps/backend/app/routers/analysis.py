"""Router for the four semantic-analysis features:

  1. Skill Gap Analysis      → POST /analysis/{resume_id}/skill-gap
  2. Strengths & Weaknesses  → bundled inside semantic_match (scorer.py upgrade,
     no separate endpoint — see services/scorer.py)
  3. AI Interview Questions  → POST /analysis/{resume_id}/interview-questions
  4. LinkedIn Headlines      → POST /analysis/{resume_id}/linkedin-headlines

All three endpoints below follow the exact on-demand-generation pattern
already used by /resumes/{id}/generate-cover-letter:
  - look up the resume
  - resolve job context (job_id stored directly on resume, OR via the
    improvements table for older records)
  - generate via LLM
  - persist result on the resume record
  - return cached result on repeat calls unless force_regenerate=true

This file is intentionally a SEPARATE router module so it never touches
the existing app/routers/enrichment.py or app/routers/resumes.py — register
it in main.py with: app.include_router(analysis_router, prefix="/api/v1")
"""

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import db
from app.schemas.analysis import (
    InterviewQuestionsResult,
    LinkedInHeadlines,
    SkillGapResult,
)
from app.services.interview_questions_service import generate_interview_questions
from app.services.linkedin_headline_service import generate_linkedin_headlines
from app.services.skill_gap_service import analyze_skill_gap

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analysis", tags=["analysis"])


class RegenerateFlag(BaseModel):
    """Optional body to force regeneration instead of returning cached result."""

    force_regenerate: bool = False


# ── Shared helper: resolve job context for a resume ────────────────────────

def _resolve_job_context(resume_id: str, resume: dict) -> tuple[dict | None, dict]:
    """Return (job_record_or_None, job_keywords_dict).

    Checks the direct job_id field first (added during the regen-rescoring
    fix), then falls back to the improvements table lookup used by the
    cover-letter/outreach generation endpoints for older resume records.
    """
    job_id = resume.get("job_id")
    if not job_id:
        improvement = db.get_improvement_by_tailored_resume(resume_id)
        if improvement:
            job_id = improvement.get("job_id")

    if not job_id:
        return None, {}

    job = db.get_job(job_id)
    if not job:
        return None, {}

    job_keywords = job.get("job_keywords") or job.get("keywords") or {}
    return job, job_keywords


def _get_resume_or_404(resume_id: str) -> dict:
    resume = db.get_resume(resume_id)
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    return resume


def _get_resume_data_or_400(resume: dict) -> dict:
    resume_data = resume.get("processed_data")
    if not resume_data:
        raise HTTPException(
            status_code=400,
            detail="Resume has no processed data. Please re-upload the resume.",
        )
    return resume_data


# ── 1. Skill Gap Analysis ──────────────────────────────────────────────────

@router.post("/{resume_id}/skill-gap", response_model=SkillGapResult)
async def get_skill_gap_analysis(
    resume_id: str, body: RegenerateFlag | None = None
) -> SkillGapResult:
    """Get (or compute) skill gap analysis for a tailored resume.

    Requires the resume to have an associated job context — i.e. it must
    have been tailored against a JD. Returns a cached result on repeat
    calls unless force_regenerate=true.
    """
    resume = _get_resume_or_404(resume_id)

    # Return cached result unless caller explicitly wants a fresh one
    if not (body and body.force_regenerate):
        cached = resume.get("skill_gap_analysis")
        if cached:
            return SkillGapResult.model_validate(cached)

    job, job_keywords = _resolve_job_context(resume_id, resume)
    if not job:
        raise HTTPException(
            status_code=400,
            detail="No job context found for this resume. "
            "Tailor this resume against a job description first.",
        )

    resume_data = _get_resume_data_or_400(resume)

    # Reuse already-computed section scores from semantic_match if present —
    # avoids re-embedding or re-scoring.
    semantic_match = resume.get("semantic_match") or {}
    section_scores = semantic_match.get("section_scores", [])

    result = await analyze_skill_gap(resume_data, job_keywords, section_scores)

    try:
        db.update_resume(resume_id, {"skill_gap_analysis": result.model_dump()})
    except Exception as exc:
        logger.warning("Could not persist skill_gap_analysis: %s", exc)

    return result


# ── 3. AI Interview Questions ──────────────────────────────────────────────

@router.post("/{resume_id}/interview-questions", response_model=InterviewQuestionsResult)
async def get_interview_questions(
    resume_id: str, body: RegenerateFlag | None = None
) -> InterviewQuestionsResult:
    """Get (or compute) interview questions tailored to this resume/JD pair."""
    resume = _get_resume_or_404(resume_id)

    if not (body and body.force_regenerate):
        cached = resume.get("interview_questions")
        if cached:
            return InterviewQuestionsResult.model_validate(cached)

    job, job_keywords = _resolve_job_context(resume_id, resume)
    if not job:
        raise HTTPException(
            status_code=400,
            detail="No job context found for this resume. "
            "Tailor this resume against a job description first.",
        )

    resume_data = _get_resume_data_or_400(resume)

    semantic_match = resume.get("semantic_match") or {}
    section_scores = semantic_match.get("section_scores", [])
    known_gaps = semantic_match.get("gaps", [])

    result = await generate_interview_questions(
        resume_data, job["content"], job_keywords, section_scores, known_gaps
    )

    try:
        db.update_resume(resume_id, {"interview_questions": result.model_dump()})
    except Exception as exc:
        logger.warning("Could not persist interview_questions: %s", exc)

    return result


# ── 4. LinkedIn Headline Generator ─────────────────────────────────────────

@router.post("/{resume_id}/linkedin-headlines", response_model=LinkedInHeadlines)
async def get_linkedin_headlines(
    resume_id: str, body: RegenerateFlag | None = None
) -> LinkedInHeadlines:
    """Get (or compute) LinkedIn headline variants for this resume.

    Unlike skill-gap and interview-questions, this does NOT require a job
    context — it works for master resumes too. If a job context exists,
    the ats_friendly variant is tailored to that specific JD.
    """
    resume = _get_resume_or_404(resume_id)

    if not (body and body.force_regenerate):
        cached = resume.get("linkedin_headlines")
        if cached:
            return LinkedInHeadlines.model_validate(cached)

    resume_data = _get_resume_data_or_400(resume)

    # Job context is optional here — None is fine, the service handles it
    job, _ = _resolve_job_context(resume_id, resume)
    jd_text = job["content"] if job else None

    result = await generate_linkedin_headlines(resume_data, jd_text)

    try:
        db.update_resume(resume_id, {"linkedin_headlines": result.model_dump()})
    except Exception as exc:
        logger.warning("Could not persist linkedin_headlines: %s", exc)

    return result
