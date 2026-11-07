from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import Annotated

from backend.app.db.session import get_db_session
from backend.app.identity.api_dependencies import TenantPrincipal, require_permission
from backend.app.identity.models import AuditEvent, Membership, MembershipRole, Permission, Role, RolePermission
from backend.app.identity.permissions import PERMISSION_CATALOG

router = APIRouter(prefix="/access", tags=["access-control"])

RoleName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9 _.-]*$")]
RoleDescription = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]


class RoleCreateRequest(BaseModel):
    name: RoleName
    description: RoleDescription | None = None


class RolePermissionsRequest(BaseModel):
    permission_codes: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=120)]] = Field(max_length=100)


def _audit(db: Session, principal: TenantPrincipal, action: str, resource_type: str, resource_id: str) -> None:
    db.add(AuditEvent(
        tenant_id=principal.tenant.id,
        actor_user_id=principal.user.id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        outcome="success",
    ))


@router.get("/permissions")
def list_permissions(
    principal: TenantPrincipal = Depends(require_permission("access.roles.read")),
    db: Session = Depends(get_db_session),
) -> dict:
    permissions = db.scalars(select(Permission).order_by(Permission.code)).all()
    return {"items": [{"code": item.code, "description": item.description} for item in permissions]}


@router.get("/roles")
def list_roles(
    principal: TenantPrincipal = Depends(require_permission("access.roles.read")),
    db: Session = Depends(get_db_session),
) -> dict:
    roles = db.scalars(
        select(Role).where(Role.tenant_id == principal.tenant.id).order_by(Role.name, Role.id)
    ).all()
    result = []
    for role in roles:
        codes = db.scalars(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role.id)
            .order_by(Permission.code)
        ).all()
        result.append({
            "id": str(role.id),
            "name": role.name,
            "description": role.description,
            "is_system": role.is_system,
            "permission_codes": codes,
        })
    return {"items": result}


@router.post("/roles", status_code=status.HTTP_201_CREATED)
def create_role(
    payload: RoleCreateRequest,
    principal: TenantPrincipal = Depends(require_permission("access.roles.manage")),
    db: Session = Depends(get_db_session),
) -> dict:
    role = Role(tenant_id=principal.tenant.id, name=payload.name, description=payload.description)
    db.add(role)
    try:
        db.flush()
        _audit(db, principal, "access.role_created", "role", str(role.id))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Role name already exists") from exc
    return {"id": str(role.id), "name": role.name, "description": role.description, "is_system": role.is_system}


@router.put("/roles/{role_id}/permissions")
def replace_role_permissions(
    role_id: UUID,
    payload: RolePermissionsRequest,
    principal: TenantPrincipal = Depends(require_permission("access.roles.manage")),
    db: Session = Depends(get_db_session),
) -> dict:
    role = db.scalar(select(Role).where(Role.id == role_id, Role.tenant_id == principal.tenant.id))
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="System roles cannot be modified")
    codes = sorted(set(payload.permission_codes))
    permissions = db.scalars(select(Permission).where(Permission.code.in_(codes))).all() if codes else []
    found_codes = {item.code for item in permissions}
    if found_codes != set(codes):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unknown permission code")
    db.query(RolePermission).filter(RolePermission.role_id == role.id).delete(synchronize_session=False)
    db.add_all([RolePermission(role_id=role.id, permission_id=item.id) for item in permissions])
    _audit(db, principal, "access.role_permissions_replaced", "role", str(role.id))
    db.commit()
    return {"role_id": str(role.id), "permission_codes": codes}


@router.put("/memberships/{membership_id}/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def assign_membership_role(
    membership_id: UUID,
    role_id: UUID,
    principal: TenantPrincipal = Depends(require_permission("access.memberships.manage")),
    db: Session = Depends(get_db_session),
) -> None:
    membership = db.scalar(select(Membership).where(
        Membership.id == membership_id,
        Membership.tenant_id == principal.tenant.id,
        Membership.is_active.is_(True),
    ))
    role = db.scalar(select(Role).where(Role.id == role_id, Role.tenant_id == principal.tenant.id))
    if membership is None or role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership or role not found")
    exists = db.scalar(select(MembershipRole.id).where(
        MembershipRole.tenant_id == principal.tenant.id,
        MembershipRole.membership_id == membership.id,
        MembershipRole.role_id == role.id,
    ))
    if exists is None:
        db.add(MembershipRole(tenant_id=principal.tenant.id, membership_id=membership.id, role_id=role.id))
    _audit(db, principal, "access.membership_role_assigned", "membership", str(membership.id))
    db.commit()
