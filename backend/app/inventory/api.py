import hashlib
import json
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field, StringConstraints, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.catalog.models import Product
from backend.app.db.session import get_db_session
from backend.app.identity.api_dependencies import TenantPrincipal, require_csrf_protection, require_permission
from backend.app.identity.models import AuditEvent
from backend.app.inventory.models import InventoryBalance, InventoryMovement, Warehouse

router = APIRouter(prefix="/inventory", tags=["inventory"])

WarehouseCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=40,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$",
    ),
]
WarehouseName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Reference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]


class WarehouseCreateRequest(BaseModel):
    code: WarehouseCode
    name: WarehouseName


class MovementCreateRequest(BaseModel):
    warehouse_id: UUID
    product_id: UUID
    movement_type: Literal["receipt", "issue", "adjustment"]
    quantity: int | None = Field(default=None, gt=0, le=2_000_000_000)
    adjustment_delta: int | None = Field(default=None, ge=-2_000_000_000, le=2_000_000_000)
    reference: Reference | None = None

    @model_validator(mode="after")
    def validate_quantity_shape(self) -> "MovementCreateRequest":
        if self.movement_type in {"receipt", "issue"}:
            if self.quantity is None or self.adjustment_delta is not None:
                raise ValueError("receipt and issue require quantity and do not accept adjustment_delta")
        elif self.quantity is not None or self.adjustment_delta is None or self.adjustment_delta == 0:
            raise ValueError("adjustment requires a non-zero adjustment_delta and does not accept quantity")
        return self

    @property
    def quantity_delta(self) -> int:
        if self.movement_type == "receipt":
            return int(self.quantity or 0)
        if self.movement_type == "issue":
            return -int(self.quantity or 0)
        return int(self.adjustment_delta or 0)


def _warehouse_dict(item: Warehouse) -> dict:
    return {
        "id": str(item.id),
        "tenant_id": str(item.tenant_id),
        "code": item.code,
        "name": item.name,
        "is_active": item.is_active,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def _movement_dict(item: InventoryMovement) -> dict:
    return {
        "id": str(item.id),
        "tenant_id": str(item.tenant_id),
        "warehouse_id": str(item.warehouse_id),
        "product_id": str(item.product_id),
        "movement_type": item.movement_type,
        "quantity_delta": item.quantity_delta,
        "idempotency_key": item.idempotency_key,
        "reference": item.reference,
        "created_at": item.created_at.isoformat(),
    }


def _request_hash(payload: MovementCreateRequest) -> str:
    canonical = {
        "warehouse_id": str(payload.warehouse_id),
        "product_id": str(payload.product_id),
        "movement_type": payload.movement_type,
        "quantity_delta": payload.quantity_delta,
        "reference": payload.reference,
    }
    encoded = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _audit(db: Session, principal: TenantPrincipal, action: str, resource_type: str, resource_id: UUID) -> None:
    db.add(
        AuditEvent(
            tenant_id=principal.tenant.id,
            actor_user_id=principal.user.id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id),
            outcome="success",
        )
    )


@router.post("/warehouses", status_code=status.HTTP_201_CREATED)
def create_warehouse(
    payload: WarehouseCreateRequest,
    principal: TenantPrincipal = Depends(require_permission("inventory.write")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    item = Warehouse(tenant_id=principal.tenant.id, code=payload.code, name=payload.name)
    db.add(item)
    try:
        db.flush()
        _audit(db, principal, "inventory.warehouse_created", "warehouse", item.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Warehouse code already exists in this tenant") from exc
    db.refresh(item)
    return _warehouse_dict(item)


@router.get("/warehouses")
def list_warehouses(
    principal: TenantPrincipal = Depends(require_permission("inventory.read")),
    db: Session = Depends(get_db_session),
    active_only: bool = True,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    statement = select(Warehouse).where(Warehouse.tenant_id == principal.tenant.id)
    if active_only:
        statement = statement.where(Warehouse.is_active.is_(True))
    items = db.scalars(statement.order_by(Warehouse.code, Warehouse.id).offset(offset).limit(limit)).all()
    return {"items": [_warehouse_dict(item) for item in items], "limit": limit, "offset": offset}


@router.post("/movements", status_code=status.HTTP_201_CREATED)
def create_inventory_movement(
    payload: MovementCreateRequest,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)],
    principal: TenantPrincipal = Depends(require_permission("inventory.write")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    key = idempotency_key.strip()
    if not key:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Idempotency-Key cannot be blank")
    request_hash = _request_hash(payload)
    existing = db.scalar(
        select(InventoryMovement).where(
            InventoryMovement.tenant_id == principal.tenant.id,
            InventoryMovement.idempotency_key == key,
        )
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Idempotency-Key was used for a different movement")
        return {**_movement_dict(existing), "replayed": True}

    warehouse = db.scalar(
        select(Warehouse).where(
            Warehouse.id == payload.warehouse_id,
            Warehouse.tenant_id == principal.tenant.id,
            Warehouse.is_active.is_(True),
        )
    )
    product = db.scalar(
        select(Product).where(
            Product.id == payload.product_id,
            Product.tenant_id == principal.tenant.id,
            Product.is_active.is_(True),
        )
    )
    if warehouse is None or product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active warehouse or product not found in this tenant")

    dialect = db.get_bind().dialect.name
    values = {
        "tenant_id": principal.tenant.id,
        "warehouse_id": warehouse.id,
        "product_id": product.id,
        "quantity_on_hand": 0,
        "updated_at": datetime.now(UTC),
    }
    if dialect == "postgresql":
        insert_statement = postgresql_insert(InventoryBalance).values(**values).on_conflict_do_nothing(
            index_elements=["tenant_id", "warehouse_id", "product_id"]
        )
    elif dialect == "sqlite":
        insert_statement = sqlite_insert(InventoryBalance).values(**values).on_conflict_do_nothing(
            index_elements=["tenant_id", "warehouse_id", "product_id"]
        )
    else:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Unsupported inventory database")
    db.execute(insert_statement)
    balance = db.scalar(
        select(InventoryBalance)
        .where(
            InventoryBalance.tenant_id == principal.tenant.id,
            InventoryBalance.warehouse_id == warehouse.id,
            InventoryBalance.product_id == product.id,
        )
        .with_for_update()
    )
    if balance is None:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Inventory balance could not be locked")

    delta = payload.quantity_delta
    if balance.quantity_on_hand + delta < 0:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Insufficient stock for this movement")
    balance.quantity_on_hand += delta
    balance.updated_at = datetime.now(UTC)
    movement = InventoryMovement(
        tenant_id=principal.tenant.id,
        warehouse_id=warehouse.id,
        product_id=product.id,
        movement_type=payload.movement_type,
        quantity_delta=delta,
        idempotency_key=key,
        request_hash=request_hash,
        reference=payload.reference,
        created_by_user_id=principal.user.id,
    )
    db.add(movement)
    try:
        db.flush()
        _audit(db, principal, "inventory.movement_created", "inventory_movement", movement.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        replay = db.scalar(
            select(InventoryMovement).where(
                InventoryMovement.tenant_id == principal.tenant.id,
                InventoryMovement.idempotency_key == key,
            )
        )
        if replay is not None and replay.request_hash == request_hash:
            return {**_movement_dict(replay), "replayed": True}
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Inventory movement conflicts with existing stock data") from exc
    db.refresh(movement)
    return {**_movement_dict(movement), "replayed": False}


@router.get("/balances")
def list_inventory_balances(
    principal: TenantPrincipal = Depends(require_permission("inventory.read")),
    db: Session = Depends(get_db_session),
    warehouse_id: UUID | None = None,
    product_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    statement = (
        select(InventoryBalance, Warehouse, Product)
        .join(Warehouse, Warehouse.id == InventoryBalance.warehouse_id)
        .join(Product, Product.id == InventoryBalance.product_id)
        .where(InventoryBalance.tenant_id == principal.tenant.id)
    )
    if warehouse_id is not None:
        statement = statement.where(InventoryBalance.warehouse_id == warehouse_id)
    if product_id is not None:
        statement = statement.where(InventoryBalance.product_id == product_id)
    rows = db.execute(
        statement.order_by(Warehouse.code, Product.sku).offset(offset).limit(limit)
    ).all()
    return {
        "items": [
            {
                "warehouse_id": str(balance.warehouse_id),
                "warehouse_code": warehouse.code,
                "product_id": str(balance.product_id),
                "product_sku": product.sku,
                "product_name": product.name,
                "unit_code": product.unit_code,
                "quantity_on_hand": balance.quantity_on_hand,
                "updated_at": balance.updated_at.isoformat(),
            }
            for balance, warehouse, product in rows
        ],
        "limit": limit,
        "offset": offset,
    }


@router.get("/movements")
def list_inventory_movements(
    principal: TenantPrincipal = Depends(require_permission("inventory.read")),
    db: Session = Depends(get_db_session),
    warehouse_id: UUID | None = None,
    product_id: UUID | None = None,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    statement = select(InventoryMovement).where(InventoryMovement.tenant_id == principal.tenant.id)
    if warehouse_id is not None:
        statement = statement.where(InventoryMovement.warehouse_id == warehouse_id)
    if product_id is not None:
        statement = statement.where(InventoryMovement.product_id == product_id)
    items = db.scalars(
        statement.order_by(InventoryMovement.created_at.desc(), InventoryMovement.id.desc()).offset(offset).limit(limit)
    ).all()
    return {"items": [_movement_dict(item) for item in items], "limit": limit, "offset": offset}
