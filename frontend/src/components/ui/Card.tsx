import type { HTMLAttributes, ReactNode } from 'react';

import { cn } from '../../lib/cn';

export function Card({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return (
    <section
      className={cn('min-w-0 rounded-lg border border-slate-200 bg-white', className)}
      {...props}
    />
  );
}

interface CardHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  id?: string;
}

/** Card title row: title, one-line description (often the metric definition) and actions. */
export function CardHeader({ title, description, actions, id }: CardHeaderProps) {
  return (
    <header className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 border-b border-slate-100 px-4 py-3">
      <div className="min-w-0">
        <h2 id={id} className="text-sm font-semibold text-slate-900">
          {title}
        </h2>
        {description && <p className="mt-0.5 text-xs text-slate-500">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
