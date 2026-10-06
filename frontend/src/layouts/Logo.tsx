import { Play, TrendingUp } from 'lucide-react';

import { cn } from '../lib/cn';

/** App logo in YouTube red: trending arrow with a play badge (our own mark, not YouTube's). */
export function Logo({ size = 'sm' }: { size?: 'sm' | 'lg' }) {
  const large = size === 'lg';
  return (
    <span
      aria-hidden="true"
      className={cn(
        'relative grid shrink-0 place-items-center bg-gradient-to-br from-red-500 to-red-700',
        large ? 'size-16 rounded-2xl shadow-lg shadow-red-600/30' : 'size-8 rounded-lg',
      )}
    >
      <TrendingUp className={cn('text-white', large ? 'size-8' : 'size-4')} strokeWidth={2.5} />
      <span
        className={cn(
          'absolute grid place-items-center rounded-full bg-white shadow',
          large ? '-right-2 -bottom-2 size-7 ring-2 ring-red-50' : '-right-1 -bottom-1 size-3.5',
        )}
      >
        <Play
          className={cn('translate-x-px fill-red-600 text-red-600', large ? 'size-3.5' : 'size-2')}
        />
      </span>
    </span>
  );
}
