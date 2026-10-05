import type { CurrentUser, Permission, Role } from '../../api/types';

/**
 * Role-aware UI helpers. These only decide what to SHOW: the backend enforces every permission
 * and role rule itself, and its answer (403) always wins.
 */
export function hasPermission(user: CurrentUser | null | undefined, permission: Permission) {
  return Boolean(user?.user.permissions.includes(permission));
}

export const ROLE_LABELS: Record<Role, string> = {
  OWNER: 'Owner',
  ADMIN: 'Admin',
  MEMBER: 'Member',
};

export const ROLES: readonly Role[] = ['OWNER', 'ADMIN', 'MEMBER'];

/** Roles `actor` may grant (mirrors the server rule: only owners grant OWNER). */
export function assignableRoles(actor: Role): Role[] {
  if (actor === 'OWNER') return [...ROLES];
  if (actor === 'ADMIN') return ['ADMIN', 'MEMBER'];
  return [];
}

/** Whether `actor` may change a member whose role is `target` (not themselves; checked separately). */
export function canManageMember(actor: Role, target: Role) {
  return actor === 'OWNER' || (actor === 'ADMIN' && target !== 'OWNER');
}

/**
 * Where to go after signing in. Only same-app absolute paths are accepted, so a crafted
 * ?next= link cannot send the user to another site (open redirect).
 */
export function safeNextPath(next: string | null | undefined): string {
  if (!next || !next.startsWith('/') || next.startsWith('//') || next.startsWith('/\\')) return '/';
  if (/^\/(login|register)(\/|\?|$)/.test(next)) return '/';
  return next;
}

export function loginPathFor(location: { pathname: string; search: string }) {
  const next = `${location.pathname}${location.search}`;
  return next === '/' ? '/login' : `/login?next=${encodeURIComponent(next)}`;
}
