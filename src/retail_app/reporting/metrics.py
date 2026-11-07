from dataclasses import dataclass
from decimal import Decimal
from collections.abc import Iterable


@dataclass(frozen=True)
class SaleFact:
    gross_amount: Decimal
    discount_amount: Decimal
    return_amount: Decimal
    tax_amount: Decimal
    cogs_amount: Decimal
    posted: bool = True
    voided: bool = False


@dataclass(frozen=True)
class ExpenseFact:
    amount: Decimal
    posted: bool = True


def summarize_sales(sales: Iterable[SaleFact], expenses: Iterable[ExpenseFact] = ()) -> dict:
    """Aggregate posted facts only. Monetary values remain Decimal until API serialization."""
    valid = [s for s in sales if s.posted and not s.voided]
    gross = sum((s.gross_amount for s in valid), Decimal("0"))
    discounts = sum((s.discount_amount for s in valid), Decimal("0"))
    returns = sum((s.return_amount for s in valid), Decimal("0"))
    tax = sum((s.tax_amount for s in valid), Decimal("0"))
    cogs = sum((s.cogs_amount for s in valid), Decimal("0"))
    net_including_tax = gross - discounts - returns
    net_excluding_tax = net_including_tax - tax
    profit = net_excluding_tax - cogs
    posted_expenses = sum((e.amount for e in expenses if e.posted), Decimal("0"))
    margin = (profit / net_excluding_tax) if net_excluding_tax else None
    return {
        "sale_count": len(valid),
        "gross_sales": gross,
        "discounts": discounts,
        "returns": returns,
        "tax": tax,
        "net_sales_including_tax": net_including_tax,
        "net_sales_excluding_tax": net_excluding_tax,
        "cogs": cogs,
        "gross_profit": profit,
        "gross_margin": margin,
        "posted_operating_expenses": posted_expenses,
        "operating_result_before_unmodeled_costs": profit - posted_expenses,
        "average_basket": (net_including_tax / len(valid)) if valid else None,
        "currency": None,
        "data_status": "calculated_from_supplied_posted_facts",
    }
