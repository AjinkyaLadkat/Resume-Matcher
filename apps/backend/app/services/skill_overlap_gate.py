"""Deterministic skill-overlap gate for semantic scoring.

This module exists because embedding cosine similarity alone cannot detect
domain mismatch. Two resumes from completely unrelated fields (e.g. Data
Analytics vs Retail Operations) both contain professional English — verbs,
nouns, workplace nouns — and land in the same 0.30-0.45 cosine range that
genuinely related but differently-worded pairs also occupy. Cosine similarity
measures "is this professionally-written text," not "does this candidate
have the skills this job needs."

The fix: compute literal/fuzzy overlap between JD required_skills and the
resume's skill + experience + project text, and use that as a hard multiplier
on the final score. A resume with zero required-skill evidence gets capped
low regardless of how "well-written" its unrelated content is.

This is intentionally NOT an LLM call — it must be fast, deterministic, and
reproducible for the benchmark suite in tests/test_scoring_calibration.py.
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Generic/soft skills that should contribute minimally to overlap scoring —
# present in nearly every job description regardless of domain, so matching
# on these alone is not evidence of domain fit.
_GENERIC_SOFT_SKILLS = {
    "communication", "communication skills", "teamwork", "team player",
    "leadership", "problem solving", "problem-solving", "time management",
    "organization", "organizational skills", "attention to detail",
    "interpersonal skills", "collaboration", "adaptability", "flexibility",
    "customer service", "multitasking", "critical thinking", "work ethic",
    "self-motivated", "detail-oriented", "fast-paced environment",
    "professionalism", "reliability", "punctuality", "positive attitude",
}


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation noise, collapse whitespace."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s+#./-]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _is_generic(skill: str) -> bool:
    return _normalize(skill) in _GENERIC_SOFT_SKILLS


def _skill_found_in_text(skill: str, haystack_normalized: str) -> bool:
    """Fuzzy containment check: does this skill appear in the resume text?

    Uses substring match on normalized text plus a word-overlap fallback
    for multi-word skills (e.g. "Microsoft Power BI" should match resume
    text containing "Power BI dashboards").
    """
    skill_norm = _normalize(skill)
    if not skill_norm:
        return False

    if skill_norm in haystack_normalized:
        return True

    # Multi-word fallback: if every significant word of the skill appears
    # somewhere in the haystack, count it as found. Guards against JD
    # phrasing like "proficiency in SQL" vs resume listing just "SQL".
    words = [w for w in skill_norm.split() if len(w) > 2]
    if len(words) >= 2:
        return all(w in haystack_normalized for w in words)

    # Single short word (e.g. "SQL", "R") — require exact word-boundary match
    # to avoid false positives from substring collisions.
    return bool(re.search(rf"\b{re.escape(skill_norm)}\b", haystack_normalized))


def compute_skill_overlap(
    resume_data: dict[str, Any],
    jd_keywords: dict[str, Any],
) -> dict[str, Any]:
    """Compute literal/fuzzy overlap between JD requirements and resume content.

    Returns a dict with:
        required_total:     count of non-generic required skills in the JD
        required_matched:   how many of those were found in the resume
        required_match_rate: required_matched / required_total (0.0-1.0)
        preferred_match_rate: same, for preferred_skills
        matched_skills:      list of matched skill names (for debugging/UI)
        missing_critical:    required skills with zero evidence
    """
    haystack = _build_resume_haystack(resume_data)
    haystack_norm = _normalize(haystack)

    required = [s for s in jd_keywords.get("required_skills", []) if isinstance(s, str) and s.strip()]
    preferred = [s for s in jd_keywords.get("preferred_skills", []) if isinstance(s, str) and s.strip()]

    # Filter out generic soft skills from the "critical" count — matching on
    # "communication" tells us nothing about domain fit.
    required_specific = [s for s in required if not _is_generic(s)]

    matched_skills: list[str] = []
    missing_critical: list[str] = []
    for skill in required_specific:
        if _skill_found_in_text(skill, haystack_norm):
            matched_skills.append(skill)
        else:
            missing_critical.append(skill)

    required_total = len(required_specific)
    required_matched = len(matched_skills)
    required_match_rate = (required_matched / required_total) if required_total else 1.0
    # No required skills extracted at all → don't penalise (upstream extraction
    # may have failed); treat as neutral rather than as a mismatch signal.

    preferred_matched = sum(
        1 for s in preferred if not _is_generic(s) and _skill_found_in_text(s, haystack_norm)
    )
    preferred_specific_total = len([s for s in preferred if not _is_generic(s)])
    preferred_match_rate = (
        (preferred_matched / preferred_specific_total) if preferred_specific_total else 1.0
    )

    return {
        "required_total": required_total,
        "required_matched": required_matched,
        "required_match_rate": round(required_match_rate, 3),
        "preferred_match_rate": round(preferred_match_rate, 3),
        "matched_skills": matched_skills,
        "missing_critical": missing_critical,
    }


def _build_resume_haystack(resume_data: dict[str, Any]) -> str:
    """Concatenate all resume text where a skill could legitimately appear.

    Includes: technical skills list, certifications, summary, experience
    bullets, project bullets. Deliberately excludes personal info, education
    institution names, and dates — those are never where a skill claim lives.
    """
    parts: list[str] = []

    additional = resume_data.get("additional", {}) or {}
    for key in ("technicalSkills", "certificationsTraining", "languages"):
        val = additional.get(key, [])
        if isinstance(val, list):
            parts.extend(str(v) for v in val)

    summary = resume_data.get("summary", "")
    if isinstance(summary, str):
        parts.append(summary)

    for exp in resume_data.get("workExperience", []) or []:
        if not isinstance(exp, dict):
            continue
        parts.append(str(exp.get("title", "")))
        desc = exp.get("description", [])
        if isinstance(desc, list):
            parts.extend(str(d) for d in desc)

    for proj in resume_data.get("personalProjects", []) or []:
        if not isinstance(proj, dict):
            continue
        parts.append(str(proj.get("name", "")))
        desc = proj.get("description", [])
        if isinstance(desc, list):
            parts.extend(str(d) for d in desc)

    return " ".join(p for p in parts if p)

