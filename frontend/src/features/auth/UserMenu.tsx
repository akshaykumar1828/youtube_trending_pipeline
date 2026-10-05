import * as Popover from '@radix-ui/react-popover';
import { ChevronDown, LogOut } from 'lucide-react';
import { useNavigate } from 'react-router';

import { Badge } from '../../components/ui/Badge';
import { Button } from '../../components/ui/Button';
import { ROLE_LABELS } from './permissions';
import { useCurrentUser, useLogout } from './queries';

/** Signed-in identity (name, role, workspace) and sign-out. */
export function UserMenu() {
  const currentUser = useCurrentUser();
  const logout = useLogout();
  const navigate = useNavigate();
  const me = currentUser.data;
  if (!me) return null;

  const signOut = () =>
    logout.mutate(undefined, { onSettled: () => void navigate('/login', { replace: true }) });

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <Button variant="ghost" size="sm" aria-label={`Account: ${me.user.display_name}`}>
          <span
            aria-hidden="true"
            className="grid size-6 place-items-center rounded-full bg-accent-50 text-[11px] font-semibold text-accent-700"
          >
            {me.user.display_name.trim().charAt(0).toUpperCase() || '?'}
          </span>
          <span className="hidden max-w-36 truncate text-xs font-medium text-slate-700 md:inline">
            {me.user.display_name}
          </span>
          <ChevronDown aria-hidden="true" className="size-3.5" />
        </Button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          sideOffset={6}
          className="z-50 w-64 rounded-lg border border-slate-200 bg-white p-3 shadow-lg"
        >
          <p className="truncate text-sm font-semibold text-slate-900">{me.user.display_name}</p>
          <p className="truncate text-xs text-slate-500">{me.user.email}</p>
          <dl className="mt-3 space-y-1.5 text-xs">
            <div className="flex items-center justify-between gap-2">
              <dt className="text-slate-500">Workspace</dt>
              <dd className="truncate font-medium text-slate-800">{me.tenant.name}</dd>
            </div>
            <div className="flex items-center justify-between gap-2">
              <dt className="text-slate-500">Role</dt>
              <dd>
                <Badge tone="accent">{ROLE_LABELS[me.user.role]}</Badge>
              </dd>
            </div>
          </dl>
          <Button
            variant="secondary"
            size="sm"
            className="mt-3 w-full"
            onClick={signOut}
            disabled={logout.isPending}
          >
            <LogOut aria-hidden="true" className="size-3.5" />
            {logout.isPending ? 'Signing out…' : 'Sign out'}
          </Button>
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
