'use client';

import { FileText } from 'lucide-react';
import { useTranslations } from '@/lib/i18n';

interface JDDisplayProps {
  content: string;
}

/**
 * Read-only display of the job description.
 * Shows the original JD text in a scrollable container.
 */
export function JDDisplay({ content }: JDDisplayProps) {
  const { t } = useTranslations();

  return (
    <div className="flex flex-col">
      {/* Header */}
      <div className="flex items-center gap-2 p-4 border-b border-paper-tint bg-paper-tint">
        <FileText className="w-4 h-4 text-ink-soft" />
        <h3 className="font-mono text-sm font-bold uppercase text-ink-soft">
          {t('builder.jdMatch.jobDescriptionTitle')}
        </h3>
      </div>

      {/* Content — capped height with its own scroll on large screens so the
          page doesn't grow unbounded when the JD is very long, but never
          forces scrolling at the page level. */}
      <div className="max-h-[70vh] overflow-y-auto p-4">
        <div className="whitespace-pre-wrap text-sm leading-relaxed text-ink-soft">{content}</div>
      </div>
    </div>
  );
}
