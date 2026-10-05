"""Roles, permissions and role-management rules (enforced server-side).

Permissions are deliberately few. OWNER and ADMIN hold the same permissions; they differ in
the role hierarchy: only an OWNER can grant the OWNER role or change an OWNER's membership.
"""

from enum import StrEnum


class Role(StrEnum):
    OWNER = "OWNER"
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"


class Permission(StrEnum):
    VIEW_ANALYTICS = "VIEW_ANALYTICS"
    MAKE_PREDICTION = "MAKE_PREDICTION"
    MANAGE_USERS = "MANAGE_USERS"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: frozenset(Permission),
    Role.ADMIN: frozenset(Permission),
    Role.MEMBER: frozenset({Permission.VIEW_ANALYTICS, Permission.MAKE_PREDICTION}),
}


def permissions_for(role: Role) -> frozenset[Permission]:
    return ROLE_PERMISSIONS[role]


def can_assign_role(actor: Role, role: Role) -> bool:
    """Whether `actor` may give someone `role` (on creation or role change)."""
    if Permission.MANAGE_USERS not in permissions_for(actor):
        return False
    return actor is Role.OWNER or role is not Role.OWNER


def can_manage_member(actor: Role, target: Role) -> bool:
    """Whether `actor` may change a member that currently has role `target`."""
    if Permission.MANAGE_USERS not in permissions_for(actor):
        return False
    return actor is Role.OWNER or target is not Role.OWNER
