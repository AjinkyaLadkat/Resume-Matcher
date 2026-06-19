"""Section detection engine for resume markdown.

Pure regex/heuristic logic — no LLM involved.  Splits a resume's raw
markdown into labelled text chunks so each section can be parsed
independently, preventing the token-budget truncation that kills the
single-call approach.

Public API
----------
detect_sections(markdown)  → dict[canonical_key, raw_text]
classify_header(text)      → canonical_key | None
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# ── Canonical section keys ─────────────────────────────────────────────────
#
# These map to the output schema and are used throughout the parsing
# pipeline to keep naming consistent.
#
CANONICAL = {
    # Standard ResumeData fields
    "personalInfo":     "personalInfo",
    "summary":          "summary",
    "workExperience":   "workExperience",
    "education":        "education",
    "personalProjects": "personalProjects",
    "skills":           "skills",       # → merged into additional.technicalSkills
    "languages":        "languages",    # → merged into additional.languages
    "certifications":   "certifications",  # → merged into additional.certificationsTraining
    "awards":           "awards",       # → merged into additional.awards
    # Custom section buckets
    "internships":      "internships",
    "research":         "research",
    "publications":     "publications",
    "volunteer":        "volunteer",
    "extracurricular":  "extracurricular",
    "interests":        "interests",
}

# ── Header → canonical mapping ────────────────────────────────────────────
#
# Keys are lowercased, stripped header texts (or substrings).
# Longer/more-specific phrases first so they match before shorter ones.
#
_HEADER_MAP: list[tuple[str, str]] = [
    # Work experience
    ("professional experience",  "workExperience"),
    ("work experience",          "workExperience"),
    ("work history",             "workExperience"),
    ("employment history",       "workExperience"),
    ("career history",           "workExperience"),
    ("relevant experience",      "workExperience"),
    ("industry experience",      "workExperience"),
    ("experience",               "workExperience"),
    ("employment",               "workExperience"),
    # Internships (before "experience" so it captures "internship experience")
    ("internship experience",    "internships"),
    ("internships",              "internships"),
    ("internship",               "internships"),
    # Projects
    ("personal projects",        "personalProjects"),
    ("side projects",            "personalProjects"),
    ("open source projects",     "personalProjects"),
    ("open source",              "personalProjects"),
    ("project experience",       "personalProjects"),
    ("selected projects",        "personalProjects"),
    ("academic projects",        "personalProjects"),
    ("notable projects",         "personalProjects"),
    ("projects",                 "personalProjects"),
    # Education
    ("academic background",      "education"),
    ("academic qualifications",  "education"),
    ("educational background",   "education"),
    ("education and training",   "education"),
    ("education",                "education"),
    ("qualifications",           "education"),
    ("degrees",                  "education"),
    # Skills
    ("technical skills",         "skills"),
    ("core competencies",        "skills"),
    ("key competencies",         "skills"),
    ("technical competencies",   "skills"),
    ("areas of expertise",       "skills"),
    ("skills & technologies",    "skills"),
    ("technologies",             "skills"),
    ("tools & technologies",     "skills"),
    ("programming languages",    "skills"),
    ("technical expertise",      "skills"),
    ("skills",                   "skills"),
    ("competencies",             "skills"),
    ("expertise",                "skills"),
    ("technologies used",        "skills"),
    # Summary / Profile
    ("professional summary",     "summary"),
    ("executive summary",        "summary"),
    ("career objective",         "summary"),
    ("career summary",           "summary"),
    ("personal statement",       "summary"),
    ("profile summary",          "summary"),
    ("professional profile",     "summary"),
    ("about me",                 "summary"),
    ("objective",                "summary"),
    ("summary",                  "summary"),
    ("profile",                  "summary"),
    ("overview",                 "summary"),
    ("about",                    "summary"),
    # Certifications
    ("certifications & training", "certifications"),
    ("certifications and training", "certifications"),
    ("professional certifications", "certifications"),
    ("licenses and certifications", "certifications"),
    ("certifications",           "certifications"),
    ("certificates",             "certifications"),
    ("training",                 "certifications"),
    ("courses",                  "certifications"),
    ("professional development", "certifications"),
    # Languages
    ("languages",                "languages"),
    ("language skills",          "languages"),
    # Awards / Achievements
    ("honors and awards",        "awards"),
    ("awards and recognition",   "awards"),
    ("achievements and awards",  "awards"),
    ("achievements",             "awards"),
    ("awards",                   "awards"),
    ("honors",                   "awards"),
    ("recognition",              "awards"),
    ("accomplishments",          "awards"),
    # Research / Publications
    ("research experience",      "research"),
    ("research publications",    "publications"),
    ("publications",             "publications"),
    ("research",                 "research"),
    # Volunteer / Extra
    ("volunteer experience",     "volunteer"),
    ("community involvement",    "volunteer"),
    ("volunteer work",           "volunteer"),
    ("volunteering",             "volunteer"),
    ("extracurricular activities", "extracurricular"),
    ("extracurricular",          "extracurricular"),
    ("activities",               "extracurricular"),
    ("interests",                "interests"),
    ("hobbies",                  "interests"),
    ("hobbies & interests",      "interests"),
]


def classify_header(header_text: str) -> str | None:
    """Map a raw section header string to a canonical key.

    Returns None when the header doesn't match any known section.
    Matching is substring-based: "Work Experience (2018-Present)"
    still maps to "workExperience".
    """
    normalised = header_text.lower().strip()
    # Strip trailing punctuation and common suffixes
    normalised = re.sub(r"[:\-–—]+$", "", normalised).strip()

    for phrase, canonical_key in _HEADER_MAP:
        if phrase in normalised:
            return canonical_key
    return None


# ── Header detection patterns ──────────────────────────────────────────────
#
# Ordered from most- to least-specific.  Each is tried in sequence; the
# first match wins for a given line.
#
_HEADER_PATTERNS: list[re.Pattern[str]] = [
    # Markdown ATX headers:  ## Work Experience
    re.compile(r"^#{1,4}\s+(.+?)\s*#*\s*$", re.MULTILINE),
    # Setext-style underline:  Work Experience\n==================
    re.compile(r"^(.+?)\n[=\-]{3,}\s*$", re.MULTILINE),
    # Bold-only lines (entire line bold, common in DOCX→MD):  **Work Experience**
    re.compile(r"^\*\*([^*\n]{3,60})\*\*\s*$", re.MULTILINE),
    # ALL-CAPS lines (min 4 chars, allow spaces, &, /):  WORK EXPERIENCE
    re.compile(r"^([A-Z][A-Z0-9 &/\-]{3,60})$", re.MULTILINE),
    # Title-cased lines ending in colon (and nothing else):  Work Experience:
    re.compile(r"^([A-Z][A-Za-z0-9 &/\-]{3,60}):$", re.MULTILINE),
]


def detect_sections(markdown: str) -> dict[str, str]:
    """Split resume markdown into labelled section chunks.

    Returns a dict mapping canonical section keys to their raw text.
    Unrecognised section headers are preserved under a generated key
    ("custom_<n>") so no content is ever discarded.

    The "personalInfo" key always maps to the text before the first
    recognised section header, which typically contains the candidate's
    contact information.

    Sections with duplicate canonical keys are concatenated (e.g. two
    "Skills" blocks → one "skills" entry).
    """
    if not markdown or not markdown.strip():
        logger.warning("detect_sections: empty markdown received")
        return {}

    # --- Step 1: find ALL header positions ---------------------------------
    # Collect (start_pos, header_text) tuples from every pattern.
    raw_hits: list[tuple[int, str]] = []

    for pattern in _HEADER_PATTERNS:
        for m in pattern.finditer(markdown):
            header_text = m.group(1).strip()
            raw_hits.append((m.start(), header_text))

    if not raw_hits:
        logger.info(
            "detect_sections: no section headers found — "
            "returning full text as single chunk (monolithic fallback)"
        )
        return {"_raw": markdown}

    # Sort by position, deduplicate overlapping matches (keep earliest)
    raw_hits.sort(key=lambda x: x[0])
    deduped: list[tuple[int, str]] = []
    last_end = -1
    for pos, header in raw_hits:
        if pos < last_end:
            continue
        deduped.append((pos, header))
        last_end = pos + len(header) + 10  # rough overlap window

    # --- Step 2: extract text between headers --------------------------------
    sections: dict[str, str] = {}
    custom_count = 0

    # Text before the first header → personal info block
    preamble = markdown[: deduped[0][0]].strip()
    if preamble:
        sections["personalInfo"] = preamble

    for i, (pos, header_text) in enumerate(deduped):
        # Section body = everything after the header line until the next header
        line_end = markdown.find("\n", pos)
        body_start = line_end + 1 if line_end != -1 else pos + len(header_text)

        if i + 1 < len(deduped):
            body_end = deduped[i + 1][0]
        else:
            body_end = len(markdown)

        body = markdown[body_start:body_end].strip()
        canonical_key = classify_header(header_text)

        if canonical_key:
            key = canonical_key
        else:
            custom_count += 1
            key = f"custom_{custom_count}"
            logger.debug(
                "detect_sections: unrecognised header %r → %s", header_text, key
            )

        # Concatenate if key already seen (duplicate sections)
        if key in sections:
            sections[key] = sections[key] + "\n\n" + body
        else:
            sections[key] = body

    # --- Step 3: log what was found ----------------------------------------
    counts = {k: len(v) for k, v in sections.items()}
    logger.info(
        "detect_sections: found %d sections — %s",
        len(sections),
        counts,
    )

    # Warn about suspiciously empty sections
    for key, text in sections.items():
        if not text.strip():
            logger.warning("detect_sections: section %r is empty after detection", key)

    return sections


def count_bullets(text: str) -> int:
    """Count bullet-like lines in a text block (for truncation detection)."""
    bullet_re = re.compile(r"^\s*(?:[-*•►▸▹◆◦‣⁃]|\d+[.):])\s+\S", re.MULTILINE)
    return len(bullet_re.findall(text))


def estimate_entry_count(text: str) -> int:
    """Rough estimate of how many experience/project entries are in a block.

    Counts lines that look like a job title or company header (contain
    a date range, or match a bold/caps pattern).
    """
    date_re = re.compile(
        r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|\d{4})"
        r"[^|\n]{0,40}"
        r"(?:\d{4}|Present|Current|Now)",
        re.IGNORECASE,
    )
    lines_with_dates = sum(1 for ln in text.splitlines() if date_re.search(ln))
    return max(1, lines_with_dates)
