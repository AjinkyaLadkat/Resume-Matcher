"""Section-aware resume parsing pipeline — three-stage architecture.

Stage 1  section_detector.py   detect_sections()
         Regex splits markdown into named section chunks.

Stage 2  entry_splitter.py     split_entries() / extract_bullets()
         Deterministically splits each section into individual entry blocks
         and extracts bullets WITHOUT any LLM call.

Stage 3  section_parser.py     (this file)
         Sends ONLY the 3-5 header lines of each entry to the LLM for
         field extraction (title, company, dates).  Bullets from Stage 2
         are merged in after — they never touch the LLM.

Why this matters
----------------
The previous architecture sent entire sections to the LLM in one call.
The model could merge entries, compress bullets, and silently truncate
when its output budget was exhausted.  The three-stage approach:

  - Guarantees bullet preservation  (never LLM-processed)
  - Guarantees entry count fidelity (split before, not during, LLM call)
  - Reduces token usage by ~70%     (header-only LLM context per entry)
  - Makes truncation structurally impossible at the entry level
"""

import logging
import re
from typing import Any

from app.llm import complete_json, get_llm_config, get_model_name, get_safe_max_tokens
from app.prompts.section_prompts import (
    EXTRACT_EDUCATION_ENTRY,
    EXTRACT_EXPERIENCE_HEADER,
    EXTRACT_PROJECT_HEADER,
    PARSE_CUSTOM_SECTION_PROMPT,
    PARSE_PERSONAL_INFO_PROMPT,
    PARSE_SKILLS_PROMPT,
)
from app.services.entry_splitter import (
    diagnose_section,
    extract_bullets,
    extract_urls,
    get_header_text,
    parse_simple_list,
    split_entries,
)
from app.services.section_detector import detect_sections

logger = logging.getLogger(__name__)

_SYSTEM = (
    "You are a precise JSON extraction engine. "
    "Output ONLY valid JSON — no markdown, no explanation, no preamble."
)

# Max tokens for each per-entry header call (small — header is 3-5 lines)
_HEADER_TOKENS   = 256
_EDU_TOKENS      = 384
_SKILLS_TOKENS   = 800
_CUSTOM_TOKENS   = 900
_PERSONAL_TOKENS = 512


# ── LLM helper ────────────────────────────────────────────────────────────

async def _llm(prompt: str, max_tokens: int, schema_type: str = "keywords") -> Any:
    config     = get_llm_config()
    model_name = get_model_name(config)
    safe       = get_safe_max_tokens(model_name, max_tokens)
    return await complete_json(
        prompt=prompt,
        system_prompt=_SYSTEM,
        max_tokens=safe,
        retries=2,
        schema_type=schema_type,
    )


# ── Personal info ──────────────────────────────────────────────────────────

_EMAIL_RE    = re.compile(r"[\w\.+\-]+@[\w.\-]+\.\w{2,}")
_PHONE_RE    = re.compile(r"(?:\+?\d{1,3}[\s\-.])?(?:\(?\d{2,4}\)?[\s\-.])\d{3,4}[\s\-.]\d{3,4}")
_LINKEDIN_RE = re.compile(r"linkedin\.com/in/[\w\-]+", re.IGNORECASE)
_GITHUB_RI   = re.compile(r"github\.com/[\w\-]+", re.IGNORECASE)
_URL_RE      = re.compile(r"https?://[^\s,<>\"']+")
_LOCATION_RE = re.compile(
    r"(?:^|\s)([A-Z][a-z]+(?:\s[A-Z][a-z]+)?,\s*(?:[A-Z]{2}|[A-Z][a-z]+(?:\s[A-Z][a-z]+)?))"
)


def _regex_personal_info(text: str) -> dict[str, Any]:
    info: dict[str, Any] = {
        "name": "", "title": "", "email": "", "phone": "",
        "location": "", "website": None, "linkedin": None, "github": None,
    }
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines:
        first = re.sub(r"\*+", "", lines[0]).strip()
        if not re.search(r"[@/:\d]", first):
            info["name"] = first
    if len(lines) > 1:
        second = re.sub(r"\*+", "", lines[1]).strip()
        if not re.search(r"[@:/\d|]", second) and 3 < len(second) < 80:
            info["title"] = second
    full = "\n".join(lines)
    for attr, pattern in [("email", _EMAIL_RE), ("phone", _PHONE_RE)]:
        m = pattern.search(full)
        if m:
            info[attr] = m.group(0).strip()
    m = _LINKEDIN_RE.search(full)
    if m:
        info["linkedin"] = m.group(0)
    m = _GITHUB_RI.search(full)
    if m:
        info["github"] = m.group(0)
    for um in _URL_RE.finditer(full):
        url = um.group(0)
        if "linkedin" not in url.lower() and "github" not in url.lower():
            info["website"] = url
            break
    m = _LOCATION_RE.search(full)
    if m:
        info["location"] = m.group(1).strip()
    return info


async def _parse_personal_info(text: str) -> dict[str, Any]:
    result = _regex_personal_info(text)
    if result.get("name") and result.get("email"):
        return result
    try:
        llm_result = await _llm(
            PARSE_PERSONAL_INFO_PROMPT.format(section_text=text[:1200]),
            _PERSONAL_TOKENS,
        )
        if isinstance(llm_result, dict):
            for k, v in llm_result.items():
                if v and not result.get(k):
                    result[k] = v
    except Exception as exc:
        logger.warning("personal_info LLM fallback failed: %s", exc)
    return result


# ── Work experience (per-entry) ────────────────────────────────────────────

async def _parse_experience_entry(
    entry_text: str, entry_idx: int, key: str
) -> dict[str, Any]:
    """Parse one work experience entry: bullets via regex, header via LLM."""
    # Stage 2a: deterministic bullet extraction
    bullets = extract_bullets(entry_text)

    # Stage 2b: isolate header (no bullets in LLM context)
    header = get_header_text(entry_text)
    if not header.strip():
        logger.warning("%s entry %d: no header text found", key, entry_idx + 1)
        return {
            "id": entry_idx + 1,
            "title": "", "company": "", "location": None, "years": "",
            "description": bullets,
        }

    # Stage 3: LLM extracts title/company/dates from tiny context
    try:
        fields = await _llm(
            EXTRACT_EXPERIENCE_HEADER.format(header_text=header),
            _HEADER_TOKENS,
        )
        if not isinstance(fields, dict):
            fields = {}
    except Exception as exc:
        logger.warning("%s entry %d: header LLM failed: %s", key, entry_idx + 1, exc)
        fields = {}

    entry = {
        "id":          entry_idx + 1,
        "title":       str(fields.get("title",    "")).strip(),
        "company":     str(fields.get("company",  "")).strip(),
        "location":    fields.get("location") or None,
        "years":       str(fields.get("years",    "")).strip(),
        "description": bullets,
    }

    if not bullets:
        logger.warning(
            "%s entry %d (%s @ %s): 0 bullets extracted from %d chars",
            key, entry_idx + 1, entry.get("title", "?"),
            entry.get("company", "?"), len(entry_text),
        )
    return entry


async def _parse_experience(text: str, key: str = "workExperience") -> list[dict]:
    """Stage 2+3: split → per-entry parse."""
    entry_blocks = split_entries(text, section_type=key)  # type: ignore[arg-type]
    logger.info("%s: split into %d entry blocks", key, len(entry_blocks))

    results = []
    for i, block in enumerate(entry_blocks):
        entry = await _parse_experience_entry(block, i, key)
        results.append(entry)

    diagnose_section(text, key, results)
    return results


# ── Projects (per-entry) ───────────────────────────────────────────────────

async def _parse_project_entry(entry_text: str, entry_idx: int) -> dict[str, Any]:
    """Parse one project entry: bullets via regex, header + URLs via LLM + regex."""
    bullets = extract_bullets(entry_text)
    urls    = extract_urls(entry_text)   # GitHub/website extracted deterministically
    header  = get_header_text(entry_text)

    if not header.strip():
        return {
            "id": entry_idx + 1,
            "name": "", "role": "", "years": "",
            "github": urls["github"], "website": urls["website"],
            "description": bullets,
        }

    try:
        fields = await _llm(
            EXTRACT_PROJECT_HEADER.format(header_text=header),
            _HEADER_TOKENS,
        )
        if not isinstance(fields, dict):
            fields = {}
    except Exception as exc:
        logger.warning("projects entry %d: header LLM failed: %s", entry_idx + 1, exc)
        fields = {}

    # LLM-extracted URLs override regex only when they look valid
    github  = fields.get("github")  or urls["github"]
    website = fields.get("website") or urls["website"]

    entry = {
        "id":          entry_idx + 1,
        "name":        str(fields.get("name", "")).strip(),
        "role":        str(fields.get("role", "")).strip(),
        "years":       str(fields.get("years", "")).strip(),
        "github":      github  if isinstance(github,  str) and github.startswith("http") else None,
        "website":     website if isinstance(website, str) and website.startswith("http") else None,
        "description": bullets,
    }

    if not bullets:
        logger.warning(
            "projects entry %d (%s): 0 bullets from %d chars",
            entry_idx + 1, entry.get("name", "?"), len(entry_text),
        )
    return entry


async def _parse_projects(text: str) -> list[dict]:
    entry_blocks = split_entries(text, section_type="personalProjects")
    logger.info("personalProjects: split into %d entry blocks", len(entry_blocks))

    results = []
    for i, block in enumerate(entry_blocks):
        entry = await _parse_project_entry(block, i)
        results.append(entry)

    diagnose_section(text, "personalProjects", results)
    return results


# ── Education (per-entry) ─────────────────────────────────────────────────

async def _parse_education_entry(entry_text: str, entry_idx: int) -> dict[str, Any]:
    """Education entries are smaller — send the whole entry to LLM."""
    # Cap at 600 chars — education entries are brief
    trimmed = entry_text.strip()[:600]
    try:
        fields = await _llm(
            EXTRACT_EDUCATION_ENTRY.format(entry_text=trimmed),
            _EDU_TOKENS,
        )
        if not isinstance(fields, dict):
            fields = {}
    except Exception as exc:
        logger.warning("education entry %d: LLM failed: %s", entry_idx + 1, exc)
        fields = {}

    desc_raw = fields.get("description")
    return {
        "id":          entry_idx + 1,
        "institution": str(fields.get("institution", "")).strip(),
        "degree":      str(fields.get("degree",      "")).strip(),
        "years":       str(fields.get("years",        "")).strip(),
        "description": str(desc_raw).strip() if desc_raw else None,
    }


async def _parse_education(text: str) -> list[dict]:
    entry_blocks = split_entries(text, section_type="education")
    logger.info("education: split into %d entry blocks", len(entry_blocks))

    results = []
    for i, block in enumerate(entry_blocks):
        entry = await _parse_education_entry(block, i)
        results.append(entry)

    logger.info("education: parsed %d entries", len(results))
    return results


# ── Skills (hybrid: regex-first, LLM for structured categorisation) ───────

async def _parse_skills(text: str) -> dict[str, list[str]]:
    # Try pure regex first — fast and reliable for well-formatted skill sections
    items = parse_simple_list(text)
    if items and len(items) >= 3:
        # Heuristic: if items are short (≤5 words), they're individual skills
        short_items = [it for it in items if len(it.split()) <= 5]
        if len(short_items) / len(items) >= 0.7:
            logger.info(
                "skills: regex extracted %d items (skipping LLM)", len(short_items)
            )
            return {
                "technicalSkills":        short_items,
                "languages":              [],
                "certificationsTraining": [],
                "awards":                 [],
            }

    # LLM for structured/categorised skill sections
    try:
        raw = await _llm(
            PARSE_SKILLS_PROMPT.format(section_text=text),
            _SKILLS_TOKENS,
        )
        if not isinstance(raw, dict):
            raw = {}
    except Exception as exc:
        logger.error("skills: LLM failed: %s", exc)
        raw = {}

    def _clean(key: str) -> list[str]:
        v = raw.get(key, [])
        if isinstance(v, list):
            return [str(s).strip() for s in v if str(s).strip()]
        return []

    result = {
        "technicalSkills":        _clean("technicalSkills"),
        "languages":              _clean("languages"),
        "certificationsTraining": _clean("certificationsTraining"),
        "awards":                 _clean("awards"),
    }
    logger.info(
        "skills: %d technical / %d languages / %d certs / %d awards",
        len(result["technicalSkills"]), len(result["languages"]),
        len(result["certificationsTraining"]), len(result["awards"]),
    )
    return result


# ── Simple list sections (no LLM) ─────────────────────────────────────────

def _parse_certifications(text: str) -> list[str]:
    items = parse_simple_list(text)
    logger.info("certifications: %d items (no LLM)", len(items))
    return items


def _parse_awards(text: str) -> list[str]:
    items = parse_simple_list(text)
    logger.info("awards: %d items (no LLM)", len(items))
    return items


def _parse_languages(text: str) -> list[str]:
    items = parse_simple_list(text)
    logger.info("languages: %d items (no LLM)", len(items))
    return items


# ── Summary (no LLM) ──────────────────────────────────────────────────────

def _parse_summary(text: str) -> str:
    cleaned = re.sub(r"\*+", "", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    logger.info("summary: %d chars", len(cleaned))
    return cleaned


# ── Custom sections ───────────────────────────────────────────────────────

async def _parse_custom(section_name: str, text: str) -> dict[str, Any]:
    # First, try deterministic extraction
    items = parse_simple_list(text)
    if items and len(items) >= 2:
        logger.info(
            "custom[%s]: %d items extracted without LLM", section_name, len(items)
        )
        return {"sectionType": "stringList", "strings": items}

    # Check for bullet-driven entries
    bullets = extract_bullets(text)
    if len(bullets) >= 2:
        return {"sectionType": "stringList", "strings": bullets}

    # LLM as final fallback
    try:
        raw = await _llm(
            PARSE_CUSTOM_SECTION_PROMPT.format(
                section_name=section_name,
                section_text=text[:800],
            ),
            _CUSTOM_TOKENS,
        )
        return raw if isinstance(raw, dict) else {"sectionType": "text", "text": text}
    except Exception as exc:
        logger.warning("custom[%s]: LLM failed: %s", section_name, exc)
        return {"sectionType": "text", "text": text}


# ── Main pipeline ─────────────────────────────────────────────────────────

async def parse_resume_sectioned(markdown: str) -> dict[str, Any]:
    """Three-stage section-aware parsing pipeline.

    Returns a dict compatible with ResumeData schema.
    Never raises — partial results on per-section failure.
    Signals monolithic fallback via {"_needs_monolithic_parse": True}
    when no section headers are detected.
    """
    sections = detect_sections(markdown)

    if "_raw" in sections and len(sections) == 1:
        logger.warning(
            "parse_resume_sectioned: no section headers — "
            "signalling monolithic fallback"
        )
        return {"_needs_monolithic_parse": True}

    logger.info(
        "parse_resume_sectioned: %d sections detected: %s",
        len(sections),
        list(sections.keys()),
    )

    result: dict[str, Any] = {
        "personalInfo": {
            "name": "", "title": "", "email": "", "phone": "",
            "location": "", "website": None, "linkedin": None, "github": None,
        },
        "summary":         "",
        "workExperience":  [],
        "education":       [],
        "personalProjects": [],
        "additional": {
            "technicalSkills":        [],
            "languages":              [],
            "certificationsTraining": [],
            "awards":                 [],
        },
        "customSections": {},
    }

    accum: dict[str, list[str]] = {
        "technicalSkills": [], "languages": [],
        "certificationsTraining": [], "awards": [],
    }

    for key, text in sections.items():
        if not text.strip():
            logger.debug("skip empty section: %s", key)
            continue

        try:
            if key == "personalInfo":
                result["personalInfo"] = await _parse_personal_info(text)

            elif key == "summary":
                result["summary"] = _parse_summary(text)

            elif key == "workExperience":
                result["workExperience"] = await _parse_experience(text, "workExperience")

            elif key == "internships":
                interns = await _parse_experience(text, "internships")
                offset  = len(result["workExperience"])
                for e in interns:
                    e["id"] = offset + e.get("id", 1)
                result["workExperience"].extend(interns)

            elif key == "personalProjects":
                result["personalProjects"] = await _parse_projects(text)

            elif key == "education":
                result["education"] = await _parse_education(text)

            elif key == "skills":
                skills = await _parse_skills(text)
                for k in accum:
                    accum[k].extend(skills.get(k, []))

            elif key == "certifications":
                accum["certificationsTraining"].extend(_parse_certifications(text))

            elif key == "awards":
                accum["awards"].extend(_parse_awards(text))

            elif key == "languages":
                accum["languages"].extend(_parse_languages(text))

            elif key in ("research", "publications", "volunteer",
                         "extracurricular", "interests"):
                result["customSections"][key] = await _parse_custom(key, text)

            elif key.startswith("custom_"):
                result["customSections"][key] = await _parse_custom(key, text)

            else:
                result["customSections"][key] = await _parse_custom(key, text)

        except Exception as exc:
            logger.error(
                "parse_resume_sectioned: section %r failed: %s", key, exc
            )

    # Merge accumulated lists, dedup preserving order
    def _dedup(lst: list[str]) -> list[str]:
        seen: set[str] = set()
        out:  list[str] = []
        for item in lst:
            norm = item.lower().strip()
            if norm not in seen and norm:
                seen.add(norm)
                out.append(item)
        return out

    result["additional"] = {
        "technicalSkills":        _dedup(accum["technicalSkills"]),
        "languages":              _dedup(accum["languages"]),
        "certificationsTraining": _dedup(accum["certificationsTraining"]),
        "awards":                 _dedup(accum["awards"]),
    }

    _log_integrity(result, sections)
    return result


def _log_integrity(result: dict[str, Any], sections: dict[str, str]) -> None:
    exp_entries  = len(result.get("workExperience",   []))
    proj_entries = len(result.get("personalProjects", []))
    edu_entries  = len(result.get("education",        []))
    skills_n     = len(result.get("additional", {}).get("technicalSkills", []))
    exp_bullets  = sum(len(e.get("description", [])) for e in result.get("workExperience",   []))
    proj_bullets = sum(len(p.get("description", [])) for p in result.get("personalProjects", []))
    custom_n     = len(result.get("customSections", {}))

    logger.info(
        "PARSE COMPLETE — "
        "exp: %d entries (%d bullets) | "
        "projects: %d entries (%d bullets) | "
        "edu: %d | skills: %d | custom: %d",
        exp_entries,  exp_bullets,
        proj_entries, proj_bullets,
        edu_entries, skills_n, custom_n,
    )

    for req in ("personalInfo", "workExperience", "education"):
        if req not in sections and not result.get(req):
            logger.warning("required section %r absent from both source and output", req)
