"""Skill Gap Analysis service.

Reuses existing computed context wherever possible:
  - job["job_keywords"]            already cached on the job record
  - semantic_match.section_scores  already computed by scorer.py

Only the categorisation step (critical / nice-to-have / related-already-
demonstrated) is a new LLM call — everything else is assembled from data
that already exists, so this never re-extracts keywords or re-embeds text.
"""

import logging
from typing import Any

from app.llm import complete_json
from app.prompts.analysis import SKILL_GAP_ANALYSIS_PROMPT
from app.schemas.analysis import RelatedSkillItem, SkillGapItem, SkillGapResult

logger = logging.getLogger(__name__)


async def analyze_skill_gap(
    resume_data: dict[str, Any],
    job_keywords: dict[str, Any],
    section_scores: list[dict[str, Any]] | None = None,
) -> SkillGapResult:
    """Compute skill gap analysis between a resume and cached job keywords.

    Never raises — returns an empty result with a fallback summary on failure.
    """
    try:
        return await _analyze(resume_data, job_keywords, section_scores or [])
    except Exception as exc:
        logger.warning("Skill gap analysis failed: %s", str(exc)[:300])
        return SkillGapResult(
            summary="Skill gap analysis is temporarily unavailable.",
        )


async def _analyze(
    resume_data: dict[str, Any],
    job_keywords: dict[str, Any],
    section_scores: list[dict[str, Any]],
) -> SkillGapResult:
    required_skills  = job_keywords.get("required_skills", [])
    preferred_skills = job_keywords.get("preferred_skills", [])
    responsibilities = job_keywords.get("key_responsibilities", [])

    resume_skills = (resume_data.get("additional") or {}).get("technicalSkills", [])
    experience_summary = _summarize_experience(resume_data)
    projects_summary   = _summarize_projects(resume_data)
    scores_text         = _format_section_scores(section_scores)

    prompt = SKILL_GAP_ANALYSIS_PROMPT.format(
        required_skills=", ".join(str(s) for s in required_skills[:15]) or "(none extracted)",
        preferred_skills=", ".join(str(s) for s in preferred_skills[:10]) or "(none extracted)",
        key_responsibilities="\n".join(f"  - {r}" for r in responsibilities[:8]) or "  (none extracted)",
        resume_skills=", ".join(str(s) for s in resume_skills[:25]) or "(none listed)",
        experience_summary=experience_summary,
        projects_summary=projects_summary,
        section_scores=scores_text,
    )

    raw = await complete_json(
        prompt=prompt,
        system_prompt=(
            "You are a technical recruiter performing skill gap analysis. "
            "Be specific and evidence-based. Output only valid JSON."
        ),
        max_tokens=1000,
        schema_type="keywords",
    )

    if not isinstance(raw, dict):
        raw = {}

    critical: list[SkillGapItem] = []
    for item in raw.get("critical_missing", []):
        if isinstance(item, dict) and item.get("skill"):
            critical.append(SkillGapItem(
                skill=str(item.get("skill", "")),
                why_it_matters=str(item.get("why_it_matters", "")),
                estimated_score_impact=str(item.get("estimated_score_impact", "")),
                suggested_placement=str(item.get("suggested_placement", "")),
            ))

    nice_to_have: list[SkillGapItem] = []
    for item in raw.get("nice_to_have_missing", []):
        if isinstance(item, dict) and item.get("skill"):
            nice_to_have.append(SkillGapItem(
                skill=str(item.get("skill", "")),
                why_it_matters=str(item.get("why_it_matters", "")),
                estimated_score_impact=str(item.get("estimated_score_impact", "")),
                suggested_placement=str(item.get("suggested_placement", "")),
            ))

    related: list[RelatedSkillItem] = []
    for item in raw.get("related_skills_demonstrated", []):
        if isinstance(item, dict) and item.get("jd_skill"):
            related.append(RelatedSkillItem(
                jd_skill=str(item.get("jd_skill", "")),
                resume_evidence=str(item.get("resume_evidence", "")),
                explanation=str(item.get("explanation", "")),
            ))

    return SkillGapResult(
        critical_missing=critical,
        nice_to_have_missing=nice_to_have,
        related_skills_demonstrated=related,
        summary=str(raw.get("summary", "")),
    )


def _summarize_experience(resume_data: dict[str, Any]) -> str:
    lines = []
    for exp in resume_data.get("workExperience", [])[:4]:
        if not isinstance(exp, dict):
            continue
        title = exp.get("title", "")
        company = exp.get("company", "")
        header = f"{title} at {company}".strip(" at")
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


def _format_section_scores(section_scores: list[dict[str, Any]]) -> str:
    if not section_scores:
        return "  (not available)"
    lines = [
        f"  - {s.get('section', '?').capitalize()}: {s.get('score', 0):.0f}/100"
        for s in section_scores
    ]
    return "\n".join(lines)
