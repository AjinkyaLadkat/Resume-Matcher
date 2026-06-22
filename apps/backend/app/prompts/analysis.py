"""LLM prompts for the four semantic-analysis features.

Design principle shared across all four: every prompt receives PRE-COMPUTED
context (section scores, cached job_keywords, resume summary) rather than
raw full-text, keeping each call small and focused — consistent with the
rest of the codebase's "small focused calls over monolithic ones" pattern.
"""

# ── 1. Skill Gap Analysis ──────────────────────────────────────────────────

SKILL_GAP_ANALYSIS_PROMPT = """\
You are a technical recruiter performing a skill gap analysis.

JOB REQUIREMENTS:
Required skills: {required_skills}
Preferred skills: {preferred_skills}
Key responsibilities: {key_responsibilities}

CANDIDATE'S RESUME:
Technical skills listed: {resume_skills}
Experience summary:
{experience_summary}
Projects summary:
{projects_summary}

SEMANTIC SECTION SCORES (for context — lower scores indicate weaker alignment):
{section_scores}

TASK:
Categorise the gap between job requirements and the resume into three groups.

1. CRITICAL MISSING: required skills with NO evidence anywhere in the resume
   (not in skills list, not implied by experience/projects)
2. NICE_TO_HAVE MISSING: preferred (non-required) skills missing from the resume
3. RELATED SKILLS DEMONSTRATED: JD skills that aren't explicitly listed but ARE
   evidenced by related resume content (e.g. JD wants "Kubernetes", resume shows
   "Docker" — that's relevant prior art, not a clean match, but real evidence)

For each CRITICAL or NICE_TO_HAVE item, also provide:
- why_it_matters: one sentence on why this skill matters for the role
- estimated_score_impact: qualitative estimate, e.g. "could raise Skills score by 5-10 pts"
- suggested_placement: realistically, where could this be added — "skills", "projects",
  "experience", or "summary" (only suggest if the candidate could honestly claim it)

Output ONLY this JSON structure:
{{
  "critical_missing": [
    {{"skill": "...", "why_it_matters": "...", "estimated_score_impact": "...", "suggested_placement": "..."}}
  ],
  "nice_to_have_missing": [
    {{"skill": "...", "why_it_matters": "...", "estimated_score_impact": "...", "suggested_placement": "..."}}
  ],
  "related_skills_demonstrated": [
    {{"jd_skill": "...", "resume_evidence": "...", "explanation": "..."}}
  ],
  "summary": "1-2 sentence overview of the overall skill gap"
}}

RULES:
- Be specific — never output generic skills like "communication" unless explicitly required
- critical_missing: 2-6 items max, ordered by importance
- nice_to_have_missing: 0-4 items max
- related_skills_demonstrated: 0-5 items max
- Do not suggest placement for a skill the candidate has zero realistic claim to
- Output ONLY valid JSON — no markdown, no preamble\
"""


# ── 2. Strengths & Weaknesses (upgrade to existing contextual analysis) ───

CONTEXTUAL_FIT_ANALYSIS_PROMPT_V2 = """\
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
  "strengths_detailed": [
    {{
      "strength": "specific, non-generic strength statement",
      "evidence": "the exact resume content (bullet, skill, or project) that supports this",
      "relevance": "why this specifically matters for THIS job's requirements"
    }}
  ],
  "weaknesses_detailed": [
    {{
      "weakness": "specific, non-generic weakness statement",
      "jd_requirement": "the specific JD requirement or responsibility this relates to",
      "weakness_type": "missing_experience | missing_evidence | weak_alignment"
    }}
  ],
  "recommendation": "One concrete sentence: what change to this resume would most improve its fit for this role"
}}

RULES (follow strictly):
- strengths_detailed: 3-5 items. Each MUST cite specific resume content as evidence — "strong technical skills" without an evidence quote is REJECTED, not generic praise.
- weaknesses_detailed: 3-5 items. Each MUST tie to a specific JD requirement — "needs more experience" without naming what experience is REJECTED.
- NEVER output generic filler such as "improve your skills" or "add more details" — every item must be specific enough that removing the JD/resume context would make the claim false for a different candidate.
- weakness_type: "missing_experience" = role/responsibility never held; "missing_evidence" = candidate may have done it but didn't write it down; "weak_alignment" = present but tangential to JD need.
- fit_summary: reference concrete role titles, skills, or experience from both sides
- recommendation: actionable and specific (e.g. "Add a bullet to the X role describing Y")
- If overall_score > 75: tone is positive with minor suggestions
- If overall_score 50–75: constructive tone noting solid foundation with clear next steps
- If overall_score < 50: honest about gaps but highlight transferable strengths
- Output ONLY valid JSON — no markdown, no preamble, no trailing text\
"""


# ── 3. AI Interview Questions ──────────────────────────────────────────────

INTERVIEW_QUESTIONS_PROMPT = """\
You are a hiring manager preparing interview questions for this specific candidate and role.

CANDIDATE'S RESUME SUMMARY:
{resume_summary}

CANDIDATE'S KEY EXPERIENCE:
{experience_summary}

CANDIDATE'S PROJECTS:
{projects_summary}

JOB DESCRIPTION (excerpt):
{job_description}

REQUIRED SKILLS: {required_skills}

SEMANTIC ANALYSIS CONTEXT (use to target weak areas with probing questions):
Weakest section: {weakest_section} ({weakest_score}/100)
Known gaps: {known_gaps}

TASK:
Generate interview questions SPECIFIC to this resume and this JD. Never generate generic
questions like "tell me about yourself" or "what are your strengths" — every question must
reference something concrete from either the resume or the JD.

Generate questions across 5 categories:
1. TECHNICAL (3-4 questions): probe technical depth on skills/tools claimed in the resume
   that are also relevant to the JD
2. PROJECT (2-3 questions): dig into specific projects from the resume — architecture
   decisions, tradeoffs, what they'd do differently
3. BEHAVIORAL (2-3 questions): situational questions tied to JD responsibilities
   (e.g. if JD mentions "cross-functional collaboration", ask about a specific instance)
4. RESUME_SPECIFIC (2-3 questions): questions that probe claims in the resume that lack
   detail or metrics — especially around the weakest semantic section identified above
5. JD_SPECIFIC (2-3 questions): questions testing whether the candidate can do something
   the JD requires but the resume doesn't clearly demonstrate

For each question include:
- difficulty: "easy", "medium", or "hard"
- rationale: one sentence on WHY an interviewer would ask this, citing the specific
  resume content or JD requirement that motivated it

Output ONLY this JSON structure:
{{
  "technical": [
    {{"question": "...", "category": "technical", "difficulty": "medium", "rationale": "..."}}
  ],
  "project": [
    {{"question": "...", "category": "project", "difficulty": "medium", "rationale": "..."}}
  ],
  "behavioral": [
    {{"question": "...", "category": "behavioral", "difficulty": "easy", "rationale": "..."}}
  ],
  "resume_specific": [
    {{"question": "...", "category": "resume_specific", "difficulty": "medium", "rationale": "..."}}
  ],
  "jd_specific": [
    {{"question": "...", "category": "jd_specific", "difficulty": "hard", "rationale": "..."}}
  ]
}}

RULES:
- Every question must name a specific technology, project, or responsibility — no generic questions
- rationale must reference the SPECIFIC resume bullet/project or JD requirement that motivated the question
- Vary difficulty across each category — not all "medium"
- Output ONLY valid JSON — no markdown, no preamble\
"""


# ── 4. LinkedIn Headline Generator ─────────────────────────────────────────

LINKEDIN_HEADLINE_PROMPT = """\
You are a personal branding expert writing LinkedIn headlines for this candidate.

CANDIDATE PROFILE:
Current title: {current_title}
Top skills: {top_skills}
Years of experience signal: {experience_signal}
Most relevant experience:
{experience_summary}

{job_context_section}

TASK:
Generate 4 distinct LinkedIn headline variants, each ≤220 characters (LinkedIn's limit),
each serving a different purpose:

1. PROFESSIONAL: formal, role-focused, emphasises core expertise and seniority
2. RECRUITER_FRIENDLY: keyword-dense, structured for recruiter search (uses pipe/separator
   format common in recruiter-optimised headlines, e.g. "Title | Skill | Skill | Outcome")
3. ATS_FRIENDLY: uses exact terminology from the job description (if provided) so it
   surfaces in ATS/recruiter keyword searches for that specific role
4. PERSONAL_BRAND: distinctive, conveys personality and unique value proposition —
   avoids generic corporate language, sounds like a real person

Output ONLY this JSON structure:
{{
  "professional": "...",
  "recruiter_friendly": "...",
  "ats_friendly": "...",
  "personal_brand": "..."
}}

RULES:
- Each headline must be ≤220 characters
- Use ONLY skills/experience already present in the candidate profile — never invent credentials
- ats_friendly: if job context is provided, prioritise exact JD terminology; otherwise behave like recruiter_friendly
- Avoid empty buzzwords ("passionate", "results-driven", "synergy") unless paired with concrete specifics
- Output ONLY valid JSON — no markdown, no preamble\
"""
