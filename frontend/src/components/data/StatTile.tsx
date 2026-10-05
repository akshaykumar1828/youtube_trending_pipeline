import type { ReactNode } from 'react';

/** A labelled value without a period comparison. */
export function StatTile({
  label,
  value,
  hint,
}: {
  label: string;
  value: ReactNode;
  hint?: string;
}) {
  return (
    <div className="min-w-0 rounded-md border border-slate-200 bg-white px-3 py-2.5" title={hint}>
      <dt className="truncate text-xs text-slate-500">{label}</dt>
      <dd className="mt-1 text-lg font-semibold text-slate-900 tabular-nums">{value}</dd>
    </div>
  );
}
