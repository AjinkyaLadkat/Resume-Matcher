'use client';

import { useState } from 'react';
import { AlertCircle, ChevronDown, ChevronRight, Layers, Link2, Loader2 } from 'lucide-react';
import { fetchSkillGapAnalysis, type SkillGapResult } from '@/lib/api/analysis';

interface SkillGapPanelProps {
  resumeId: string;
  /** Pre-fetched result, if the parent already has one cached. */
  initialResult?: SkillGapResult | null;
}

/**
 * Skill Gap Analysis panel — answers "what is missing?"
 *
 * Lazy-loads on first expand (does not fetch on mount) to avoid an
 * unnecessary LLM call when the user never opens this section.
 * Backend caches the result on the resume record, so repeat expands
 * within the same session or across reloads are free until the user
 * explicitly clicks Regenerate.
 */
export function SkillGapPanel({ resumeId, initialResult = null }: SkillGapPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const [result, setResult] = useState<SkillGapResult | null>(initialResult);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async (force = false) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchSkillGapAnalysis(resumeId, force);
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load skill gap analysis.');
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = () => {
    const next = !expanded;
    setExpanded(next);
    if (next && !result && !loading) {
      load(false);
    }
  };

  return (
    <div className="border-2 border-black bg-white">
      <button
        onClick={handleToggle}
        className="w-full flex items-center justify-between p-4 hover:bg-paper-tint transition-colors"
      >
        <div className="flex items-center gap-3">
          <Layers className="w-4 h-4 text-primary" />
          <span className="font-mono text-sm font-bold uppercase tracking-wider">
            Skill Gap Analysis
          </span>
          <span className="font-mono text-xs text-ink-soft hidden md:inline">
            [// what is missing?]
          </span>
        </div>
        <div className="flex items-center gap-3">
          {result && (
            <span className="font-mono text-xs text-ink-soft">
              {result.critical_missing.length} critical
            </span>
          )}
          {expanded ? (
            <ChevronDown className="w-4 h-4 text-ink-soft" />
          ) : (
            <ChevronRight className="w-4 h-4 text-ink-soft" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="border-t-2 border-black p-4 space-y-5">
          {loading && (
            <div className="flex items-center gap-2 text-ink-soft py-4 justify-center">
              <Loader2 className="w-4 h-4 animate-spin" />
              <span className="font-mono text-xs">Analyzing skill gaps...</span>
            </div>
          )}

          {error && (
            <div className="border border-red-600 bg-red-50 p-3 font-mono text-xs text-red-700">
              {error}
              <button onClick={() => load(false)} className="ml-2 underline hover:no-underline">
                Retry
              </button>
            </div>
          )}

          {result && !loading && (
            <>
              {result.summary && (
                <p className="font-mono text-xs text-ink-soft leading-relaxed bg-paper-tint border border-paper-tint p-3">
                  {result.summary}
                </p>
              )}

              {result.critical_missing.length > 0 && (
                <div>
                  <p className="font-mono text-xs font-bold uppercase tracking-wider text-red-600 mb-2">
                    Critical Missing Skills
                  </p>
                  <div className="space-y-2">
                    {result.critical_missing.map((item, i) => (
                      <SkillGapCard key={i} item={item} severity="critical" />
                    ))}
                  </div>
                </div>
              )}

              {result.nice_to_have_missing.length > 0 && (
                <div>
                  <p className="font-mono text-xs font-bold uppercase tracking-wider text-amber-600 mb-2">
                    Nice-to-Have Missing Skills
                  </p>
                  <div className="space-y-2">
                    {result.nice_to_have_missing.map((item, i) => (
                      <SkillGapCard key={i} item={item} severity="nice-to-have" />
                    ))}
                  </div>
                </div>
              )}

              {result.related_skills_demonstrated.length > 0 && (
                <div>
                  <p className="font-mono text-xs font-bold uppercase tracking-wider text-emerald-600 mb-2">
                    Related Skills Already Demonstrated
                  </p>
                  <div className="space-y-2">
                    {result.related_skills_demonstrated.map((item, i) => (
                      <div
                        key={i}
                        className="border border-emerald-200 bg-emerald-50 p-3 flex gap-2"
                      >
                        <Link2 className="w-3.5 h-3.5 text-emerald-600 shrink-0 mt-0.5" />
                        <div className="font-mono text-xs text-ink-soft">
                          <span className="font-bold">{item.jd_skill}</span>
                          {' → '}
                          <span>{item.resume_evidence}</span>
                          <p className="text-ink-soft mt-1 italic">{item.explanation}</p>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {result.critical_missing.length === 0 &&
                result.nice_to_have_missing.length === 0 &&
                result.related_skills_demonstrated.length === 0 && (
                  <p className="font-mono text-xs text-ink-soft text-center py-4">
                    No significant skill gaps identified.
                  </p>
                )}

              <div className="border-t border-paper-tint pt-3 flex justify-end">
                <button
                  onClick={() => load(true)}
                  disabled={loading}
                  className="font-mono text-xs text-ink-soft hover:text-primary underline disabled:opacity-50"
                >
                  Regenerate analysis
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

function SkillGapCard({
  item,
  severity,
}: {
  item: {
    skill: string;
    why_it_matters: string;
    estimated_score_impact: string;
    suggested_placement: string;
  };
  severity: 'critical' | 'nice-to-have';
}) {
  const borderColor = severity === 'critical' ? 'border-red-200' : 'border-amber-200';
  const bgColor = severity === 'critical' ? 'bg-red-50' : 'bg-amber-50';
  const iconColor = severity === 'critical' ? 'text-red-500' : 'text-amber-500';

  return (
    <div className={`border ${borderColor} ${bgColor} p-3`}>
      <div className="flex items-start gap-2">
        <AlertCircle className={`w-3.5 h-3.5 ${iconColor} shrink-0 mt-0.5`} />
        <div className="flex-1">
          <p className="font-mono text-xs font-bold text-ink-soft">{item.skill}</p>
          <p className="font-mono text-xs text-ink-soft mt-1">{item.why_it_matters}</p>
          <div className="flex flex-wrap gap-3 mt-2">
            {item.estimated_score_impact && (
              <span className="font-mono text-xs text-ink-soft">
                <span className="font-bold">Impact:</span> {item.estimated_score_impact}
              </span>
            )}
            {item.suggested_placement && (
              <span className="font-mono text-xs text-ink-soft">
                <span className="font-bold">Add to:</span> {item.suggested_placement}
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
