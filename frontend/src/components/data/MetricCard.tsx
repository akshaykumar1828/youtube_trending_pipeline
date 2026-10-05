import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react';

import { cn } from '../../lib/cn';
import { Skeleton } from '../ui/Skeleton';

interface MetricCardProps {
  label: string;
  value: string;
  /** Formatted change from the API (e.g. "+5.3%" or "+0.16 pp"); null when unavailable. */
  change: string | null;
  /** Raw change used only to pick the direction icon/colour. */
  changeValue: number | null | undefined;
  comparisonLabel: string;
  noComparisonText?: string;
  /** Metric definition, shown as a description for assistive tech and as a tooltip. */
  definition: string;
}

export function MetricCard({
  label,
  value,
  change,
  changeValue,
  comparisonLabel,
  noComparisonText = 'No comparison available',
  definition,
}: MetricCardProps) {
  const direction =
    changeValue == null || changeValue === 0 ? 'flat' : changeValue > 0 ? 'up' : 'down';
  const Icon = direction === 'up' ? ArrowUpRight : direction === 'down' ? ArrowDownRight : Minus;
  return (
    <article
      className="min-w-0 rounded-lg border border-slate-200 bg-white px-4 py-3.5"
      title={definition}
    >
      <h3 className="truncate text-xs font-medium text-slate-500">{label}</h3>
      <p className="mt-1.5 text-2xl font-semibold tracking-tight text-slate-900 tabular-nums">
        {value}
      </p>
      <p className="mt-1.5 flex items-center gap-1 text-xs text-slate-500">
        {change ? (
          <>
            <span
              className={cn(
                'inline-flex items-center gap-0.5 font-medium tabular-nums',
                direction === 'up' && 'text-emerald-700',
                direction === 'down' && 'text-rose-700',
                direction === 'flat' && 'text-slate-600',
              )}
            >
              <Icon aria-hidden="true" className="size-3.5" />
              {change}
            </span>
            <span className="truncate">{comparisonLabel}</span>
          </>
        ) : (
          <span>{noComparisonText}</span>
        )}
      </p>
      <p className="sr-only">{definition}</p>
    </article>
  );
}

export function MetricCardSkeleton() {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3.5" aria-hidden="true">
      <Skeleton className="h-3 w-24" />
      <Skeleton className="mt-3 h-7 w-28" />
      <Skeleton className="mt-3 h-3 w-36" />
    </div>
  );
}
