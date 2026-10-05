import { cn } from '../../lib/cn';

export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn('rounded bg-slate-200/70 motion-safe:animate-pulse', className)}
    />
  );
}
