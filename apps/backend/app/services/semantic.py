"""Semantic embedding engine using Ollama nomic-embed-text.

Phase 1 of the semantic upgrade. Provides:
- Async embedding generation via litellm → Ollama nomic-embed-text
- Pure-Python cosine similarity (no numpy dependency)
- Section-wise resume chunking
- JD aspect chunking
"""

import asyncio
import logging
import math
from typing import Any

import litellm

from app.llm import get_llm_config

logger = logging.getLogger(__name__)

# Embedding model config
EMBEDDING_MODEL = "nomic-embed-text"
EMBEDDING_TIMEOUT = 30  # seconds per embedding call
# nomic-embed-text context window is 8192 tokens; we cap chars to stay safe
_MAX_EMBED_CHARS = 6000


# ---------------------------------------------------------------------------
# Core math helpers (pure Python — no numpy required)
# ---------------------------------------------------------------------------

def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two dense vectors.

    Returns 0.0 if either vector is empty or all-zeros.
    """
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    sim = dot / (norm_a * norm_b)
    # Clamp to [-1, 1] to avoid floating-point drift
    return max(-1.0, min(1.0, sim))


# ---------------------------------------------------------------------------
# Embedding generation
# ---------------------------------------------------------------------------

async def get_embedding(text: str) -> list[float]:
    """Get embedding vector from Ollama nomic-embed-text via LiteLLM.

    Returns an empty list on any failure so callers can degrade gracefully.
    The text is truncated to _MAX_EMBED_CHARS before sending.
    """
    if not text or not text.strip():
        return []

    text = text.strip()[:_MAX_EMBED_CHARS]

    try:
        config = get_llm_config()
        # Use the configured Ollama base; fall back to default local address
        api_base = (config.api_base or "http://localhost:11434").rstrip("/")

        response = await litellm.aembedding(
            model=f"ollama/{EMBEDDING_MODEL}",
            input=text,
            api_base=api_base,
            timeout=EMBEDDING_TIMEOUT,
        )
        embedding: list[float] = response.data[0]["embedding"]
        return embedding

    except Exception as exc:
        logger.warning(
            "Embedding generation failed (model=%s): %s",
            EMBEDDING_MODEL,
            str(exc)[:200],
        )
        return []


async def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Fetch embeddings for a list of texts concurrently.

    Preserves order. Failures return empty lists at their position.
    """
    tasks = [get_embedding(t) for t in texts]
    results: list[list[float]] = await asyncio.gather(*tasks)
    return results


# ---------------------------------------------------------------------------
# Resume section chunking
# ---------------------------------------------------------------------------

def chunk_resume_by_section(resume_data: dict[str, Any]) -> dict[str, str]:
    """Convert structured resume data into one text chunk per section.

    Sections produced: summary, experience, projects, skills, education.
    Missing or empty sections return an empty string (key still present).
    """
    chunks: dict[str, str] = {
        "summary": "",
        "experience": "",
        "projects": "",
        "skills": "",
        "education": "",
    }

    # ── Summary ──────────────────────────────────────────────────────────
    summary = resume_data.get("summary", "")
    if isinstance(summary, str) and summary.strip():
        chunks["summary"] = summary.strip()

    # ── Work experience ───────────────────────────────────────────────────
    exp_lines: list[str] = []
    for exp in resume_data.get("workExperience", []):
        if not isinstance(exp, dict):
            continue
        parts = [
            exp.get("title", ""),
            exp.get("company", ""),
            exp.get("years", ""),
        ]
        header = " | ".join(p for p in parts if p)
        if header:
            exp_lines.append(header)
        desc = exp.get("description", [])
        if isinstance(desc, list):
            exp_lines.extend(d for d in desc if isinstance(d, str) and d.strip())
        elif isinstance(desc, str) and desc.strip():
            exp_lines.append(desc.strip())
    if exp_lines:
        chunks["experience"] = "\n".join(exp_lines)

    # ── Personal projects ─────────────────────────────────────────────────
    proj_lines: list[str] = []
    for proj in resume_data.get("personalProjects", []):
        if not isinstance(proj, dict):
            continue
        parts = [proj.get("name", ""), proj.get("role", "")]
        header = " | ".join(p for p in parts if p)
        if header:
            proj_lines.append(header)
        desc = proj.get("description", [])
        if isinstance(desc, list):
            proj_lines.extend(d for d in desc if isinstance(d, str) and d.strip())
        elif isinstance(desc, str) and desc.strip():
            proj_lines.append(desc.strip())
    if proj_lines:
        chunks["projects"] = "\n".join(proj_lines)

    # ── Skills (technical + certs + languages) ────────────────────────────
    additional = resume_data.get("additional", {})
    if isinstance(additional, dict):
        skill_items: list[str] = []
        for key in ("technicalSkills", "certificationsTraining", "languages"):
            val = additional.get(key, [])
            if isinstance(val, list):
                skill_items.extend(s for s in val if isinstance(s, str) and s.strip())
        if skill_items:
            chunks["skills"] = ", ".join(skill_items)

    # ── Education ─────────────────────────────────────────────────────────
    edu_lines: list[str] = []
    for edu in resume_data.get("education", []):
        if not isinstance(edu, dict):
            continue
        parts = [edu.get("degree", ""), edu.get("institution", "")]
        line = " | ".join(p for p in parts if p)
        if line:
            edu_lines.append(line)
        desc = edu.get("description", "")
        if isinstance(desc, str) and desc.strip():
            edu_lines.append(desc.strip())
    if edu_lines:
        chunks["education"] = "\n".join(edu_lines)

    return chunks


# ---------------------------------------------------------------------------
# JD aspect chunking
# ---------------------------------------------------------------------------

def chunk_jd_by_aspect(
    jd_text: str,
    jd_keywords: dict[str, Any],
) -> dict[str, str]:
    """Produce a context-relevant text chunk for each resume section.

    Each value is what the JD says about the corresponding requirement so
    that section-level cosine similarity is meaningful.
    """
    # Cap raw JD text to avoid token overflows
    jd_capped = (jd_text or "")[:_MAX_EMBED_CHARS]
    jd_short = jd_capped[:2000]

    # Required + preferred skills string
    req = jd_keywords.get("required_skills", [])
    pref = jd_keywords.get("preferred_skills", [])
    all_skills = [str(s) for s in (req + pref) if s]
    skills_text = ", ".join(all_skills) if all_skills else jd_short

    # Key responsibilities for experience / projects
    resp = jd_keywords.get("key_responsibilities", [])
    if isinstance(resp, list) and resp:
        resp_text = "\n".join(str(r) for r in resp)
    else:
        resp_text = jd_capped

    # Job summary / overview for the summary section
    summary_text = jd_keywords.get("job_summary", jd_short) or jd_short
    if isinstance(summary_text, list):
        summary_text = " ".join(str(s) for s in summary_text)

    return {
        "summary": str(summary_text)[:_MAX_EMBED_CHARS],
        "experience": resp_text[:_MAX_EMBED_CHARS],
        "projects": resp_text[:_MAX_EMBED_CHARS],
        "skills": skills_text[:_MAX_EMBED_CHARS],
        "education": jd_short[:_MAX_EMBED_CHARS],
    }
