import { Database } from 'lucide-react';
import type { ReactNode } from 'react';

import { UserMenu } from '../features/auth/UserMenu';
import { useFilterOptions } from '../features/filters/useFilterOptions';
import { formatDate } from '../lib/format';
import { Brand } from './Sidebar';

/** Top bar: mobile menu button + brand (small screens), data coverage, and the account menu. */
export function Header({ menuButton }: { menuButton: ReactNode }) {
  const options = useFilterOptions();
  const range = options.data?.date_range;
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-slate-200 bg-white px-4 sm:px-6">
      {menuButton}
      <div className="lg:hidden">
        <Brand />
      </div>
      <p className="ml-auto hidden items-center gap-1.5 text-xs text-slate-500 sm:flex">
        <Database aria-hidden="true" className="size-3.5" />
        {range ? (
          <span>
            Data coverage: {formatDate(range.min_date)} – {formatDate(range.max_date)}
          </span>
        ) : (
          <span>Data coverage loading…</span>
        )}
      </p>
      <div className="ml-auto sm:ml-0">
        <UserMenu />
      </div>
    </header>
  );
}
