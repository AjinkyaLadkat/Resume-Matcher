## Semantic Matching V3

### New Features

- Hybrid semantic scoring using embedding similarity and deterministic skill overlap.
- Expanded deterministic technical skill taxonomy covering major software and IT domains.
- Evidence-based Strengths & Weaknesses panel with recruiter-style explanations.
- Professional outreach message generation.
- Structured contextual fit analysis.
- Improved semantic score calibration for unrelated resumes.
- Skill synonym normalization to improve resume/JD matching.
- Extensive logging for semantic scoring diagnostics.

### Scoring Pipeline

Overall Score =
Embedding Semantic Similarity +
Deterministic Skill Overlap

The skill-overlap gate reduces false positives caused by generic professional language while preserving semantic understanding of related technologies.
