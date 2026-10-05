import { BarChart3, Flame, Gauge, LayoutDashboard, Users, type LucideIcon } from 'lucide-react';
import { NavLink } from 'react-router';

import type { Permission } from '../api/types';
import { hasPermission } from '../features/auth/permissions';
import { useCurrentUser } from '../features/auth/queries';
import { useGlobalFilters } from '../features/filters/useGlobalFilters';
import { cn } from '../lib/cn';

/** Items are shown only with their permission (UX only: the API enforces the same rules). */
const NAV_ITEMS: {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
  permission: Permission;
}[] = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, end: true, permission: 'VIEW_ANALYTICS' },
  { to: '/trending', label: 'Trending', icon: Flame, permission: 'VIEW_ANALYTICS' },
  { to: '/analytics', label: 'Analytics', icon: BarChart3, permission: 'VIEW_ANALYTICS' },
  { to: '/predictions', label: 'Predictions', icon: Gauge, permission: 'MAKE_PREDICTION' },
  { to: '/team', label: 'Team', icon: Users, permission: 'MANAGE_USERS' },
];

export function Brand() {
  return (
    <div className="flex items-center gap-2.5">
      <span aria-hidden="true" className="grid size-7 place-items-center rounded-md bg-accent-600">
        <BarChart3 className="size-4 text-white" />
      </span>
      <span className="text-sm leading-tight font-semibold text-slate-900">
        Trending
        <span className="block text-xs font-normal text-slate-500">Intelligence</span>
      </span>
    </div>
  );
}

/** Primary navigation. Links carry the current global filters to the next page. */
export function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const { search } = useGlobalFilters();
  const currentUser = useCurrentUser();
  const items = NAV_ITEMS.filter((item) => hasPermission(currentUser.data, item.permission));
  return (
    <div className="flex h-full flex-col">
      <div className="flex h-14 items-center border-b border-slate-200 px-4">
        <Brand />
      </div>
      <nav aria-label="Main" className="flex-1 space-y-0.5 p-3">
        {items.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={{ pathname: to, search }}
            end={end}
            onClick={onNavigate}
            className={({ isActive }) =>
              cn(
                'flex h-9 items-center gap-2.5 rounded-md border-l-2 px-2.5 text-sm font-medium transition-colors',
                isActive
                  ? 'border-accent-600 bg-accent-50 text-accent-700'
                  : 'border-transparent text-slate-600 hover:bg-slate-100 hover:text-slate-900',
              )
            }
          >
            <Icon aria-hidden="true" className="size-4" />
            {label}
          </NavLink>
        ))}
      </nav>
      <p className="border-t border-slate-200 px-4 py-3 text-[11px] leading-relaxed text-slate-500">
        YouTube trending snapshots across 9 countries, served read-only from PostgreSQL.
      </p>
    </div>
  );
}
