'use client';

/**
 * SemanticScoreCard
 * Reusable component that displays semantic alignment scores.
 *
 * Variants:
 *   "full"    — entire breakdown with bars, strengths, gaps, recommendation
 *               Used on: resumes/[id]/page.tsx
 *   "compact" — overall score + section bars only
 *               Used on: jd-comparison-view.tsx (builder JD tab)
 *   "badge"   — single number + colour-coded label
 *               Used on: dashboard tailored resume cards
 */

import { useState } from 'react';
import { TrendingUp, ChevronDown, ChevronRight, AlertCircle } from 'lucide-react';
import type { SemanticMatchResult, SectionScore } from './resume_previewer_context';

// ── Colour helpers ─────────────────────────────────────────────────────────

function scoreColour(score: number) {
  if (score >= 70) return 'text-emerald-600';
  if (score >= 45) return 'text-amber-600';
  return 'text-red-500';
}

function barColour(score: number) {
  if (score >= 70) return 'bg-emerald-500';
  if (score >= 45) return 'bg-amber-400';
  return 'bg-red-400';
}

function scoreLabel(score: number) {
  if (score >= 80) return 'Strong Alignment';
  if (score >= 65) return 'Good Alignment';
  if (score >= 50) return 'Moderate Alignment';
  if (score >= 35) return 'Partial Alignment';
  return 'Low Alignment';
}

// ── Section bar (shared across variants) ──────────────────────────────────

function SectionBar({ s }: { s: SectionScore }) {
  const LABEL: Record<string, string> = {
    experience: 'Experience',
    skills: 'Skills',
    projects: 'Projects',
    summary: 'Summary',
    education: 'Education',
  };
  return (
    <div className="flex items-center gap-2">
      <span className="font-mono text-xs w-20 capitalize text-ink-soft shrink-0 leading-none">
        {LABEL[s.section] ?? s.section}
      </span>
      <div className="flex-1 h-1.5 bg-gray-100 border border-gray-300">
        <div
          className={`h-full transition-all ${barColour(s.score)}`}
          style={{ width: `${Math.max(Math.min(s.score, 100), 0)}%` }}
        />
      </div>
      <span className={`font-mono text-xs font-bold w-8 text-right shrink-0 ${scoreColour(s.score)}`}>
        {s.score.toFixed(0)}
      </span>
    </div>
  );
}

// ── Badge variant ─────────────────────────────────────────────────────────

interface BadgeProps {
  score: number;
  className?: string;
}

export function SemanticScoreBadge({ score, className = '' }: BadgeProps) {
  return (
    <div className={`flex items-center gap-1.5 ${className}`}>
      <TrendingUp className={`w-3 h-3 ${scoreColour(score)}`} />
      <span className={`font-mono text-xs font-bold ${scoreColour(score)}`}>
        {score.toFixed(0)}
        <span className="font-normal text-ink-soft">/100</span>
      </span>
      <span className="font-mono text-xs text-ink-soft hidden sm:inline">
        · {scoreLabel(score)}
      </span>
    </div>
  );
}

// ── Compact variant ───────────────────────────────────────────────────────

interface CompactProps {
  match: SemanticMatchResult;
  className?: string;
}

export function SemanticScoreCompact({ match, className = '' }: CompactProps) {
  return (
    <div className={`space-y-3 ${className}`}>
      {/* Overall */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-primary" />
          <span className="font-mono text-xs font-bold uppercase tracking-wider">
            Semantic Alignment
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className={`font-mono text-xl font-bold ${scoreColour(match.overall_score)}`}>
            {match.overall_score.toFixed(0)}
            <span className="text-xs font-normal text-ink-soft">/100</span>
          </span>
          <span className="font-mono text-xs text-ink-soft hidden md:inline">
            {scoreLabel(match.overall_score)}
          </span>
        </div>
      </div>

      {/* Section bars */}
      {match.section_scores.length > 0 && (
        <div className="space-y-1.5">
          {match.section_scores.map((s) => (
            <SectionBar key={s.section} s={s} />
          ))}
        </div>
      )}

      {/* One-liner fit summary */}
      {match.fit_summary && (
        <p className="font-mono text-xs text-ink-soft leading-relaxed border-t border-paper-tint pt-2">
          {match.fit_summary}
        </p>
      )}
    </div>
  );
}

// ── Full variant ──────────────────────────────────────────────────────────

interface FullProps {
  match: SemanticMatchResult;
  /** Start expanded (default: true) */
  defaultExpanded?: boolean;
  className?: string;
}

export function SemanticScoreFull({
  match,
  defaultExpanded = true,
  className = '',
}: FullProps) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <div className={`border-2 border-black bg-white ${className}`}>
      {/* Header / toggle */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between p-4 hover:bg-paper-tint transition-colors"
      >
        <div className="flex items-center gap-3">
          <TrendingUp className="w-4 h-4 text-primary" />
          <span className="font-mono text-sm font-bold uppercase tracking-wider">
            Semantic Alignment Analysis
          </span>
          <span className="font-mono text-xs text-ink-soft hidden md:inline">
            // embedding · cosine similarity
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className={`font-mono text-2xl font-bold ${scoreColour(match.overall_score)}`}>
            {match.overall_score.toFixed(0)}
            <span className="text-sm font-normal text-ink-soft">/100</span>
          </span>
          <span className="font-mono text-xs text-ink-soft uppercase hidden sm:inline">
            {scoreLabel(match.overall_score)}
          </span>
          {expanded ? (
            <ChevronDown className="w-4 h-4 text-ink-soft" />
          ) : (
            <ChevronRight className="w-4 h-4 text-ink-soft" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="border-t-2 border-black p-4 space-y-5">
          {/* Section bars */}
          {match.section_scores.length > 0 && (
            <div>
              <p className="font-mono text-xs font-bold uppercase tracking-wider text-ink-soft mb-3">
                Section Scores
              </p>
              <div className="space-y-2.5">
                {match.section_scores.map((s) => (
                  <SectionBar key={s.section} s={s} />
                ))}
              </div>
            </div>
          )}

          {/* Fit summary */}
          {match.fit_summary && (
            <div className="bg-paper-tint border border-paper-tint p-3">
              <p className="font-mono text-xs text-ink-soft leading-relaxed">
                {match.fit_summary}
              </p>
            </div>
          )}

          {/* Strengths */}
          {match.strengths.length > 0 && (
            <div>
              <p className="font-mono text-xs font-bold uppercase tracking-wider text-emerald-600 mb-2">
                ✓ Strengths
              </p>
              <ul className="space-y-1">
                {match.strengths.map((s, i) => (
                  <li key={i} className="font-mono text-xs text-ink-soft flex gap-2">
                    <span className="text-emerald-500 shrink-0">+</span>
                    {s}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Gaps */}
          {match.gaps.length > 0 && (
            <div>
              <p className="font-mono text-xs font-bold uppercase tracking-wider text-amber-600 mb-2">
                △ Areas to Strengthen
              </p>
              <ul className="space-y-1">
                {match.gaps.map((g, i) => (
                  <li key={i} className="font-mono text-xs text-ink-soft flex gap-2 items-start">
                    <AlertCircle className="w-3 h-3 text-amber-500 shrink-0 mt-0.5" />
                    {g}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Recommendation */}
          {match.recommendation && (
            <div className="border-t border-paper-tint pt-3">
              <p className="font-mono text-xs font-bold uppercase tracking-wider text-ink-soft mb-1">
                Recommendation
              </p>
              <p className="font-mono text-xs text-ink-soft italic leading-relaxed">
                {match.recommendation}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Default export: pick variant via prop ─────────────────────────────────

interface SemanticScoreCardProps {
  match: SemanticMatchResult;
  variant?: 'full' | 'compact' | 'badge';
  defaultExpanded?: boolean;
  className?: string;
}

export function SemanticScoreCard({
  match,
  variant = 'full',
  defaultExpanded = true,
  className,
}: SemanticScoreCardProps) {
  if (variant === 'badge') {
    return <SemanticScoreBadge score={match.overall_score} className={className} />;
  }
  if (variant === 'compact') {
    return <SemanticScoreCompact match={match} className={className} />;
  }
  return (
    <SemanticScoreFull match={match} defaultExpanded={defaultExpanded} className={className} />
  );
}
