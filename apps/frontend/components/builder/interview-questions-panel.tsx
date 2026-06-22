'use client';

import { useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  HelpCircle,
  Loader2,
  MessageCircleQuestion,
} from 'lucide-react';
import {
  fetchInterviewQuestions,
  type InterviewQuestion,
  type InterviewQuestionsResult,
} from '@/lib/api/analysis';

interface InterviewQuestionsPanelProps {
  resumeId: string;
  initialResult?: InterviewQuestionsResult | null;
}

const CATEGORY_LABELS: Record<string, string> = {
  technical: 'Technical',
  project: 'Project',
  behavioral: 'Behavioral',
  resume_specific: 'Resume-Specific',
  jd_specific: 'JD-Specific',
};

const CATEGORY_ORDER = ['technical', 'project', 'behavioral', 'resume_specific', 'jd_specific'];

function difficultyColor(d: string) {
  if (d === 'hard') return 'text-red-600 bg-red-50 border-red-200';
  if (d === 'medium') return 'text-amber-600 bg-amber-50 border-amber-200';
  return 'text-emerald-600 bg-emerald-50 border-emerald-200';
}

/**
 * AI Interview Questions panel — answers "what will likely be asked?"
 *
 * Lazy-loads on first expand. Backend targets the candidate's weakest
 * semantic section automatically (reusing section_scores), so this never
 * re-runs embedding or keyword extraction — only the question-generation
 * LLM call is new.
 */
export function InterviewQuestionsPanel({
  resumeId,
  initialResult = null,
}: InterviewQuestionsPanelProps) {
  const [expanded, setExpanded] = useState(false);
  const [result, setResult] = useState<InterviewQuestionsResult | null>(initialResult);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = async (force = false) => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchInterviewQuestions(resumeId, force);
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load interview questions.');
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

  const totalQuestions = result
    ? CATEGORY_ORDER.reduce(
        (sum, cat) => sum + (result[cat as keyof InterviewQuestionsResult]?.length ?? 0),
        0
      )
    : 0;

  return (
    <div className="border-2 border-black bg-white">
      <button
        onClick={handleToggle}
        className="w-full flex items-center justify-between p-4 hover:bg-paper-tint transition-colors"
      >
        <div className="flex items-center gap-3">
          <MessageCircleQuestion className="w-4 h-4 text-primary" />
          <span className="font-mono text-sm font-bold uppercase tracking-wider">
            AI Interview Questions
          </span>
          <span className="font-mono text-xs text-ink-soft hidden md:inline">
            [// what will likely be asked?]
          </span>
        </div>
        <div className="flex items-center gap-3">
          {result && (
            <span className="font-mono text-xs text-ink-soft">{totalQuestions} questions</span>
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
              <span className="font-mono text-xs">Generating interview questions...</span>
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
              {CATEGORY_ORDER.map((cat) => {
                const questions = result[cat as keyof InterviewQuestionsResult] as
                  | InterviewQuestion[]
                  | undefined;
                if (!questions || questions.length === 0) return null;
                return (
                  <div key={cat}>
                    <p className="font-mono text-xs font-bold uppercase tracking-wider text-ink-soft mb-2">
                      {CATEGORY_LABELS[cat] ?? cat}
                    </p>
                    <div className="space-y-2">
                      {questions.map((q, i) => (
                        <div key={i} className="border border-paper-tint bg-paper-tint/40 p-3">
                          <div className="flex items-start justify-between gap-2">
                            <p className="font-mono text-xs font-bold text-ink-soft flex-1">
                              {q.question}
                            </p>
                            <span
                              className={`font-mono text-xs px-2 py-0.5 border shrink-0 uppercase ${difficultyColor(
                                q.difficulty
                              )}`}
                            >
                              {q.difficulty}
                            </span>
                          </div>
                          <div className="flex items-start gap-1.5 mt-2">
                            <HelpCircle className="w-3 h-3 text-ink-soft shrink-0 mt-0.5" />
                            <p className="font-mono text-xs text-ink-soft italic">{q.rationale}</p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}

              {totalQuestions === 0 && (
                <p className="font-mono text-xs text-ink-soft text-center py-4">
                  No questions generated.
                </p>
              )}

              <div className="border-t border-paper-tint pt-3 flex justify-end">
                <button
                  onClick={() => load(true)}
                  disabled={loading}
                  className="font-mono text-xs text-ink-soft hover:text-primary underline disabled:opacity-50"
                >
                  Regenerate questions
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
