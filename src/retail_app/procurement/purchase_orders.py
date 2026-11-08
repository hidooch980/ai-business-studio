"""Purchase-order domain primitives using integer minor currency units."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum


class PurchaseOrderStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    PARTIALLY_RECEIVED = "partially_received"
    RECEIVED = "received"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class PurchaseOrderLine:
    line_number: int
    item_id: str
    description: str
    quantity_milli: int
    unit_price_minor: int

    def __post_init__(self) -> None:
        if self.line_number < 1 or not self.item_id.strip():
            raise ValueError("line_number and item_id are required")
        if not self.description.strip():
            raise ValueError("line description is required")
        if self.quantity_milli <= 0:
            raise ValueError("quantity_milli must be positive")
        if self.unit_price_minor < 0:
            raise ValueError("unit_price_minor cannot be negative")

    @property
    def line_total_minor(self) -> int:
        numerator = self.quantity_milli * self.unit_price_minor
        if numerator % 1000:
            raise ValueError("line total has fractional minor units; define an explicit rounding policy")
        return numerator // 1000


@dataclass(frozen=True, slots=True)
class PurchaseOrder:
    id: str
    tenant_id: str
    branch_id: str
    supplier_id: str
    currency: str
    order_date: date
    lines: tuple[PurchaseOrderLine, ...]
    status: PurchaseOrderStatus = PurchaseOrderStatus.DRAFT

    def __post_init__(self) -> None:
        if not all(value.strip() for value in (self.id, self.tenant_id, self.branch_id, self.supplier_id)):
            raise ValueError("purchase order identifiers are required")
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError("currency must be a three-letter code")
        if not self.lines:
            raise ValueError("purchase order requires at least one line")
        numbers = [line.line_number for line in self.lines]
        if len(numbers) != len(set(numbers)):
            raise ValueError("purchase order line numbers must be unique")

    @property
    def total_minor(self) -> int:
        return sum(line.line_total_minor for line in self.lines)
