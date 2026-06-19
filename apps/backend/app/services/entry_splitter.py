"""Deterministic entry splitter for resume sections.

This is the critical Stage 2 layer between section detection (Stage 1)
and LLM field extraction (Stage 3).

Key principle: bullets are extracted HERE without any LLM.
The LLM only ever sees the 3-4 header lines of each entry (title, company,
dates). This means bullet content is NEVER subject to compression, merging,
or truncation by the model.

Public API
----------
split_entries(text, section_type)  → list[str]   one block per entry
extract_bullets(entry_text)         → list[str]   verbatim bullet strings
get_header_text(entry_text)         → str         non-bullet header lines
parse_simple_list(text)             → list[str]   certs / awards / languages
extract_urls(text)                  → dict        github + website URLs
"""

import re
import logging
from typing import Literal

logger = logging.getLogger(__name__)

SectionType = Literal[
    "workExperience", "personalProjects", "education",
    "internships", "volunteer", "research", "publications",
    "certifications", "awards", "languages", "custom",
]

# ── Core regex patterns ────────────────────────────────────────────────────

# Full date range: "Jan 2020 – Present", "2018 – 2021", "March 2020 to Dec 2022"
DATE_RANGE_RE = re.compile(
    r"(?:"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\.?\s*(?:'|')?\d{2,4}"
    r"|\d{4}"
    r")"
    r"\s*(?:–|—|‒|―|-|to|till|until)\s*"
    r"(?:"
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
    r"Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
    r"\.?\s*(?:'|')?\d{2,4}"
    r"|\d{4}"
    r"|Present|Current|Now|Ongoing|Today|Continuing|Till\s+[Dd]ate"
    r")",
    re.IGNORECASE,
)

# Single year – only used as a weak signal in context
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

# Bullet markers: -, *, •, ►, ▸, ▹, ◆, ◦, or numbered
BULLET_RE = re.compile(r"^\s*(?:[-*•►▸▹◆◦‣⁃]|\d+[.):])\s+\S")

# Markdown ATX headers (##, ###, ####) – strongest entry boundary signal
MARKDOWN_HDR_RE = re.compile(r"^#{1,4}\s+.+")

# Bold-only line: **text** (nothing else on the line)
BOLD_ONLY_RE = re.compile(r"^\*\*[^*\n]{2,80}\*\*\s*$")

# Horizontal rule separator
HR_RE = re.compile(r"^[-_*=]{3,}\s*$")

# GitHub URL — with or without https:// prefix
GITHUB_RE = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/[\w\-./#]+",
    re.IGNORECASE,
)

# Generic URL (for website/portfolio extraction)
URL_RE = re.compile(r"https?://[^\s,<>\"')\]]+")


# ── Line tagging ───────────────────────────────────────────────────────────

def _tag(line: str) -> str:
    """Classify a single line."""
    stripped = line.strip()
    if not stripped:
        return "blank"
    if HR_RE.match(stripped):
        return "hr"
    if BULLET_RE.match(line):
        return "bullet"
    if MARKDOWN_HDR_RE.match(line):
        return "md_header"
    if BOLD_ONLY_RE.match(stripped):
        return "bold"
    if DATE_RANGE_RE.search(stripped) and not BULLET_RE.match(line):
        return "date_text"
    return "text"


# ── Core splitting strategies ──────────────────────────────────────────────

def _split_by_markdown_headers(lines: list[str], tags: list[str]) -> list[list[str]]:
    """Split at every markdown ATX header line."""
    groups: list[list[str]] = []
    current: list[str] = []
    for line, tag in zip(lines, tags):
        if tag == "md_header" and current:
            groups.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        groups.append(current)
    return groups


def _split_by_date_proximity(lines: list[str], tags: list[str]) -> list[list[str]]:
    """Split using date-range lines as entry anchors.

    Algorithm:
      For each date-range line, look back up to 3 non-blank lines to find
      the entry 'title' line (first non-blank, non-bullet line before the date).
      That title line becomes the entry start.
    """
    n = len(lines)
    starts: set[int] = set()

    # First non-blank line always starts an entry
    for i, tag in enumerate(tags):
        if tag != "blank":
            starts.add(i)
            break

    for i, tag in enumerate(tags):
        if tag != "date_text":
            continue
        # The date line itself is either the start or part of a started entry.
        # Look backward for the title line.
        title_idx = None
        for j in range(i - 1, max(i - 4, -1), -1):
            if tags[j] == "blank":
                continue
            if tags[j] in ("bullet",):
                break  # date is inside a bullet block, not a new entry
            if tags[j] in ("text", "bold", "date_text"):
                title_idx = j
                break

        if title_idx is not None:
            # Verify there's a blank line BEFORE this title (or it's at the start)
            has_blank_before = title_idx == 0 or any(
                tags[k] == "blank" for k in range(max(0, title_idx - 2), title_idx)
            )
            if has_blank_before:
                starts.add(title_idx)
        elif all(tags[k] == "blank" or k == i for k in range(max(0, i - 2), i)):
            # Date line is immediately after blanks — it IS the entry start
            starts.add(i)

    sorted_starts = sorted(starts)
    if len(sorted_starts) <= 1:
        return []  # Signal: fall through to blank-line split

    groups: list[list[str]] = []
    for idx, start in enumerate(sorted_starts):
        end = sorted_starts[idx + 1] if idx + 1 < len(sorted_starts) else n
        block = lines[start:end]
        if any(ln.strip() for ln in block):
            groups.append(block)
    return groups


def _split_by_blank_lines(text: str) -> list[list[str]]:
    """Fallback: split on one-or-more consecutive blank lines."""
    blocks = re.split(r"\n(?:\s*\n)+", text.strip())
    return [b.splitlines() for b in blocks if b.strip()]


# ── Public entry point ─────────────────────────────────────────────────────

def split_entries(text: str, section_type: SectionType = "custom") -> list[str]:
    """Split section text into individual entry blocks.

    Returns a list of raw text strings, one per entry.
    Never returns an empty list — returns [text] as a single entry
    if splitting produces no meaningful boundaries.
    """
    if not text.strip():
        return []

    lines = text.splitlines()
    tags  = [_tag(ln) for ln in lines]

    # ── Strategy 1: markdown headers (most reliable) ──────────────────────
    has_md_headers = any(t == "md_header" for t in tags)
    if has_md_headers:
        groups = _split_by_markdown_headers(lines, tags)
        result = [
            "\n".join(g).strip() for g in groups
            if any(l.strip() for l in g)
        ]
        result = [r for r in result if not _is_phantom_block(r)]
        if len(result) > 1:
            logger.debug(
                "split_entries[%s]: markdown header split → %d entries",
                section_type, len(result),
            )
            return result

    # ── Strategy 2: date-proximity (plain text resumes) ───────────────────
    groups = _split_by_date_proximity(lines, tags)
    if groups and len(groups) > 1:
        result = [
            "\n".join(g).strip() for g in groups
            if any(l.strip() for l in g)
        ]
        result = [r for r in result if not _is_phantom_block(r)]
        if len(result) > 1:
            logger.debug(
                "split_entries[%s]: date-proximity split → %d entries",
                section_type, len(result),
            )
            return result

    # ── Strategy 3: bold-line boundaries (DOCX-derived resumes) ──────────
    bold_indices = [i for i, t in enumerate(tags) if t == "bold"]
    if len(bold_indices) >= 2:
        well_separated = any(
            bold_indices[j + 1] - bold_indices[j] > 3
            for j in range(len(bold_indices) - 1)
        )
        if well_separated:
            groups = _split_by_markdown_headers(
                [ln if t != "bold" else "## " + ln.strip().strip("*")
                 for ln, t in zip(lines, tags)],
                ["md_header" if t == "bold" else t for t in tags],
            )
            result = [
                "\n".join(g).strip() for g in groups
                if any(l.strip() for l in g)
            ]
            result = [r for r in result if not _is_phantom_block(r)]
            if len(result) > 1:
                logger.debug(
                    "split_entries[%s]: bold-line split → %d entries",
                    section_type, len(result),
                )
                return result

    # ── Strategy 4: blank-line segmentation (fallback) ────────────────────
    groups = _split_by_blank_lines(text)
    if len(groups) > 1:
        result = [
            "\n".join(g).strip() for g in groups
            if any(l.strip() for l in g)
        ]
        result = [r for r in result if not _is_phantom_block(r)]
        logger.debug(
            "split_entries[%s]: blank-line fallback → %d blocks",
            section_type, len(result),
        )
        return result if result else [text.strip()]

    # Single block — return as-is
    logger.debug("split_entries[%s]: single block, no split", section_type)
    return [text.strip()]


def _is_phantom_block(block: str) -> bool:
    """Return True for stray section-header remnants that contain no real entry data.

    These appear when the caller passes text that still has a section header
    line at the top (e.g. "WORK EXPERIENCE") that was not stripped by
    detect_sections.  Characteristics:
      - Very few lines (≤ 2 non-blank lines)
      - No bullet points
      - No date range
      - Looks like a plain section heading
    """
    lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
    if len(lines) > 3:
        return False
    has_bullet  = any(BULLET_RE.match(ln) for ln in lines)
    has_date    = any(DATE_RANGE_RE.search(ln) for ln in lines)
    if has_bullet or has_date:
        return False
    # Short all-caps or markdown-header-looking block with no real content
    all_caps_or_header = all(
        ln.isupper() or MARKDOWN_HDR_RE.match(ln) or BOLD_ONLY_RE.match(ln)
        for ln in lines
    )
    return all_caps_or_header


# ── Bullet extraction ──────────────────────────────────────────────────────

def extract_bullets(entry_text: str) -> list[str]:
    """Extract all bullet points from an entry block verbatim.

    Handles:
    - Standard bullets: -, *, •, ►, ▸
    - Numbered lists: 1. 2. 3.
    - Continuation lines (indented text after a bullet)
    - Multi-line bullets joined into single strings

    IMPORTANT: This function never calls an LLM. Bullets are the most
    critical content to preserve and are extracted deterministically.
    """
    lines      = entry_text.splitlines()
    bullets    : list[str] = []
    current    : str | None = None
    in_header  = True  # Skip the header lines before first bullet

    for line in lines:
        stripped = line.strip()

        if not stripped:
            # Blank line may separate header from body, or separate bullets
            if current is not None:
                bullets.append(current)
                current = None
            continue

        if BULLET_RE.match(line):
            in_header = False
            if current is not None:
                bullets.append(current)
            # Strip bullet marker
            content = re.sub(r"^\s*[-*•►▸▹◆◦‣⁃]\s*", "", stripped)
            content = re.sub(r"^\d+[.):\s]\s*", "", content).strip()
            current = content

        elif current is not None:
            # Possible continuation line: indented more than 0, not a header
            is_continuation = (
                len(line) - len(line.lstrip()) >= 2  # at least 2 spaces indent
                and not MARKDOWN_HDR_RE.match(line)
                and not BOLD_ONLY_RE.match(stripped)
                and not DATE_RANGE_RE.search(stripped)
            )
            if is_continuation:
                current += " " + stripped
            else:
                bullets.append(current)
                current = None
                # Don't discard this line — it might be a new section header
        # else: still in header, or a text line before first bullet — skip

    if current is not None:
        bullets.append(current)

    return [b.strip() for b in bullets if b.strip()]


# ── Header extraction ──────────────────────────────────────────────────────

def get_header_text(entry_text: str, max_lines: int = 5) -> str:
    """Return only the header lines of an entry (before the first bullet).

    This is the only text sent to the LLM for field extraction.
    Keeping it small (3-4 lines) keeps token cost minimal and prevents
    the LLM from being distracted by bullet content.
    """
    lines   = entry_text.splitlines()
    header  : list[str] = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            if header:  # blank line after some header content = end of header
                break
            continue
        if BULLET_RE.match(line):
            break  # first bullet = end of header
        # Strip markdown header markers for cleaner LLM input
        clean = re.sub(r"^#{1,4}\s*", "", stripped)
        clean = re.sub(r"\*\*([^*]+)\*\*", r"\1", clean)  # unbold
        if clean:
            header.append(clean)
        if len(header) >= max_lines:
            break

    return "\n".join(header)


# ── URL extraction ─────────────────────────────────────────────────────────

def extract_urls(text: str) -> dict[str, str | None]:
    """Extract GitHub and website URLs from entry text.

    Handles URLs with and without https:// prefix.
    """
    github  : str | None = None
    website : str | None = None

    gh_match = GITHUB_RE.search(text)
    if gh_match:
        raw = gh_match.group(0).rstrip(".,)")
        # Normalise: ensure https:// prefix
        github = raw if raw.startswith("http") else "https://" + raw

    for url_match in URL_RE.finditer(text):
        url = url_match.group(0).rstrip(".,)")
        if "github.com" in url.lower():
            if github is None:
                github = url
        elif "linkedin.com" not in url.lower():
            if website is None:
                website = url

    return {"github": github, "website": website}


# ── Simple list parsing (no LLM) ──────────────────────────────────────────

def parse_simple_list(text: str) -> list[str]:
    """Extract a section as a flat list of strings — no LLM needed.

    Used for: certifications, awards, languages, simple skill lists.

    Handles:
    - Bullet-prefixed lines
    - Comma-separated items on one line
    - Numbered lists
    - Plain lines (one item per line)
    """
    items: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Skip section header lines
        if MARKDOWN_HDR_RE.match(line) or BOLD_ONLY_RE.match(stripped):
            continue

        if BULLET_RE.match(line):
            content = re.sub(r"^\s*[-*•►▸▹◆◦‣⁃]\s*", "", stripped)
            content = re.sub(r"^\d+[.):\s]\s*", "", content).strip()
            # A single bullet line might contain comma-separated sub-items
            sub = [s.strip() for s in content.split(",") if s.strip()]
            if len(sub) > 3:
                # Treat as comma-separated list
                items.extend(sub)
            elif content:
                items.append(content)
        elif "," in stripped and len(stripped) < 200:
            # Comma-separated items on a plain line
            sub = [s.strip() for s in stripped.split(",") if s.strip()]
            if len(sub) >= 2:
                items.extend(sub)
            else:
                items.append(stripped)
        else:
            items.append(stripped)

    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower().strip()
        if key not in seen and key:
            seen.add(key)
            result.append(item)
    return result


# ── Diagnostics ───────────────────────────────────────────────────────────

def diagnose_section(section_text: str, section_type: str, parsed_entries: list) -> None:
    """Log diagnostic info comparing source text vs parsed output."""
    source_bullets   = _count_source_bullets(section_text)
    source_entries   = _estimate_source_entries(section_text, section_type)
    parsed_count     = len(parsed_entries)
    parsed_bullets   = sum(
        len(e.get("description", []) if isinstance(e, dict) else [])
        for e in parsed_entries
    )

    logger.info(
        "[%s] source: ~%d entries / ~%d bullets  →  parsed: %d entries / %d bullets",
        section_type,
        source_entries, source_bullets,
        parsed_count,   parsed_bullets,
    )

    if parsed_count < source_entries:
        logger.warning(
            "[%s] ENTRY LOSS: expected ~%d, got %d  (diff=%d)",
            section_type, source_entries, parsed_count,
            source_entries - parsed_count,
        )
    if source_bullets > 0 and parsed_bullets < int(source_bullets * 0.75):
        logger.warning(
            "[%s] BULLET LOSS: source ~%d, parsed %d  (%.0f%% retained)",
            section_type, source_bullets, parsed_bullets,
            100 * parsed_bullets / source_bullets if source_bullets else 0,
        )


def _count_source_bullets(text: str) -> int:
    return sum(1 for ln in text.splitlines() if BULLET_RE.match(ln))


def _estimate_source_entries(text: str, section_type: str) -> int:
    """Rough count of expected entries based on date-range occurrences."""
    if section_type in ("certifications", "awards", "languages"):
        return len(parse_simple_list(text))
    dates = DATE_RANGE_RE.findall(text)
    if dates:
        return len(dates)
    # Fall back to blank-line block count
    blocks = [b for b in re.split(r"\n\s*\n", text) if b.strip()]
    return max(1, len(blocks))
