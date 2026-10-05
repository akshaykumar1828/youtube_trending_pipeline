import { AlertTriangle, Inbox, SearchX } from 'lucide-react';
import type { ReactNode } from 'react';

import { cn } from '../../lib/cn';
import { Button } from '../ui/Button';
import { Skeleton } from '../ui/Skeleton';
import { describeError } from './describeError';

export function LoadingState({
  label = 'Loading',
  className,
  rows = 4,
}: {
  label?: string;
  className?: string;
  rows?: number;
}) {
  return (
    <div role="status" aria-live="polite" className={cn('space-y-2.5 p-4', className)}>
      <span className="sr-only">{label}…</span>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className={cn('h-4', i % 3 === 2 ? 'w-2/3' : 'w-full')} />
      ))}
    </div>
  );
}

interface StateProps {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function EmptyState({ title, description, action, className }: StateProps) {
  return (
    <div
      className={cn('flex flex-col items-center justify-center px-6 py-10 text-center', className)}
    >
      <Inbox aria-hidden="true" className="size-6 text-slate-400" />
      <p className="mt-2 text-sm font-medium text-slate-800">{title}</p>
      {description && <p className="mt-1 max-w-sm text-xs text-slate-500">{description}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function ErrorState({
  error,
  onRetry,
  className,
}: {
  error: unknown;
  onRetry?: () => void;
  className?: string;
}) {
  const { title, message, requestId, canRetry } = describeError(error);
  return (
    <div
      role="alert"
      className={cn('flex flex-col items-center justify-center px-6 py-10 text-center', className)}
    >
      <AlertTriangle aria-hidden="true" className="size-6 text-amber-500" />
      <p className="mt-2 text-sm font-medium text-slate-800">{title}</p>
      <p className="mt-1 max-w-md text-xs text-slate-600">{message}</p>
      {onRetry && canRetry && (
        <Button size="sm" className="mt-3" onClick={onRetry}>
          Retry
        </Button>
      )}
      {requestId && (
        <p className="mt-3 font-mono text-[11px] text-slate-500">Reference: {requestId}</p>
      )}
    </div>
  );
}

export function NoResultsState({ title, description, action }: StateProps) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-10 text-center">
      <SearchX aria-hidden="true" className="size-6 text-slate-400" />
      <p className="mt-2 text-sm font-medium text-slate-800">{title}</p>
      {description && <p className="mt-1 max-w-sm text-xs text-slate-500">{description}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}
