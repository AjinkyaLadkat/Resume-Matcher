/* eslint-disable react/jsx-no-comment-textnodes */
'use client';

import { useMemo } from 'react';
import { type ResumeData } from '@/components/dashboard/resume-component';
import { JDDisplay } from './jd-display';
import { HighlightedResumeView } from './highlighted-resume-view';
import { extractKeywords, calculateMatchStats } from '@/lib/utils/keyword-matcher';
import { SemanticScoreCompact } from '@/components/common/semantic-score-card';
import { TrendingUp, Sparkles, Tag } from 'lucide-react';
import type { SemanticMatchResult } from '@/components/common/resume_previewer_context';

interface JDComparisonViewProps {
  jobDescription: string;
  resumeData: ResumeData;
  semanticMatch?: SemanticMatchResult | null;
}

function getResumeText(resumeData: ResumeData): string {
  const parts: string[] = [];
  if (resumeData.summary) parts.push(resumeData.summary);
  (resumeData.workExperience || []).forEach((e) => {
    if (e.title) parts.push(e.title);
    if (e.company) parts.push(e.company);
    (e.description || []).forEach((d) => parts.push(d));
  });
  (resumeData.personalProjects || []).forEach((p) => {
    if (p.name) parts.push(p.name);
    (p.description || []).forEach((d) => parts.push(d));
  });
  const add = resumeData.additional || {};
  (add.technicalSkills || []).forEach((s) => parts.push(s));
  (add.certificationsTraining || []).forEach((c) => parts.push(c));
  return parts.join(' ');
}

function kwScoreColour(rate: number) {
  if (rate >= 70) return 'text-emerald-600';
  if (rate >= 45) return 'text-amber-600';
  return 'text-red-500';
}
export function JDComparisonView({
  jobDescription,
  resumeData,
  semanticMatch,
}: JDComparisonViewProps) {
  const keywords = useMemo(() => extractKeywords(jobDescription), [jobDescription]);

  const kwStats = useMemo(() => {
    if (!keywords.size) return null;
    const resumeText = getResumeText(resumeData);
    return calculateMatchStats(resumeText, keywords);
  }, [keywords, resumeData]);

  return (
    <div className="space-y-6">
      {/* ── Score header card ──────────────────────────────────────────── */}
      <div className="border-2 border-black bg-white p-4 space-y-3">
        {semanticMatch ? (
          <SemanticScoreCompact match={semanticMatch} />
        ) : (
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <div className="flex items-center gap-2 text-ink-soft">
              <TrendingUp className="w-4 h-4" />
              <span className="font-mono text-xs font-bold uppercase tracking-wider">
                Semantic Alignment
              </span>
            </div>
            <div className="flex items-center gap-2 text-ink-soft">
              <Sparkles className="w-3.5 h-3.5" />
              <span className="font-mono text-xs">
                Tailor this resume to see contextual alignment scores
              </span>
            </div>
          </div>
        )}

        {/* Keyword match — always shown when JD is present */}
        {kwStats && (
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 border-t border-paper-tint pt-3">
            <div className="flex items-center gap-2 text-ink-soft">
              <Tag className="w-3.5 h-3.5" />
              <span className="font-mono text-xs font-bold uppercase tracking-wider">
                Keyword Match
              </span>
              <span className="font-mono text-xs text-ink-soft hidden md:inline">
                // ATS-style surface coverage
              </span>
            </div>
            <div className="flex items-center gap-3">
              <span
                className={`font-mono text-lg font-bold ${kwScoreColour(kwStats.matchPercentage)}`}
              >
                {kwStats.matchPercentage}
                <span className="text-xs font-normal text-ink-soft">%</span>
              </span>
              <span className="font-mono text-xs text-ink-soft">
                {kwStats.matchCount}/{kwStats.totalKeywords} keywords
              </span>
            </div>
          </div>
        )}
      </div>

      {/* ── JD vs Resume comparison ──────────────────────────────────────
          Stacked on mobile/tablet, side-by-side on large screens.
          Each panel sizes to its own content — no forced inner scroll. */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="border-2 border-black bg-white">
          <JDDisplay content={jobDescription} />
        </div>
        <div className="border-2 border-black bg-white">
          <HighlightedResumeView resumeData={resumeData} keywords={keywords} />
        </div>
      </div>
    </div>
  );
}
