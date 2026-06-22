"""LinkedIn Headline Generator service.

Works in two modes:
  - With job context (tailored resume has a job_id) → ats_friendly headline
    uses exact JD terminology
  - Without job context (master resume, no JD) → all 4 variants generated
    from resume content alone; ats_friendly falls back to recruiter style
"""

import logging
from typing import Any

from app.llm import complete_json
from app.prompts.analysis import LINKEDIN_HEADLINE_PROMPT
from app.schemas.analysis import LinkedInHeadlines

logger = logging.getLogger(__name__)


async def generate_linkedin_headlines(
    resume_data: dict[str, Any],
    jd_text: str | None = None,
) -> LinkedInHeadlines:
    """Generate 4 LinkedIn headline variants from resume content.

    jd_text is optional — when provided, the ats_friendly variant targets
    that specific job's terminology. Never raises; returns empty strings
    on failure so the UI can show a retry state.
    """
    try:
        return await _generate(resume_data, jd_text)
    except Exception as exc:
        logger.warning("LinkedIn headline generation failed: %s", str(exc)[:300])
        return LinkedInHeadlines(
            professional="", recruiter_friendly="", ats_friendly="", personal_brand="",
        )


async def _generate(resume_data: dict[str, Any], jd_text: str | None) -> LinkedInHeadlines:
    info = resume_data.get("personalInfo", {}) or {}
    current_title = info.get("title", "") or "(no title listed)"

    skills = (resume_data.get("additional") or {}).get("technicalSkills", [])
    top_skills = ", ".join(str(s) for s in skills[:8]) or "(no skills listed)"

    experience_summary = _summarize_experience(resume_data)
    experience_signal   = _estimate_experience_signal(resume_data)

    if jd_text and jd_text.strip():
        job_context_section = (
            "TARGET JOB DESCRIPTION (excerpt — use its terminology for ats_friendly):\n"
            f"{jd_text[:1200]}"
        )
    else:
        job_context_section = (
            "No specific target job provided — write all headlines from the "
            "candidate's general profile. For ats_friendly, use the resume's own "
            "skill/role terminology rather than a specific JD's."
        )

    prompt = LINKEDIN_HEADLINE_PROMPT.format(
        current_title=current_title,
        top_skills=top_skills,
        experience_signal=experience_signal,
        experience_summary=experience_summary,
        job_context_section=job_context_section,
    )

    raw = await complete_json(
        prompt=prompt,
        system_prompt=(
            "You are a personal branding expert writing LinkedIn headlines. "
            "Use only real candidate content. Output only valid JSON."
        ),
        max_tokens=500,
        schema_type="keywords",
    )

    if not isinstance(raw, dict):
        raw = {}

    def _field(key: str) -> str:
        val = raw.get(key, "")
        return str(val).strip()[:220] if val else ""

    return LinkedInHeadlines(
        professional=_field("professional"),
        recruiter_friendly=_field("recruiter_friendly"),
        ats_friendly=_field("ats_friendly"),
        personal_brand=_field("personal_brand"),
    )


def _summarize_experience(resume_data: dict[str, Any]) -> str:
    lines = []
    for exp in resume_data.get("workExperience", [])[:3]:
        if not isinstance(exp, dict):
            continue
        header = f"{exp.get('title', '')} at {exp.get('company', '')}".strip(" at")
        if header:
            lines.append(f"  - {header}")
        for bullet in (exp.get("description") or [])[:2]:
            lines.append(f"    • {bullet}")
    return "\n".join(lines) if lines else "  (no experience listed)"


def _estimate_experience_signal(resume_data: dict[str, Any]) -> str:
    """Rough seniority signal from years count — qualitative, never invented."""
    exp_count = len(resume_data.get("workExperience", []))
    if exp_count == 0:
        return "entry-level / early career"
    if exp_count <= 2:
        return "early career (1-2 roles)"
    if exp_count <= 4:
        return "mid-level (multiple roles)"
    return "senior / extensive experience"
