"""Supplier domain primitives."""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class SupplierStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    BLOCKED = "blocked"


@dataclass(frozen=True, slots=True)
class Supplier:
    id: str
    tenant_id: str
    legal_name: str
    status: SupplierStatus = SupplierStatus.ACTIVE
    tax_identifier: str | None = None
    phone: str | None = None
    email: str | None = None
    address: str | None = None

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.tenant_id.strip():
            raise ValueError("supplier id and tenant_id are required")
        if not 1 <= len(self.legal_name.strip()) <= 200:
            raise ValueError("supplier legal_name must contain 1 to 200 characters")
        if self.email is not None and ("@" not in self.email or len(self.email) > 254):
            raise ValueError("supplier email is invalid")
        if self.tax_identifier is not None and len(self.tax_identifier.strip()) > 64:
            raise ValueError("tax_identifier is too long")
