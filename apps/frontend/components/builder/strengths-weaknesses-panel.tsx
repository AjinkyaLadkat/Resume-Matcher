'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight, Scale, ThumbsDown, ThumbsUp } from 'lucide-react';
import type { SemanticMatchResult } from '@/components/common/resume_previewer_context';

interface StrengthsWeaknessesPanelProps {
  match: SemanticMatchResult;
}

/**
 * Strengths & Weaknesses panel — answers "what helps or hurts candidacy?"
 *
 * Pure presentation component — reads strengths_detailed / weaknesses_detailed
 * directly from the already-computed SemanticMatchResult. No API call, no
 * loading state, no new LLM invocation: this data was generated during the
 * same scoring pass that produced section_scores and fit_summary.
 *
 * Falls back to the legacy plain-string strengths/gaps arrays for resumes
 * scored before this upgrade, so older persisted results still render.
 */
export function StrengthsWeaknessesPanel({ match }: StrengthsWeaknessesPanelProps) {
  const [expanded, setExpanded] = useState(false);

  const hasDetailed =
    (match.strengths_detailed && match.strengths_detailed.length > 0) ||
    (match.weaknesses_detailed && match.weaknesses_detailed.length > 0);
  const hasLegacy = match.strengths.length > 0 || match.gaps.length > 0;

  if (!hasDetailed && !hasLegacy) {
    return null;
  }

  return (
    <div className="border-2 border-black bg-white">
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between p-4 hover:bg-paper-tint transition-colors"
      >
        <div className="flex items-center gap-3">
          <Scale className="w-4 h-4 text-primary" />
          <span className="font-mono text-sm font-bold uppercase tracking-wider">
            Strengths &amp; Weaknesses
          </span>
          <span className="font-mono text-xs text-ink-soft hidden md:inline">
            [// what helps or hurts candidacy?]
          </span>
        </div>
        {expanded ? (
          <ChevronDown className="w-4 h-4 text-ink-soft" />
        ) : (
          <ChevronRight className="w-4 h-4 text-ink-soft" />
        )}
      </button>

      {expanded && (
        <div className="border-t-2 border-black p-4 grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Strengths column */}
          <div>
            <p className="font-mono text-xs font-bold uppercase tracking-wider text-emerald-600 mb-2 flex items-center gap-1.5">
              <ThumbsUp className="w-3.5 h-3.5" />
              Strengths
            </p>
            <div className="space-y-2">
              {match.strengths_detailed && match.strengths_detailed.length > 0
                ? match.strengths_detailed.map((s, i) => (
                    <div key={i} className="border border-emerald-200 bg-emerald-50 p-3">
                      <p className="font-mono text-xs font-bold text-ink-soft">{s.strength}</p>
                      <p className="font-mono text-xs text-ink-soft mt-1 italic">
                        Evidence: {s.evidence}
                      </p>
                      {s.relevance && (
                        <p className="font-mono text-xs text-ink-soft mt-1">{s.relevance}</p>
                      )}
                    </div>
                  ))
                : match.strengths.map((s, i) => (
                    <div key={i} className="border border-emerald-200 bg-emerald-50 p-3">
                      <p className="font-mono text-xs text-ink-soft">{s}</p>
                    </div>
                  ))}
            </div>
          </div>

          {/* Weaknesses column */}
          <div>
            <p className="font-mono text-xs font-bold uppercase tracking-wider text-amber-600 mb-2 flex items-center gap-1.5">
              <ThumbsDown className="w-3.5 h-3.5" />
              Weaknesses
            </p>
            <div className="space-y-2">
              {match.weaknesses_detailed && match.weaknesses_detailed.length > 0
                ? match.weaknesses_detailed.map((w, i) => (
                    <div key={i} className="border border-amber-200 bg-amber-50 p-3">
                      <p className="font-mono text-xs font-bold text-ink-soft">{w.weakness}</p>
                      <p className="font-mono text-xs text-ink-soft mt-1 italic">
                        Relates to: {w.jd_requirement}
                      </p>
                      <span className="font-mono text-xs text-ink-soft mt-1 inline-block uppercase tracking-wide opacity-70">
                        {w.weakness_type.replace(/_/g, ' ')}
                      </span>
                    </div>
                  ))
                : match.gaps.map((g, i) => (
                    <div key={i} className="border border-amber-200 bg-amber-50 p-3">
                      <p className="font-mono text-xs text-ink-soft">{g}</p>
                    </div>
                  ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
