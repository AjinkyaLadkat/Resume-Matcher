"""Semantic scoring engine.

Orchestrates:
  1. Section-wise resume + JD chunking   (semantic.chunk_*)
  2. Concurrent embedding generation     (semantic.get_embeddings_batch)
  3. Cosine similarity per section       (semantic.cosine_similarity)
  4. Weighted overall score + coverage bonus
  5. LLM contextual fit analysis

Entry point: score_resume_against_jd()

Calibration notes
-----------------
nomic-embed-text cosine ranges for genuinely related text pairs:
  0.30-0.45  same domain, different specifics  → user sees 38-56
  0.45-0.60  solid skill/experience match      → user sees 56-74
  0.60-0.75  strong alignment                  → user sees 74-89
  0.75-0.90  near-perfect match                → user sees 89-97

A coverage bonus (+3 or +6) is added when 3+ sections show real
semantic overlap (cosine ≥ 0.30), rewarding well-rounded resumes
without faking scores.
"""

import logging
from typing import Any

from app.llm import complete_json
from app.prompts.semantic import CONTEXTUAL_FIT_ANALYSIS_PROMPT_V2
from app.schemas.semantic import SemanticMatchResult, SectionScore, StrengthItem, WeaknessItem
from app.services.semantic import (
    chunk_jd_by_aspect,
    chunk_resume_by_section,
    cosine_similarity,
    get_embeddings_batch,
)

logger = logging.getLogger(__name__)

# ── Section weights (must sum to 1.0) ──────────────────────────────────────
SECTION_WEIGHTS: dict[str, float] = {
    "experience": 0.35,
    "skills":     0.25,
    "projects":   0.20,
    "summary":    0.10,
    "education":  0.10,
}
_SECTIONS = list(SECTION_WEIGHTS.keys())

# Cosine threshold above which a section counts as "genuinely matching"
_COVERAGE_THRESHOLD = 0.30


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def score_resume_against_jd(
    resume_data: dict[str, Any],
    jd_text: str,
    jd_keywords: dict[str, Any],
    *,
    run_llm_analysis: bool = True,
) -> SemanticMatchResult:
    """Compute semantic match score between a resume and a job description.

    Never raises — partial / empty results returned on failure.
    """
    try:
        return await _score(resume_data, jd_text, jd_keywords, run_llm_analysis)
    except Exception as exc:
        logger.warning("Semantic scoring failed entirely: %s", str(exc)[:300])
        return SemanticMatchResult(
            overall_score=0.0,
            fit_summary="Semantic scoring unavailable.",
            scoring_method="failed",
        )


# ---------------------------------------------------------------------------
# Internal pipeline
# ---------------------------------------------------------------------------

async def _score(
    resume_data: dict[str, Any],
    jd_text: str,
    jd_keywords: dict[str, Any],
    run_llm_analysis: bool,
) -> SemanticMatchResult:
    resume_chunks = chunk_resume_by_section(resume_data)
    jd_chunks = chunk_jd_by_aspect(jd_text, jd_keywords)

    resume_texts = [resume_chunks.get(s, "") for s in _SECTIONS]
    jd_texts     = [jd_chunks.get(s, "")     for s in _SECTIONS]

    all_embeddings   = await get_embeddings_batch(resume_texts + jd_texts)
    resume_embs      = all_embeddings[: len(_SECTIONS)]
    jd_embs          = all_embeddings[len(_SECTIONS) :]

    section_scores: list[SectionScore] = []
    total_weighted  = 0.0
    coverage_hits   = 0  # sections with cosine ≥ threshold

    for i, section in enumerate(_SECTIONS):
        weight      = SECTION_WEIGHTS[section]
        r_emb       = resume_embs[i]
        j_emb       = jd_embs[i]
        has_content = bool(resume_chunks.get(section))

        if r_emb and j_emb:
            raw_sim = cosine_similarity(r_emb, j_emb)
        else:
            raw_sim = 0.0

        if raw_sim >= _COVERAGE_THRESHOLD:
            coverage_hits += 1

        score_100    = _scale_cosine(raw_sim)
        contribution = round(score_100 * weight, 2)
        total_weighted += contribution

        section_scores.append(
            SectionScore(
                section=section,
                score=round(score_100, 1),
                weight=weight,
                contribution=contribution,
                raw_similarity=round(raw_sim, 4),
                has_content=has_content,
            )
        )

    # Coverage bonus — deterministic, semantically grounded
    bonus = 0.0
    if coverage_hits >= 4:
        bonus = 6.0
    elif coverage_hits >= 3:
        bonus = 3.0

    overall = round(min(total_weighted + bonus, 100.0), 1)

    # ── LLM contextual analysis ─────────────────────────────────────────
    fit_summary    = ""
    strengths: list[str] = []
    gaps:      list[str] = []
    strengths_detailed: list[StrengthItem] = []
    weaknesses_detailed: list[WeaknessItem] = []
    recommendation = ""

    if run_llm_analysis:
        try:
            analysis = await _contextual_analysis(
                resume_data, jd_text, jd_keywords, section_scores, overall
            )
            fit_summary = str(analysis.get("fit_summary", ""))

            raw_strengths = analysis.get("strengths_detailed", [])
            for s in raw_strengths:
                if isinstance(s, dict) and s.get("strength"):
                    strengths_detailed.append(
                        StrengthItem(
                            strength=str(s.get("strength", "")),
                            evidence=str(s.get("evidence", "")),
                            relevance=str(s.get("relevance", "")),
                        )
                    )
            raw_weaknesses = analysis.get("weaknesses_detailed", [])
            for w in raw_weaknesses:
                if isinstance(w, dict) and w.get("weakness"):
                    weaknesses_detailed.append(
                        WeaknessItem(
                            weakness=str(w.get("weakness", "")),
                            jd_requirement=str(w.get("jd_requirement", "")),
                            weakness_type=str(w.get("weakness_type", "missing_evidence")),
                        )
                    )

            # Populate legacy plain-string fields for backward compatibility
            # with any UI code still reading list[str] directly.
            strengths = [s.strength for s in strengths_detailed]
            gaps      = [w.weakness for w in weaknesses_detailed]

            recommendation = str(analysis.get("recommendation", ""))
        except Exception as exc:
            logger.warning("LLM contextual analysis failed: %s", str(exc)[:200])
            fit_summary = _fallback_summary(overall, section_scores)

    return SemanticMatchResult(
        overall_score=overall,
        section_scores=section_scores,
        fit_summary=fit_summary,
        strengths=strengths,
        gaps=gaps,
        strengths_detailed=strengths_detailed,
        weaknesses_detailed=weaknesses_detailed,
        recommendation=recommendation,
        scoring_method="semantic_embedding_cosine_v2",
    )


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

def _scale_cosine(cosine: float) -> float:
    """Map cosine similarity to 0-100 score.

    Calibrated for nomic-embed-text where relevant text pairs typically
    produce cosine 0.35-0.75.  Mapping keeps semantic ordering intact
    while producing more confidence-inspiring scores for mid-range matches.

    Breakpoints (cosine → score):
      0.00 → 0
      0.20 → 15    (truly unrelated)
      0.35 → 40    (weak match)
      0.50 → 62    (moderate match)
      0.65 → 78    (good match)
      0.80 → 91    (strong match)
      1.00 → 100   (identical)
    """
    if cosine <= 0.00: return 0.0
    if cosine <= 0.20: return (cosine / 0.20) * 15
    if cosine <= 0.35: return 15 + ((cosine - 0.20) / 0.15) * 25
    if cosine <= 0.50: return 40 + ((cosine - 0.35) / 0.15) * 22
    if cosine <= 0.65: return 62 + ((cosine - 0.50) / 0.15) * 16
    if cosine <= 0.80: return 78 + ((cosine - 0.65) / 0.15) * 13
    return                     91 + ((cosine - 0.80) / 0.20) * 9


# ---------------------------------------------------------------------------
# LLM analysis helpers
# ---------------------------------------------------------------------------

async def _contextual_analysis(
    resume_data: dict[str, Any],
    jd_text: str,
    jd_keywords: dict[str, Any],
    section_scores: list[SectionScore],
    overall_score: float,
) -> dict[str, Any]:
    resume_summary = _build_resume_summary(resume_data)
    jd_excerpt     = (jd_text or "")[:1500]
    scores_text    = "\n".join(
        f"  - {s.section.capitalize()}: {s.score:.0f}/100 (weight {s.weight:.0%})"
        for s in section_scores
    )
    req_skills  = ", ".join(str(s) for s in jd_keywords.get("required_skills",  [])[:12])
    pref_skills = ", ".join(str(s) for s in jd_keywords.get("preferred_skills", [])[:8])

    prompt = CONTEXTUAL_FIT_ANALYSIS_PROMPT_V2.format(
        overall_score=f"{overall_score:.1f}",
        section_scores=scores_text,
        resume_summary=resume_summary,
        job_description=jd_excerpt,
        required_skills=req_skills  or "(none extracted)",
        preferred_skills=pref_skills or "(none extracted)",
    )

    return await complete_json(
        prompt=prompt,
        system_prompt=(
            "You are a senior technical recruiter. "
            "Be specific, concise, and honest. Output only valid JSON."
        ),
        max_tokens=900,
        schema_type="keywords",
    )


def _build_resume_summary(resume_data: dict[str, Any]) -> str:
    parts: list[str] = []
    info  = resume_data.get("personalInfo", {})
    title = info.get("title", "") if isinstance(info, dict) else ""
    if title:
        parts.append(f"Current title: {title}")

    summary = resume_data.get("summary", "")
    if isinstance(summary, str) and summary.strip():
        parts.append(f"Profile: {summary.strip()[:300]}")

    for exp in resume_data.get("workExperience", [])[:3]:
        if not isinstance(exp, dict): continue
        t = exp.get("title", ""); c = exp.get("company", "")
        if t or c: parts.append(f"  - {t} at {c}".strip(" at"))

    skills = (resume_data.get("additional") or {}).get("technicalSkills", [])
    if isinstance(skills, list) and skills:
        parts.append(f"Skills: {', '.join(str(s) for s in skills[:15])}")

    return "\n".join(parts) if parts else "(no resume summary available)"


def _fallback_summary(
    overall_score: float,
    section_scores: list[SectionScore],
) -> str:
    level = "strong" if overall_score >= 75 else ("moderate" if overall_score >= 50 else "partial")
    summary = (
        f"This resume shows {level} semantic alignment with the job description "
        f"(score: {overall_score:.0f}/100)."
    )
    if section_scores:
        top = max(section_scores, key=lambda s: s.score)
        low = min(section_scores, key=lambda s: s.score)
        summary += f" Strongest match in {top.section} ({top.score:.0f}/100)."
        if low.score < 45 and low.section != top.section:
            summary += f" Gap identified in {low.section}."
    return summary
