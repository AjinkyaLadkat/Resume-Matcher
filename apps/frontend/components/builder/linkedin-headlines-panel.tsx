'use client';

import { useEffect, useState } from 'react';
import { Check, Copy, Loader2, RotateCcw, Sparkles } from 'lucide-react';
import {
  fetchLinkedInHeadlines,
  type LinkedInHeadlines as LinkedInHeadlinesData,
} from '@/lib/api/analysis';
import { Button } from '@/components/ui/button';

interface LinkedInHeadlinesPanelProps {
  resumeId: string;
}

const VARIANTS: { key: keyof LinkedInHeadlinesData; label: string; description: string }[] = [
  {
    key: 'professional',
    label: 'Professional',
    description: 'Formal, role-focused — emphasises core expertise and seniority',
  },
  {
    key: 'recruiter_friendly',
    label: 'Recruiter-Friendly',
    description: 'Keyword-dense, structured for recruiter search',
  },
  {
    key: 'ats_friendly',
    label: 'ATS-Friendly',
    description: 'Uses exact job description terminology for keyword matching',
  },
  {
    key: 'personal_brand',
    label: 'Personal-Brand',
    description: 'Distinctive — conveys personality and unique value',
  },
];

/**
 * LinkedIn Headline Generator — answers "how should the candidate market
 * themselves?" Renders as a new tab, parallel to Cover Letter and Outreach.
 *
 * Auto-fetches on mount (unlike Skill Gap / Interview Questions, which
 * lazy-load on expand) because this is a dedicated tab the user explicitly
 * navigated to — fetching immediately matches the existing GeneratePrompt
 * pattern used by Cover Letter / Outreach tabs.
 */
export function LinkedInHeadlinesPanel({ resumeId }: LinkedInHeadlinesPanelProps) {
  const [data, setData] = useState<LinkedInHeadlinesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copiedKey, setCopiedKey] = useState<string | null>(null);

  const load = async (force = false) => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetchLinkedInHeadlines(resumeId, force);
      setData(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to generate LinkedIn headlines.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (resumeId) {
      load(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resumeId]);

  const handleCopy = async (key: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedKey(key);
      setTimeout(() => setCopiedKey(null), 2000);
    } catch (e) {
      console.error('Failed to copy:', e);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 text-ink-soft py-16">
        <Loader2 className="w-5 h-5 animate-spin" />
        <span className="font-mono text-sm">Generating LinkedIn headlines...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="p-6">
        <div className="border-2 border-red-600 bg-red-50 p-4 font-mono text-sm text-red-700">
          {error}
        </div>
        <Button variant="outline" size="sm" className="mt-4" onClick={() => load(false)}>
          <RotateCcw className="w-4 h-4" />
          Retry
        </Button>
      </div>
    );
  }

  if (!data) {
    return null;
  }

  const hasAnyContent = VARIANTS.some((v) => data[v.key]?.trim());

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between border-b-2 border-black pb-2">
        <h3 className="font-mono text-sm font-bold uppercase tracking-wider">
          LinkedIn Headline Variants
        </h3>
        <Button variant="outline" size="sm" onClick={() => load(true)} disabled={loading}>
          {loading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Sparkles className="w-4 h-4" />
          )}
          Regenerate
        </Button>
      </div>

      {!hasAnyContent && (
        <p className="font-mono text-xs text-ink-soft text-center py-8">
          No headlines were generated. Try regenerating.
        </p>
      )}

      {VARIANTS.map((variant) => {
        const text = data[variant.key];
        if (!text) return null;
        const isCopied = copiedKey === variant.key;

        return (
          <div key={variant.key} className="border-2 border-black bg-white p-4">
            <div className="flex items-center justify-between mb-2">
              <div>
                <p className="font-mono text-xs font-bold uppercase tracking-wider">
                  {variant.label}
                </p>
                <p className="font-mono text-xs text-ink-soft">{variant.description}</p>
              </div>
              <Button
                variant={isCopied ? 'success' : 'outline'}
                size="sm"
                onClick={() => handleCopy(variant.key, text)}
              >
                {isCopied ? (
                  <>
                    <Check className="w-4 h-4" />
                    Copied
                  </>
                ) : (
                  <>
                    <Copy className="w-4 h-4" />
                    Copy
                  </>
                )}
              </Button>
            </div>
            <p className="font-sans text-sm text-ink-soft leading-relaxed bg-paper-tint border border-paper-tint p-3">
              {text}
            </p>
            <p className="font-mono text-xs text-ink-soft mt-1 text-right">
              {text.length}/220 characters
            </p>
          </div>
        );
      })}
    </div>
  );
}
