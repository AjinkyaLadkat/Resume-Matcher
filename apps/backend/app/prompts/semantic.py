"""LLM prompt templates for semantic contextual fit analysis.

Used by services/scorer.py to generate human-readable fit summaries,
strengths, gaps, and recommendations after embedding-based scoring.
"""

CONTEXTUAL_FIT_ANALYSIS_PROMPT = """\
You are a senior technical recruiter performing a contextual fit analysis.

SEMANTIC SECTION SCORES (computed via embedding cosine similarity, 0–100):
{section_scores}

OVERALL SEMANTIC SCORE: {overall_score}/100

CANDIDATE PROFILE:
{resume_summary}

JOB DESCRIPTION (excerpt):
{job_description}

REQUIRED SKILLS: {required_skills}
PREFERRED SKILLS: {preferred_skills}

Analyze the fit and return ONLY a JSON object with this exact structure:
{{
  "fit_summary": "2-3 sentence summary covering overall alignment quality and dominant themes",
  "strengths": [
    "Specific strength referencing actual resume content vs job needs",
    "Specific strength 2",
    "Specific strength 3"
  ],
  "gaps": [
    "Specific gap citing a required skill or responsibility not evidenced in resume",
    "Specific gap 2"
  ],
  "recommendation": "One concrete sentence: what change to this resume would most improve its fit for this role"
}}

RULES (follow strictly):
- fit_summary: reference concrete role titles, skills, or experience from both sides
- strengths: 2–4 items; only include genuine matches, never generic praise
- gaps: 1–3 items; only required skills / core responsibilities missing from resume
- recommendation: actionable and specific (e.g. "Add a bullet to the X role describing Y")
- If overall_score > 75: tone is positive with minor suggestions
- If overall_score 50–75: constructive tone noting solid foundation with clear next steps
- If overall_score < 50: honest about gaps but highlight transferable strengths
- Output ONLY valid JSON — no markdown, no preamble, no trailing text\
"""
