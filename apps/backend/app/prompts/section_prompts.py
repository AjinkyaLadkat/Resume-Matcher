"""Per-section LLM prompts for the section-aware parsing pipeline.

Each prompt is intentionally small and asks for ONLY the content of
that section.  This keeps both input and output tokens low so even a
local Ollama model with a 4096-token output limit can parse each chunk
completely without truncation.

Design rules
------------
1. Ask for ONLY a JSON array or object — no explanatory wrapper.
2. Instruct the LLM to PRESERVE content exactly, never summarise.
3. Tell the LLM to copy bullet text verbatim, including metrics and tech.
4. Each prompt must end with: "Output ONLY valid JSON. No other text."
"""

# ── Work Experience & Internships ─────────────────────────────────────────

PARSE_EXPERIENCE_PROMPT = """\
Parse this work experience section into a JSON array.
Output ONLY a JSON array. No wrapper object. No explanation.

RULES — follow strictly:
- Create one object per role/position
- Copy EVERY bullet point VERBATIM — do not summarise, shorten, or rephrase
- Preserve all metrics (numbers, percentages, dollar amounts)
- Preserve all technology names, library names, and tool names exactly
- If a bullet spans multiple lines, join them into one string
- Keep months in date ranges: "Jan 2020 – Dec 2022", "May 2021 – Present"
- If a date has no month, use the year as-is: "2019 – 2021"
- "id" starts at 1 and increments for each entry
- Use empty string "" for any field you cannot find

Output format (JSON array):
[
  {{
    "id": 1,
    "title": "Job Title",
    "company": "Company Name",
    "location": "City, Country",
    "years": "Mon YYYY – Mon YYYY",
    "description": [
      "Exact bullet text preserved verbatim",
      "Another exact bullet"
    ]
  }}
]

Work experience section to parse:
{section_text}

Output ONLY valid JSON array. No other text."""


# ── Personal Projects ─────────────────────────────────────────────────────

PARSE_PROJECTS_PROMPT = """\
Parse this projects section into a JSON array.
Output ONLY a JSON array. No wrapper object. No explanation.

RULES — follow strictly:
- Create one object per project
- Copy EVERY bullet point VERBATIM — do not summarise, shorten, or rephrase
- Preserve ALL technical details: frameworks, libraries, algorithms, architectures
- Preserve ALL metrics: user counts, performance numbers, stars, downloads
- Preserve ALL technology names exactly as written
- If a bullet spans multiple lines, join them into one string
- Keep project dates/duration exactly: "Mar 2021 – Present", "2022"
- "role" is the candidate's role in the project (e.g. "Creator", "Lead Developer")
- If no role is stated, use empty string ""
- github/website: extract URL if present, otherwise null
- "id" starts at 1 and increments

Output format (JSON array):
[
  {{
    "id": 1,
    "name": "Project Name",
    "role": "Creator & Maintainer",
    "years": "Mon YYYY – Present",
    "github": "https://github.com/...",
    "website": null,
    "description": [
      "Exact bullet text preserved verbatim",
      "Another exact bullet with all technical details intact"
    ]
  }}
]

Projects section to parse:
{section_text}

Output ONLY valid JSON array. No other text."""


# ── Education ─────────────────────────────────────────────────────────────

PARSE_EDUCATION_PROMPT = """\
Parse this education section into a JSON array.
Output ONLY a JSON array. No wrapper object. No explanation.

RULES:
- Create one object per educational entry (degree, diploma, course)
- Preserve honours, GPA, thesis title, and coursework exactly
- Keep dates as found: "2016 – 2020", "Aug 2015 – May 2019"
- "description" is a single string (not array) — combine any descriptive lines
- "id" starts at 1 and increments

Output format (JSON array):
[
  {{
    "id": 1,
    "institution": "University Name",
    "degree": "B.S. Computer Science",
    "years": "2016 – 2020",
    "description": "GPA 3.9/4.0. Dean's List. Thesis: ..."
  }}
]

Education section to parse:
{section_text}

Output ONLY valid JSON array. No other text."""


# ── Skills / Technologies ─────────────────────────────────────────────────

PARSE_SKILLS_PROMPT = """\
Parse this skills section into categorised JSON lists.
Output ONLY a JSON object. No explanation.

RULES:
- technicalSkills: programming languages, frameworks, libraries, tools, platforms, databases, cloud services
- languages: spoken/written human languages (e.g. "English (Native)", "Spanish (B2)")
- certificationsTraining: certifications, courses, bootcamps, training programmes
- awards: awards, honours, scholarships
- Copy every item EXACTLY as written — do not abbreviate or rename
- If a category has no items, return an empty array []

Output format:
{{
  "technicalSkills": ["Python", "React", "AWS"],
  "languages": ["English (Native)"],
  "certificationsTraining": ["AWS Solutions Architect – Associate"],
  "awards": []
}}

Skills section to parse:
{section_text}

Output ONLY valid JSON object. No other text."""


# ── Certifications (standalone section) ──────────────────────────────────

PARSE_CERTIFICATIONS_PROMPT = """\
Parse this certifications/training section into a JSON array of strings.
Output ONLY a JSON array of strings. No explanation.

RULES:
- Each certification/course is one string
- Include issuer and date if present: "AWS Solutions Architect (2023, Amazon)"
- Copy names EXACTLY as written

Section to parse:
{section_text}

Output ONLY a JSON array of strings. No other text."""


# ── Awards / Achievements ─────────────────────────────────────────────────

PARSE_AWARDS_PROMPT = """\
Parse this awards/achievements section into a JSON array of strings.
Output ONLY a JSON array of strings. No explanation.

RULES:
- Each award or achievement is one string
- Preserve year, issuer, and description exactly as written
- If there are bullet points, each bullet is one string

Section to parse:
{section_text}

Output ONLY a JSON array of strings. No other text."""


# ── Languages ────────────────────────────────────────────────────────────

PARSE_LANGUAGES_PROMPT = """\
Parse this languages section into a JSON array of strings.
Output ONLY a JSON array of strings. No explanation.

RULES:
- Each language with its proficiency level is one string
- Preserve proficiency labels exactly: "French (B2)", "German – Native"
- If only the language name is given, just use that

Section to parse:
{section_text}

Output ONLY a JSON array of strings. No other text."""


# ── Personal Info (used as fallback when regex extraction misses fields) ──

PARSE_PERSONAL_INFO_PROMPT = """\
Extract personal/contact information from this resume header block.
Output ONLY a JSON object. No explanation.

RULES:
- Extract only what is explicitly present — do NOT invent any field
- Use empty string "" for any field you cannot find
- "title" is the professional headline/job title (not a salutation)
- "website" is a personal website or portfolio URL (not LinkedIn, not GitHub)
- "linkedin" is the LinkedIn profile URL or handle
- "github" is the GitHub profile URL or handle

Output format:
{{
  "name": "Full Name",
  "title": "Software Engineer",
  "email": "name@example.com",
  "phone": "+1-555-0100",
  "location": "San Francisco, CA",
  "website": "https://johndoe.dev",
  "linkedin": "linkedin.com/in/johndoe",
  "github": "github.com/johndoe"
}}

Header block to parse:
{section_text}

Output ONLY valid JSON object. No other text."""


# ── Custom / unrecognised sections ────────────────────────────────────────

PARSE_CUSTOM_SECTION_PROMPT = """\
Parse this resume section into structured JSON.
Output ONLY a JSON object. No explanation.

Choose the most appropriate output format:
- If it is a list of items (each with title/date/description):
  {{"sectionType": "itemList", "items": [{{"id": 1, "title": "...", "subtitle": "...", "years": "...", "description": ["exact bullet"]}}]}}
- If it is a simple list of strings:
  {{"sectionType": "stringList", "strings": ["item 1", "item 2"]}}
- If it is a single paragraph:
  {{"sectionType": "text", "text": "full text preserved verbatim"}}

RULES:
- PRESERVE all content verbatim — no summarising
- Copy bullet points exactly as written

Section name: {section_name}
Section content:
{section_text}

Output ONLY valid JSON object. No other text."""


# ═══════════════════════════════════════════════════════════════════════════
# Per-entry header prompts (Stage 3 — field extraction)
#
# These prompts receive ONLY the 3-5 header lines of a single entry.
# Bullet points are extracted deterministically by entry_splitter.py and
# are NEVER included in these prompts.
# ═══════════════════════════════════════════════════════════════════════════

EXTRACT_EXPERIENCE_HEADER = """\
Extract job title, company name, location, and date range from this work entry header.
Return ONLY a JSON object with exactly these keys.

RULES:
- Use empty string "" for any field not found
- "years" must be copied EXACTLY as written (e.g. "Jan 2020 – Present", "2019–2021")
- "title" is the job/role title only (not the company name)
- "company" is the employer/organisation name only
- "location" is city/country or empty string

Entry header (3-5 lines max):
{header_text}

Return ONLY: {{"title": "...", "company": "...", "location": "...", "years": "..."}}"""


EXTRACT_PROJECT_HEADER = """\
Extract project name, role, date range, and URLs from this project entry header.
Return ONLY a JSON object with exactly these keys.

RULES:
- Use empty string "" for missing text fields; null for missing URLs
- "name" is the project name
- "role" is the contributor role (e.g. "Creator", "Lead Developer") — empty if not stated
- "years" copied EXACTLY as written; empty string if absent
- "github": full GitHub URL if present, otherwise null
- "website": any other URL (portfolio, demo, paper) if present, otherwise null

Entry header:
{header_text}

Return ONLY: {{"name": "...", "role": "...", "years": "...", "github": null, "website": null}}"""


EXTRACT_EDUCATION_ENTRY = """\
Extract institution, degree, date range, and description from this single education entry.
Return ONLY a JSON object.

RULES:
- Copy fields EXACTLY as written
- "description": all additional info (GPA, honours, thesis, coursework) joined into one string; null if none

Education entry:
{entry_text}

Return ONLY: {{"institution": "...", "degree": "...", "years": "...", "description": null}}"""
