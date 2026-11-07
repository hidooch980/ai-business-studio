from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, StringConstraints, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.session import get_db_session
from backend.app.identity.api_dependencies import TenantPrincipal, require_csrf_protection, require_permission
from backend.app.identity.models import AuditEvent, Membership, MembershipRole, Permission, Role, RolePermission, Tenant, User

router = APIRouter(prefix="/access", tags=["access-control"])

RoleName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9 _.-]*$")]
RoleDescription = Annotated[str, StringConstraints(strip_whitespace=True, max_length=255)]


class RoleCreateRequest(BaseModel):
    name: RoleName
    description: RoleDescription | None = None


class RolePermissionsRequest(BaseModel):
    permission_codes: list[Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=120)]] = Field(max_length=100)


class RoleUpdateRequest(BaseModel):
    name: RoleName | None = None
    description: RoleDescription | None = None

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "RoleUpdateRequest":
        if self.name is None and self.description is None:
            raise ValueError("At least one role field must be supplied")
        return self


class MembershipStatusRequest(BaseModel):
    is_active: bool


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
    _csrf: None = Depends(require_csrf_protection),
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



@router.patch("/roles/{role_id}")
def update_role(
    role_id: UUID,
    payload: RoleUpdateRequest,
    principal: TenantPrincipal = Depends(require_permission("access.roles.manage")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    role = db.scalar(select(Role).where(Role.id == role_id, Role.tenant_id == principal.tenant.id).with_for_update())
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="System roles cannot be modified")
    if payload.name is not None:
        role.name = payload.name
    if payload.description is not None:
        role.description = payload.description
    try:
        _audit(db, principal, "access.role_updated", "role", str(role.id))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Role name already exists") from exc
    return {"id": str(role.id), "name": role.name, "description": role.description, "is_system": role.is_system}


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_role(
    role_id: UUID,
    principal: TenantPrincipal = Depends(require_permission("access.roles.manage")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> None:
    role = db.scalar(select(Role).where(Role.id == role_id, Role.tenant_id == principal.tenant.id).with_for_update())
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.is_system:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="System roles cannot be deleted")
    assigned = db.scalar(select(MembershipRole.id).where(
        MembershipRole.tenant_id == principal.tenant.id,
        MembershipRole.role_id == role.id,
    ))
    if assigned is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Role is assigned to one or more memberships")
    db.query(RolePermission).filter(RolePermission.role_id == role.id).delete(synchronize_session=False)
    _audit(db, principal, "access.role_deleted", "role", str(role.id))
    db.delete(role)
    db.commit()

@router.put("/roles/{role_id}/permissions")
def replace_role_permissions(
    role_id: UUID,
    payload: RolePermissionsRequest,
    principal: TenantPrincipal = Depends(require_permission("access.roles.manage")),
    _csrf: None = Depends(require_csrf_protection),
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
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> None:
    _lock_tenant(db, principal.tenant.id)
    membership = db.scalar(select(Membership).where(
        Membership.id == membership_id,
        Membership.tenant_id == principal.tenant.id,
        Membership.is_active.is_(True),
    ).with_for_update())
    role = db.scalar(select(Role).where(Role.id == role_id, Role.tenant_id == principal.tenant.id).with_for_update())
    if membership is None or role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership or role not found")
    if role.is_system and (
        role.name != "owner" or not _is_active_owner(db, principal.tenant.id, principal.membership.id)
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only an active owner can assign system roles")
    exists = db.scalar(select(MembershipRole.id).where(
        MembershipRole.tenant_id == principal.tenant.id,
        MembershipRole.membership_id == membership.id,
        MembershipRole.role_id == role.id,
    ))
    if exists is None:
        db.add(MembershipRole(tenant_id=principal.tenant.id, membership_id=membership.id, role_id=role.id))
    _audit(db, principal, "access.membership_role_assigned", "membership", str(membership.id))
    db.commit()



def _lock_tenant(db: Session, tenant_id: UUID) -> None:
    db.scalar(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update())


def _is_active_owner(db: Session, tenant_id: UUID, membership_id: UUID) -> bool:
    owner_assignment = db.scalar(
        select(MembershipRole.id)
        .join(Role, Role.id == MembershipRole.role_id)
        .where(
            MembershipRole.tenant_id == tenant_id,
            MembershipRole.membership_id == membership_id,
            Role.tenant_id == tenant_id,
            Role.name == "owner",
            Role.is_system.is_(True),
        )
    )
    return owner_assignment is not None


def _active_owner_count(db: Session, tenant_id: UUID, excluding_membership_id: UUID | None = None) -> int:
    statement = (
        select(func.count(MembershipRole.id))
        .join(Membership, Membership.id == MembershipRole.membership_id)
        .join(Role, Role.id == MembershipRole.role_id)
        .where(
            MembershipRole.tenant_id == tenant_id,
            Membership.tenant_id == tenant_id,
            Membership.is_active.is_(True),
            Role.tenant_id == tenant_id,
            Role.is_system.is_(True),
            Role.name == "owner",
        )
    )
    if excluding_membership_id is not None:
        statement = statement.where(Membership.id != excluding_membership_id)
    return db.scalar(statement) or 0


@router.get("/memberships")
def list_memberships(
    principal: TenantPrincipal = Depends(require_permission("users.read")),
    db: Session = Depends(get_db_session),
) -> dict:
    rows = db.execute(
        select(Membership, User)
        .join(User, User.id == Membership.user_id)
        .where(Membership.tenant_id == principal.tenant.id)
        .order_by(User.display_name, User.email, Membership.id)
    ).all()
    items = []
    for membership, user in rows:
        roles = db.execute(
            select(Role.id, Role.name, Role.is_system)
            .join(MembershipRole, MembershipRole.role_id == Role.id)
            .where(
                MembershipRole.tenant_id == principal.tenant.id,
                MembershipRole.membership_id == membership.id,
                Role.tenant_id == principal.tenant.id,
            )
            .order_by(Role.name, Role.id)
        ).all()
        items.append({
            "id": str(membership.id),
            "user_id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "user_is_active": user.is_active,
            "is_active": membership.is_active,
            "roles": [
                {"id": str(role_id), "name": name, "is_system": is_system}
                for role_id, name, is_system in roles
            ],
            "created_at": membership.created_at.isoformat(),
        })
    return {"items": items}


@router.patch("/memberships/{membership_id}")
def set_membership_status(
    membership_id: UUID,
    payload: MembershipStatusRequest,
    principal: TenantPrincipal = Depends(require_permission("users.manage")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    _lock_tenant(db, principal.tenant.id)
    membership = db.scalar(
        select(Membership).where(
            Membership.id == membership_id,
            Membership.tenant_id == principal.tenant.id,
        ).with_for_update()
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership not found")
    if not payload.is_active and membership.user_id == principal.user.id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="You cannot deactivate your own membership")
    if not payload.is_active and membership.is_active:
        owner_role = db.scalar(
            select(Role).where(
                Role.tenant_id == principal.tenant.id,
                Role.name == "owner",
                Role.is_system.is_(True),
            )
        )
        if owner_role is not None:
            assigned_owner = db.scalar(
                select(MembershipRole.id).where(
                    MembershipRole.tenant_id == principal.tenant.id,
                    MembershipRole.membership_id == membership.id,
                    MembershipRole.role_id == owner_role.id,
                )
            )
            if assigned_owner is not None and _active_owner_count(
                db, principal.tenant.id, excluding_membership_id=membership.id
            ) == 0:
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The last active owner cannot be deactivated")
    membership.is_active = payload.is_active
    _audit(
        db,
        principal,
        "access.membership_activated" if payload.is_active else "access.membership_deactivated",
        "membership",
        str(membership.id),
    )
    db.commit()
    return {"id": str(membership.id), "is_active": membership.is_active}


@router.delete("/memberships/{membership_id}/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_membership_role(
    membership_id: UUID,
    role_id: UUID,
    principal: TenantPrincipal = Depends(require_permission("access.memberships.manage")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> None:
    _lock_tenant(db, principal.tenant.id)
    membership = db.scalar(
        select(Membership).where(
            Membership.id == membership_id,
            Membership.tenant_id == principal.tenant.id,
        ).with_for_update()
    )
    role = db.scalar(
        select(Role).where(
            Role.id == role_id,
            Role.tenant_id == principal.tenant.id,
        ).with_for_update()
    )
    if membership is None or role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Membership or role not found")
    assignment = db.scalar(
        select(MembershipRole).where(
            MembershipRole.tenant_id == principal.tenant.id,
            MembershipRole.membership_id == membership.id,
            MembershipRole.role_id == role.id,
        )
    )
    if assignment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role assignment not found")
    if role.is_system and role.name == "owner" and membership.is_active:
        if _active_owner_count(db, principal.tenant.id, excluding_membership_id=membership.id) == 0:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The last active owner role cannot be removed")
    db.delete(assignment)
    _audit(db, principal, "access.membership_role_removed", "membership", str(membership.id))
    db.commit()
