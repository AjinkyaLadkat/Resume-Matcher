# Expected Behaviour

The purpose of this test case is to verify that the skill overlap gate recognizes
semantic evidence of required skills without relying on embeddings or LLMs.

The implementation must remain deterministic.

---

## Examples that SHOULD match

| JD Skill | Resume Evidence | Expected |
|----------|-----------------|----------|
| SQL | Optimized SQL queries | ✅ |
| SQL | MySQL | ✅ |
| Power BI | Developed Power BI dashboards | ✅ |
| Python | Python (Pandas, NumPy, Matplotlib) | ✅ |
| KPI Reporting | KPI analysis | ✅ |
| Data Cleaning | Data transformation | ✅ |
| Business Intelligence | Business intelligence dashboards | ✅ |
| Data Visualization | Interactive dashboards | ✅ |

---

## Examples that SHOULD NOT match

| JD Skill | Resume Evidence | Expected |
|----------|-----------------|----------|
| SQL | Excel | ❌ |
| Python | Java | ❌ |
| Power BI | Tableau | ❌ |
| Machine Learning | Microsoft Office | ❌ |
| Kubernetes | Docker | ❌ |
| React | Angular | ❌ |

---

## Success Criteria

The implementation should:

- Improve skill overlap accuracy.
- Reduce false negatives caused by literal string matching.
- Preserve deterministic behaviour.
- Preserve existing API.
- Preserve scorer.py.
- Avoid embeddings.
- Avoid LLM calls.
- Avoid redesigning compute_skill_overlap().
- Keep unrelated resumes scoring low.

---

## Current Problem

Current implementation primarily relies on normalized substring matching.

This causes legitimate evidence to be missed.

Example:

JD Skill:
Power BI

Resume:
Developed interactive Power BI dashboards.

Expected:
MATCH

Current:
Sometimes missed depending on wording.

Another example:

JD Skill:
Data Cleaning

Resume:
Performed data transformation.

Expected:
MATCH

Current:
MISS

---

The goal is to improve evidence matching while preserving the philosophy of the current overlap gate.