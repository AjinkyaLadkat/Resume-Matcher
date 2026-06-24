"""Semantic scoring engine — v3 calibration.

Orchestrates:
  1. Section-wise resume + JD chunking   (semantic.chunk_*)
  2. Concurrent embedding generation     (semantic.get_embeddings_batch)
  3. Cosine similarity per section       (semantic.cosine_similarity)
  4. Deterministic skill-overlap gate    (skill_overlap_gate.py)
  5. Weighted blend of semantic + skill-overlap signals
  6. LLM contextual fit analysis

Entry point: score_resume_against_jd()

═══════════════════════════════════════════════════════════════════════════
CALIBRATION v3 — why this exists
═══════════════════════════════════════════════════════════════════════════

Problem found in production: a Data Analytics resume scored 74/100 against
a completely unrelated Retail Store Operations Supervisor JD. Root cause:
embedding cosine similarity cannot distinguish "domain match" from "both
texts are written in professional English." Two unrelated resumes share
enough generic structure (verbs, workplace nouns, professional register)
to produce cosine ~0.30-0.45 — and the old calibration treated that whole
range as "same domain, different specifics," mapping it to scores of 40-62.

Fix: the final score is now a 50/50 BLEND of two independent signals:

  1. SEMANTIC SIGNAL (cosine-based, recalibrated)
     The cosine→score curve is widened so the "generic professional
     similarity" zone (cosine 0.30-0.45) compresses into the 25-45 range
     instead of 40-62 — it no longer pretends to mean "same domain."

  2. SKILL-OVERLAP SIGNAL (deterministic, not LLM-based)
     What fraction of the JD's required_skills are literally/fuzzily
     found anywhere in the resume (skills list, summary, experience
     bullets, project bullets). This is the signal that actually
     detects domain mismatch — a retail JD's required skills (POS
     systems, inventory management, staff scheduling) will have near-
     zero overlap with a data analytics resume's content, regardless
     of how "professionally similar" the prose reads.

Neither signal alone is sufficient:
  - Cosine alone over-rewards generic professional language (the bug).
  - Skill-overlap alone would under-reward genuinely transferable
    experience phrased with different terminology than the JD uses.

The blend means a resume needs BOTH decent semantic alignment AND
real skill-keyword evidence to score highly — exactly matching the
requirement that "domain alignment," "required skills," and "experience
alignment" all carry significant, independent weight.

Target calibration bands (validated against benchmark suite):
  Strong fit (same domain, most skills present):      75-95
  Moderate fit (related domain, some skills present): 45-75
  Weak fit (loosely related, few skills present):      20-45
  Different domain (no skill evidence):                 0-25
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
from app.services.skill_overlap_gate import compute_skill_overlap

logger = logging.getLogger(__name__)

# ── Section weights (must sum to 1.0) — unchanged from v2 ──────────────────
SECTION_WEIGHTS: dict[str, float] = {
    "experience": 0.35,
    "skills":     0.25,
    "projects":   0.20,
    "summary":    0.10,
    "education":  0.10,
}
_SECTIONS = list(SECTION_WEIGHTS.keys())

# ── Blend weights between semantic (cosine) and skill-overlap signals ─────
# Equal weighting: a resume needs BOTH dimensions to score highly. This is
# the direct fix for "domain alignment" / "required skills" / "experience
# alignment" all needing significant, independent weight per the requirements.
_SEMANTIC_SIGNAL_WEIGHT = 0.50
_SKILL_OVERLAP_SIGNAL_WEIGHT = 0.50

# Exponent controlling how punishing partial skill-overlap is.
# >1.0 means partial overlap (e.g. 50%) scores less than half credit,
# reflecting that missing half the required skills is a real gap, not a
# minor one.
_SKILL_OVERLAP_EXPONENT = 1.2


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
    total_weighted_semantic = 0.0

    for i, section in enumerate(_SECTIONS):
        weight      = SECTION_WEIGHTS[section]
        r_emb       = resume_embs[i]
        j_emb       = jd_embs[i]
        has_content = bool(resume_chunks.get(section))

        raw_sim = cosine_similarity(r_emb, j_emb) if (r_emb and j_emb) else 0.0
        score_100    = _scale_cosine(raw_sim)
        contribution = round(score_100 * weight, 2)
        total_weighted_semantic += contribution

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

    # ── Deterministic skill-overlap signal ───────────────────────────────
    # This is the mechanism that actually detects domain mismatch — cosine
    # similarity alone cannot, since generic professional English produces
    # similar embeddings regardless of domain.
    overlap = compute_skill_overlap(resume_data, jd_keywords)
    skill_overlap_score = round(100 * (overlap["required_match_rate"] ** _SKILL_OVERLAP_EXPONENT), 1)

    # ── Blend the two independent signals ────────────────────────────────
    semantic_score = round(min(total_weighted_semantic, 100.0), 1)
    overall = round(
        semantic_score * _SEMANTIC_SIGNAL_WEIGHT
        + skill_overlap_score * _SKILL_OVERLAP_SIGNAL_WEIGHT,
        1,
    )
    overall = max(0.0, min(overall, 100.0))

    logger.info(
        "Score blend: semantic=%.1f (cosine-based) + skill_overlap=%.1f "
        "(%d/%d required skills matched) -> overall=%.1f",
        semantic_score, skill_overlap_score,
        overlap["required_matched"], overlap["required_total"],
        overall,
    )

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
                resume_data, jd_text, jd_keywords, section_scores, overall, overlap
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
            strengths = [s.strength for s in strengths_detailed]
            gaps      = [w.weakness for w in weaknesses_detailed]

            recommendation = str(analysis.get("recommendation", ""))
        except Exception as exc:
            logger.warning("LLM contextual analysis failed: %s", str(exc)[:200])
            fit_summary = _fallback_summary(overall, section_scores, overlap)

    # If missing_critical skills exist and weren't already surfaced via the
    # LLM weaknesses, ensure at least one weakness reflects the gap — this
    # guarantees the UI never shows a high score with zero explanation when
    # the skill-overlap signal pulled it down.
    if overlap["missing_critical"] and not weaknesses_detailed:
        weaknesses_detailed.append(
            WeaknessItem(
                weakness=(
                    f"No evidence of required skills: "
                    f"{', '.join(overlap['missing_critical'][:5])}"
                ),
                jd_requirement=", ".join(overlap["missing_critical"][:5]),
                weakness_type="missing_evidence",
            )
        )
        gaps = gaps or [w.weakness for w in weaknesses_detailed]

    return SemanticMatchResult(
        overall_score=overall,
        section_scores=section_scores,
        fit_summary=fit_summary,
        strengths=strengths,
        gaps=gaps,
        strengths_detailed=strengths_detailed,
        weaknesses_detailed=weaknesses_detailed,
        recommendation=recommendation,
        scoring_method="semantic_skill_blend_v3",
    )


# ---------------------------------------------------------------------------
# Calibration — v3
# ---------------------------------------------------------------------------

def _scale_cosine(cosine: float) -> float:
    """Map cosine similarity to a 0-100 SEMANTIC signal score (pre-blend).

    Recalibrated in v3 to compress the "generic professional similarity"
    zone. nomic-embed-text produces cosine ~0.30-0.45 for almost any two
    pieces of professional resume/JD text — including completely unrelated
    domains. This curve no longer interprets that range as meaningful
    domain alignment; genuine alignment requires cosine 0.50+.

    Breakpoints (cosine → score):
      0.00 → 0     (no similarity)
      0.30 → 25    (generic professional-text similarity — NOT domain match)
      0.45 → 45    (some genuine topical overlap)
      0.60 → 65    (solid alignment)
      0.75 → 85    (strong alignment)
      0.90 → 95    (near-perfect)
      1.00 → 100   (identical)

    This is one of two signals blended in _score() — see module docstring.
    """
    if cosine <= 0.00: return 0.0
    if cosine <= 0.30: return (cosine / 0.30) * 25
    if cosine <= 0.45: return 25 + ((cosine - 0.30) / 0.15) * 20
    if cosine <= 0.60: return 45 + ((cosine - 0.45) / 0.15) * 20
    if cosine <= 0.75: return 65 + ((cosine - 0.60) / 0.15) * 20
    if cosine <= 0.90: return 85 + ((cosine - 0.75) / 0.15) * 10
    return                     95 + ((cosine - 0.90) / 0.10) * 5


# ---------------------------------------------------------------------------
# LLM analysis helpers
# ---------------------------------------------------------------------------

async def _contextual_analysis(
    resume_data: dict[str, Any],
    jd_text: str,
    jd_keywords: dict[str, Any],
    section_scores: list[SectionScore],
    overall_score: float,
    overlap: dict[str, Any],
) -> dict[str, Any]:
    resume_summary = _build_resume_summary(resume_data)
    jd_excerpt     = (jd_text or "")[:1500]
    scores_text    = "\n".join(
        f"  - {s.section.capitalize()}: {s.score:.0f}/100 (weight {s.weight:.0%})"
        for s in section_scores
    )
    req_skills  = ", ".join(str(s) for s in jd_keywords.get("required_skills",  [])[:12])
    pref_skills = ", ".join(str(s) for s in jd_keywords.get("preferred_skills", [])[:8])

    # Surface the deterministic skill-overlap finding directly in the prompt
    # so the LLM's narrative is consistent with the score, not contradicting it.
    overlap_context = (
        f"Required skills matched in resume: {overlap['required_matched']}/{overlap['required_total']}. "
    )
    if overlap["missing_critical"]:
        overlap_context += f"Missing critical skills: {', '.join(overlap['missing_critical'][:8])}."

    prompt = CONTEXTUAL_FIT_ANALYSIS_PROMPT_V2.format(
        overall_score=f"{overall_score:.1f}",
        section_scores=scores_text + f"\n  Skill-overlap finding: {overlap_context}",
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
    overlap: dict[str, Any],
) -> str:
    level = "strong" if overall_score >= 75 else ("moderate" if overall_score >= 45 else
            ("weak" if overall_score >= 20 else "very low"))
    summary = (
        f"This resume shows {level} alignment with the job description "
        f"(score: {overall_score:.0f}/100)."
    )
    if overlap["required_total"] > 0:
        summary += (
            f" {overlap['required_matched']}/{overlap['required_total']} "
            f"required skills are evidenced in the resume."
        )
    if section_scores:
        top = max(section_scores, key=lambda s: s.score)
        low = min(section_scores, key=lambda s: s.score)
        summary += f" Strongest match in {top.section} ({top.score:.0f}/100)."
        if low.score < 45 and low.section != top.section:
            summary += f" Gap identified in {low.section}."
    return summary
