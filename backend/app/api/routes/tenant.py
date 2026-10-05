"""The caller's workspace (tenant) and its members.

There is no tenant id in any path or body: every query is scoped to the tenant of the
authenticated session. A user id from another tenant is indistinguishable from an
unknown id (404).
"""

import uuid

from fastapi import APIRouter, Depends

from app.api.deps import AuthDb, CurrentPrincipal, require_permission
from app.api.routes.auth import no_store
from app.auth.permissions import Permission
from app.schemas.auth import CreateMemberRequest, Member, TenantDetail, UpdateMemberRequest
from app.schemas.common import DataResponse, ErrorResponse
from app.services import auth as auth_service

router = APIRouter(prefix="/tenant", tags=["tenant"], dependencies=[Depends(no_store)], responses={
    401: {"model": ErrorResponse, "description": "Not signed in or session expired."},
    403: {"model": ErrorResponse, "description": "Missing permission or role rule violated."},
    422: {"model": ErrorResponse, "description": "Invalid request."},
})

ManageUsers = Depends(require_permission(Permission.MANAGE_USERS))


@router.get("", response_model=DataResponse[TenantDetail], summary="Your workspace")
def get_tenant(principal: CurrentPrincipal, conn: AuthDb):
    return {"data": auth_service.tenant_detail(conn, principal)}


@router.get("/members", response_model=DataResponse[list[Member]], dependencies=[ManageUsers],
            summary="Members of your workspace (MANAGE_USERS)")
def list_members(principal: CurrentPrincipal, conn: AuthDb):
    return {"data": auth_service.list_members(conn, principal)}


@router.post("/members", status_code=201, response_model=DataResponse[Member], dependencies=[ManageUsers],
             summary="Add a user to your workspace with an initial password (MANAGE_USERS)",
             responses={409: {"model": ErrorResponse, "description": "Email already registered."}})
def create_member(body: CreateMemberRequest, principal: CurrentPrincipal, conn: AuthDb):
    return {"data": auth_service.create_member(conn, principal, email=body.email, display_name=body.display_name,
                                               password=body.password, role=body.role)}


@router.patch("/members/{user_id}", response_model=DataResponse[Member], dependencies=[ManageUsers],
              summary="Change a member's role or active status (MANAGE_USERS)",
              responses={404: {"model": ErrorResponse, "description": "No such member in your workspace."},
                         409: {"model": ErrorResponse, "description": "Would leave no active owner."}})
def update_member(user_id: uuid.UUID, body: UpdateMemberRequest, principal: CurrentPrincipal, conn: AuthDb):
    return {"data": auth_service.update_member(conn, principal, user_id, role=body.role,
                                               is_active=body.is_active)}
