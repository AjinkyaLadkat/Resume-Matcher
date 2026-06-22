"""AI Interview Questions service.

Targets weak areas by reusing the already-computed semantic section_scores
(picks the weakest section as a probing focus) and the already-cached
job_keywords' gaps — no new keyword extraction or embedding work needed.
"""

import logging
from typing import Any

from app.llm import complete_json
from app.prompts.analysis import INTERVIEW_QUESTIONS_PROMPT
from app.schemas.analysis import InterviewQuestion, InterviewQuestionsResult

logger = logging.getLogger(__name__)

_CATEGORIES = ["technical", "project", "behavioral", "resume_specific", "jd_specific"]


async def generate_interview_questions(
    resume_data: dict[str, Any],
    jd_text: str,
    job_keywords: dict[str, Any],
    section_scores: list[dict[str, Any]] | None = None,
    known_gaps: list[str] | None = None,
) -> InterviewQuestionsResult:
    """Generate interview questions tailored to this resume/JD pair.

    Never raises — returns an empty result on failure.
    """
    try:
        return await _generate(resume_data, jd_text, job_keywords, section_scores or [], known_gaps or [])
    except Exception as exc:
        logger.warning("Interview question generation failed: %s", str(exc)[:300])
        return InterviewQuestionsResult()


async def _generate(
    resume_data: dict[str, Any],
    jd_text: str,
    job_keywords: dict[str, Any],
    section_scores: list[dict[str, Any]],
    known_gaps: list[str],
) -> InterviewQuestionsResult:
    resume_summary      = _build_resume_summary(resume_data)
    experience_summary  = _summarize_experience(resume_data)
    projects_summary     = _summarize_projects(resume_data)
    required_skills      = job_keywords.get("required_skills", [])

    weakest_section, weakest_score = _find_weakest(section_scores)

    prompt = INTERVIEW_QUESTIONS_PROMPT.format(
        resume_summary=resume_summary,
        experience_summary=experience_summary,
        projects_summary=projects_summary,
        job_description=(jd_text or "")[:1500],
        required_skills=", ".join(str(s) for s in required_skills[:12]) or "(none extracted)",
        weakest_section=weakest_section,
        weakest_score=f"{weakest_score:.0f}",
        known_gaps="; ".join(known_gaps[:5]) or "(none identified)",
    )

    raw = await complete_json(
        prompt=prompt,
        system_prompt=(
            "You are a hiring manager preparing targeted interview questions. "
            "Be specific to this candidate and role. Output only valid JSON."
        ),
        max_tokens=1400,
        schema_type="keywords",
    )

    if not isinstance(raw, dict):
        raw = {}

    result_kwargs: dict[str, list[InterviewQuestion]] = {}
    for category in _CATEGORIES:
        items = []
        for item in raw.get(category, []):
            if isinstance(item, dict) and item.get("question"):
                items.append(InterviewQuestion(
                    question=str(item.get("question", "")),
                    category=category,
                    difficulty=str(item.get("difficulty", "medium")),
                    rationale=str(item.get("rationale", "")),
                ))
        result_kwargs[category] = items

    return InterviewQuestionsResult(**result_kwargs)


def _find_weakest(section_scores: list[dict[str, Any]]) -> tuple[str, float]:
    if not section_scores:
        return "overall alignment", 0.0
    weakest = min(section_scores, key=lambda s: s.get("score", 100))
    return weakest.get("section", "overall"), weakest.get("score", 0.0)


def _build_resume_summary(resume_data: dict[str, Any]) -> str:
    info = resume_data.get("personalInfo", {}) or {}
    title = info.get("title", "") if isinstance(info, dict) else ""
    summary = resume_data.get("summary", "")
    parts = []
    if title:
        parts.append(f"Title: {title}")
    if summary:
        parts.append(f"Summary: {summary[:300]}")
    return "\n".join(parts) if parts else "(no summary available)"


def _summarize_experience(resume_data: dict[str, Any]) -> str:
    lines = []
    for exp in resume_data.get("workExperience", [])[:4]:
        if not isinstance(exp, dict):
            continue
        header = f"{exp.get('title', '')} at {exp.get('company', '')}".strip(" at")
        if header:
            lines.append(f"  - {header}")
        for bullet in (exp.get("description") or [])[:3]:
            lines.append(f"    • {bullet}")
    return "\n".join(lines) if lines else "  (no experience listed)"


def _summarize_projects(resume_data: dict[str, Any]) -> str:
    lines = []
    for proj in resume_data.get("personalProjects", [])[:4]:
        if not isinstance(proj, dict):
            continue
        name = proj.get("name", "")
        if name:
            lines.append(f"  - {name}")
        for bullet in (proj.get("description") or [])[:2]:
            lines.append(f"    • {bullet}")
    return "\n".join(lines) if lines else "  (no projects listed)"
