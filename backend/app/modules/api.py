"""Tenant module and subscription administration endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.db.session import get_db_session
from backend.app.identity.api_dependencies import (
    TenantPrincipal,
    require_csrf_protection,
    require_permission,
)
from backend.app.identity.models import (
    AuditEvent,
    TenantModuleEntitlement,
    TenantSubscription,
)
from backend.app.modules.registry import (
    EDITION_BY_ID,
    MODULE_BY_ID,
    MODULES,
    Edition,
    ModuleStatus,
    resolve_edition,
)

router = APIRouter(prefix="/modules", tags=["module-management"])


class EditionChangeRequest(BaseModel):
    edition: Edition


class ModuleToggleRequest(BaseModel):
    is_enabled: bool


def _audit(
    db: Session,
    principal: TenantPrincipal,
    action: str,
    resource_id: str,
) -> None:
    db.add(
        AuditEvent(
            tenant_id=principal.tenant.id,
            actor_user_id=principal.user.id,
            action=action,
            resource_type="module_entitlement",
            resource_id=resource_id,
            outcome="success",
        )
    )


def _dependency_closure(module_id: str) -> set[str]:
    required: set[str] = set()
    pending = list(MODULE_BY_ID[module_id].dependencies)
    while pending:
        dependency_id = pending.pop()
        if dependency_id in required:
            continue
        required.add(dependency_id)
        pending.extend(MODULE_BY_ID[dependency_id].dependencies)
    return required


@router.get("")
def list_tenant_modules(
    principal: TenantPrincipal = Depends(require_permission("modules.read")),
    db: Session = Depends(get_db_session),
) -> dict:
    subscription = db.scalar(
        select(TenantSubscription).where(
            TenantSubscription.tenant_id == principal.tenant.id
        )
    )
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Tenant subscription has not been provisioned",
        )
    entitlements = {
        item.module_id: item
        for item in db.scalars(
            select(TenantModuleEntitlement).where(
                TenantModuleEntitlement.tenant_id == principal.tenant.id
            )
        ).all()
    }
    items = []
    for definition in MODULES:
        entitlement = entitlements.get(definition.module_id)
        items.append(
            {
                "module_id": definition.module_id,
                "name": definition.name,
                "version": definition.module_version,
                "lifecycle": definition.status.value,
                "dependencies": list(definition.dependencies),
                "is_entitled": bool(entitlement and entitlement.is_entitled),
                "is_enabled": bool(entitlement and entitlement.is_enabled),
                "source": entitlement.source if entitlement else None,
                "can_activate": bool(
                    entitlement
                    and entitlement.is_entitled
                    and definition.status is not ModuleStatus.PLANNED
                    and all(
                        entitlements.get(dependency)
                        and entitlements[dependency].is_entitled
                        for dependency in _dependency_closure(definition.module_id)
                    )
                ),
            }
        )
    return {
        "edition": subscription.edition,
        "subscription_status": subscription.status,
        "modules": items,
    }


@router.put("/edition")
def change_tenant_edition(
    payload: EditionChangeRequest,
    principal: TenantPrincipal = Depends(require_permission("modules.manage")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    subscription = db.scalar(
        select(TenantSubscription)
        .where(TenantSubscription.tenant_id == principal.tenant.id)
        .with_for_update()
    )
    if subscription is None:
        subscription = TenantSubscription(
            tenant_id=principal.tenant.id,
            edition=payload.edition.value,
            status="active",
            created_by_user_id=principal.user.id,
            updated_by_user_id=principal.user.id,
        )
        db.add(subscription)
    else:
        subscription.edition = payload.edition.value
        subscription.updated_by_user_id = principal.user.id

    resolved = resolve_edition(payload.edition)
    selected = {
        item["module_id"]
        for item in resolved["modules"]
        if item["included_by_edition_or_addon"]
    }
    rows = {
        item.module_id: item
        for item in db.scalars(
            select(TenantModuleEntitlement)
            .where(TenantModuleEntitlement.tenant_id == principal.tenant.id)
            .with_for_update()
        ).all()
    }
    for definition in MODULES:
        entitled = definition.module_id in selected
        dependencies_ready = all(
            dependency in selected
            and MODULE_BY_ID[dependency].status is not ModuleStatus.PLANNED
            for dependency in _dependency_closure(definition.module_id)
        )
        enabled = (
            entitled
            and dependencies_ready
            and definition.status is not ModuleStatus.PLANNED
        )
        row = rows.get(definition.module_id)
        if row is None:
            row = TenantModuleEntitlement(
                tenant_id=principal.tenant.id,
                module_id=definition.module_id,
            )
            db.add(row)
        row.source = "edition"
        row.is_entitled = entitled
        row.is_enabled = enabled
        row.updated_by_user_id = principal.user.id

    _audit(db, principal, "modules.edition_changed", payload.edition.value)
    db.commit()
    return {
        "edition": payload.edition.value,
        "message": "Edition updated. Modules not included in the new edition were disabled; their data was retained.",
    }


@router.put("/{module_id}")
def set_module_enabled(
    module_id: str,
    payload: ModuleToggleRequest,
    principal: TenantPrincipal = Depends(require_permission("modules.manage")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    definition = MODULE_BY_ID.get(module_id)
    if definition is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown module")
    if definition.status is ModuleStatus.PLANNED:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Module is not released")

    db.scalar(
        select(TenantSubscription)
        .where(TenantSubscription.tenant_id == principal.tenant.id)
        .with_for_update()
    )
    rows = {
        item.module_id: item
        for item in db.scalars(
            select(TenantModuleEntitlement)
            .where(TenantModuleEntitlement.tenant_id == principal.tenant.id)
            .with_for_update()
        ).all()
    }
    row = rows.get(module_id)
    if row is None or not row.is_entitled:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Module is not included in the tenant edition or an add-on",
        )

    dependencies = _dependency_closure(module_id)
    if payload.is_enabled:
        missing = [
            dependency
            for dependency in dependencies
            if dependency not in rows
            or not rows[dependency].is_entitled
            or not rows[dependency].is_enabled
        ]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": "Required modules must be entitled and enabled", "missing": sorted(missing)},
            )
    else:
        dependents = [
            other.module_id
            for other in MODULES
            if other.module_id in rows
            and rows[other.module_id].is_enabled
            and module_id in _dependency_closure(other.module_id)
        ]
        if dependents:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"message": "Disable dependent modules first", "dependent_modules": sorted(dependents)},
            )

    row.is_enabled = payload.is_enabled
    row.updated_by_user_id = principal.user.id
    _audit(
        db,
        principal,
        "modules.enabled" if payload.is_enabled else "modules.disabled",
        module_id,
    )
    db.commit()
    return {"module_id": module_id, "is_enabled": row.is_enabled}


@router.get("/editions")
def list_product_editions(
    _principal: TenantPrincipal = Depends(require_permission("modules.read")),
) -> dict:
    return {
        "items": [
            {
                "edition": edition.value,
                "name": definition.name,
                "included_modules": list(definition.included_modules),
                "description": definition.description,
            }
            for edition, definition in EDITION_BY_ID.items()
        ]
    }
