import type { ReactNode } from 'react';

import { cn } from '../../lib/cn';

type Tone = 'neutral' | 'accent' | 'positive' | 'negative';

const tones: Record<Tone, string> = {
  neutral: 'bg-slate-100 text-slate-700',
  accent: 'bg-accent-50 text-accent-700',
  positive: 'bg-emerald-50 text-emerald-700',
  negative: 'bg-rose-50 text-rose-700',
};

export function Badge({
  children,
  tone = 'neutral',
  className,
  title,
}: {
  children: ReactNode;
  tone?: Tone;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={cn(
        'inline-flex items-center rounded px-1.5 py-0.5 text-xs font-medium whitespace-nowrap',
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
