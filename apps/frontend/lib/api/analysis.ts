/**
 * API functions for the four semantic-analysis features:
 *   1. Skill Gap Analysis
 *   2. Strengths & Weaknesses (bundled inside SemanticMatchResult — see
 *      resume_previewer_context.tsx, no separate fetch function needed)
 *   3. AI Interview Questions
 *   4. LinkedIn Headline Generator
 *
 * Kept in a separate file from resume.ts / enrichment.ts so this feature
 * set never touches those existing, working files.
 */

import { apiPost } from './client';

// ── 1. Skill Gap Analysis ──────────────────────────────────────────────────

export interface SkillGapItem {
  skill: string;
  why_it_matters: string;
  estimated_score_impact: string;
  suggested_placement: string;
}

export interface RelatedSkillItem {
  jd_skill: string;
  resume_evidence: string;
  explanation: string;
}

export interface SkillGapResult {
  critical_missing: SkillGapItem[];
  nice_to_have_missing: SkillGapItem[];
  related_skills_demonstrated: RelatedSkillItem[];
  summary: string;
}

export async function fetchSkillGapAnalysis(
  resumeId: string,
  forceRegenerate = false
): Promise<SkillGapResult> {
  const res = await apiPost(`/analysis/${encodeURIComponent(resumeId)}/skill-gap`, {
    force_regenerate: forceRegenerate,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Failed to fetch skill gap analysis (status ${res.status}): ${text}`);
  }
  return res.json();
}

// ── 3. AI Interview Questions ──────────────────────────────────────────────

export interface InterviewQuestion {
  question: string;
  category: 'technical' | 'project' | 'behavioral' | 'resume_specific' | 'jd_specific';
  difficulty: 'easy' | 'medium' | 'hard';
  rationale: string;
}

export interface InterviewQuestionsResult {
  technical: InterviewQuestion[];
  project: InterviewQuestion[];
  behavioral: InterviewQuestion[];
  resume_specific: InterviewQuestion[];
  jd_specific: InterviewQuestion[];
}

export async function fetchInterviewQuestions(
  resumeId: string,
  forceRegenerate = false
): Promise<InterviewQuestionsResult> {
  const res = await apiPost(`/analysis/${encodeURIComponent(resumeId)}/interview-questions`, {
    force_regenerate: forceRegenerate,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Failed to fetch interview questions (status ${res.status}): ${text}`);
  }
  return res.json();
}

// ── 4. LinkedIn Headline Generator ─────────────────────────────────────────

export interface LinkedInHeadlines {
  professional: string;
  recruiter_friendly: string;
  ats_friendly: string;
  personal_brand: string;
}

export async function fetchLinkedInHeadlines(
  resumeId: string,
  forceRegenerate = false
): Promise<LinkedInHeadlines> {
  const res = await apiPost(`/analysis/${encodeURIComponent(resumeId)}/linkedin-headlines`, {
    force_regenerate: forceRegenerate,
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`Failed to fetch LinkedIn headlines (status ${res.status}): ${text}`);
  }
  return res.json();
}
