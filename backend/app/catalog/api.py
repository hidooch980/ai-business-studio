from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, StringConstraints, model_validator
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.session import get_db_session
from backend.app.catalog.models import Product
from backend.app.identity.api_dependencies import TenantPrincipal, require_csrf_protection, require_permission
from backend.app.identity.models import AuditEvent

router = APIRouter(prefix="/catalog/products", tags=["product-catalog"])

Sku = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")]
ProductName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
UnitCode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
Barcode = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)]


class ProductCreateRequest(BaseModel):
    sku: Sku
    name: ProductName
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None
    unit_code: UnitCode = "pcs"
    barcode: Barcode | None = None


class ProductUpdateRequest(BaseModel):
    sku: Sku | None = None
    name: ProductName | None = None
    description: Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)] | None = None
    unit_code: UnitCode | None = None
    barcode: Barcode | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "ProductUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("At least one product field must be supplied")
        for field in ("sku", "name", "unit_code", "is_active"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


def _serialize(product: Product) -> dict:
    return {
        "id": str(product.id),
        "tenant_id": str(product.tenant_id),
        "sku": product.sku,
        "name": product.name,
        "description": product.description,
        "unit_code": product.unit_code,
        "barcode": product.barcode,
        "is_active": product.is_active,
        "created_at": product.created_at.isoformat(),
        "updated_at": product.updated_at.isoformat(),
    }


def _audit(db: Session, principal: TenantPrincipal, action: str, product: Product) -> None:
    db.add(
        AuditEvent(
            tenant_id=principal.tenant.id,
            actor_user_id=principal.user.id,
            action=action,
            resource_type="product",
            resource_id=str(product.id),
            outcome="success",
        )
    )


@router.get("")
def list_products(
    principal: TenantPrincipal = Depends(require_permission("catalog.read")),
    db: Session = Depends(get_db_session),
    search: str | None = Query(default=None, min_length=1, max_length=128),
    active_only: bool = True,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> dict:
    statement = select(Product).where(Product.tenant_id == principal.tenant.id)
    if active_only:
        statement = statement.where(Product.is_active.is_(True))
    if search:
        term = f"%{search.strip()}%"
        statement = statement.where(
            or_(
                Product.sku.ilike(term),
                Product.name.ilike(term),
                Product.barcode.ilike(term),
            )
        )
    products = db.scalars(
        statement.order_by(Product.name, Product.sku, Product.id).offset(offset).limit(limit)
    ).all()
    return {"items": [_serialize(item) for item in products], "limit": limit, "offset": offset}


@router.post("", status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreateRequest,
    principal: TenantPrincipal = Depends(require_permission("catalog.write")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    product = Product(
        tenant_id=principal.tenant.id,
        sku=payload.sku,
        name=payload.name,
        description=payload.description,
        unit_code=payload.unit_code,
        barcode=payload.barcode,
    )
    db.add(product)
    try:
        db.flush()
        _audit(db, principal, "catalog.product_created", product)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SKU or barcode already exists in this tenant") from exc
    db.refresh(product)
    return _serialize(product)


@router.patch("/{product_id}")
def update_product(
    product_id: UUID,
    payload: ProductUpdateRequest,
    principal: TenantPrincipal = Depends(require_permission("catalog.write")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> dict:
    product = db.scalar(
        select(Product)
        .where(Product.id == product_id, Product.tenant_id == principal.tenant.id)
        .with_for_update()
    )
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    product.updated_at = datetime.now(UTC)
    try:
        _audit(db, principal, "catalog.product_updated", product)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="SKU or barcode already exists in this tenant") from exc
    db.refresh(product)
    return _serialize(product)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_product(
    product_id: UUID,
    principal: TenantPrincipal = Depends(require_permission("catalog.write")),
    _csrf: None = Depends(require_csrf_protection),
    db: Session = Depends(get_db_session),
) -> None:
    product = db.scalar(
        select(Product)
        .where(Product.id == product_id, Product.tenant_id == principal.tenant.id)
        .with_for_update()
    )
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    if product.is_active:
        product.is_active = False
        product.updated_at = datetime.now(UTC)
        _audit(db, principal, "catalog.product_deactivated", product)
        db.commit()
