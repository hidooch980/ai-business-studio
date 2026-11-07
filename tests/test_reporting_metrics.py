from decimal import Decimal as D

from retail_app.reporting.metrics import ExpenseFact, SaleFact, summarize_sales


def test_sales_summary_excludes_unposted_and_voided_records():
    rows = [
        SaleFact(D("100"), D("10"), D("0"), D("9"), D("50")),
        SaleFact(D("500"), D("0"), D("0"), D("0"), D("0"), posted=False),
        SaleFact(D("200"), D("0"), D("0"), D("18"), D("80"), voided=True),
    ]
    result = summarize_sales(rows, [ExpenseFact(D("5")), ExpenseFact(D("99"), posted=False)])
    assert result["sale_count"] == 1
    assert result["net_sales_including_tax"] == D("90")
    assert result["net_sales_excluding_tax"] == D("81")
    assert result["gross_profit"] == D("31")
    assert result["posted_operating_expenses"] == D("5")


def test_zero_denominators_are_null_not_fake_zero_percentages():
    result = summarize_sales([])
    assert result["gross_margin"] is None
    assert result["average_basket"] is None


def test_returns_and_discounts_reduce_net_sales():
    result = summarize_sales([SaleFact(D("250"), D("20"), D("30"), D("20"), D("100"))])
    assert result["net_sales_including_tax"] == D("200")
    assert result["gross_profit"] == D("80")
