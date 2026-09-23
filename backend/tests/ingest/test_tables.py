"""Data tables on real filing pages, as Markdown blocks."""

from ingest import xhtml


def _tables(filing_root, name: str) -> list[str]:
    pages = xhtml.read_pages(filing_root(name))
    return [
        block.markdown
        for page in pages
        for block in page.blocks
        if isinstance(block, xhtml.DataTable)
    ]


def test_workiva_figures_are_rejoined_under_their_headers(filing_root):
    # Workiva puts "$" | "201,183" and "(2)" | "%" in cells of their own, under
    # one header each. The lead-in naming the units, and the footnote, stay
    # in the table's block.
    assert (
        "The following table shows net sales by category for 2024, 2023 and 2022 "
        "(dollars in millions):\n"
        "|  | 2024 | Change | 2023 | Change | 2022 |\n"
        "| --- | --- | --- | --- | --- | --- |\n"
        "| iPhone | $201,183 | —% | $200,583 | (2)% | $205,489 |\n"
        "| Mac | 29,984 | 2% | 29,357 | (27)% | 40,177 |\n"
        "| iPad | 26,694 | (6)% | 28,300 | (3)% | 29,292 |\n"
        "| Wearables, Home and Accessories | 37,005 | (7)% | 39,845 | (3)% | 41,241 |\n"
        "| Services (1) | 96,169 | 13% | 85,200 | 9% | 78,129 |\n"
        "| Total net sales | $391,035 | 2% | $383,285 | (3)% | $394,328 |\n"
        "(1)Services net sales include amortization of the deferred value of services "
        "bundled in the sales price of certain products."
    ) in _tables(filing_root, "aapl_2024_net_sales.htm")


def test_dfin_negatives_are_rejoined(filing_root):
    # Microsoft's generator writes "$" | "(9,605" | ")", and puts the header
    # over the middle cell only.
    (table,) = _tables(filing_root, "msft_2024_item_7a.htm")

    assert table.startswith(
        "(In millions)\n"
        "| Risk Categories | Hypothetical Change | June 30, 2024 | Impact |\n"
        "| --- | --- | --- | --- |\n"
        "| Foreign currency – Revenue | 10% decrease in foreign exchange rates | $(9,605) | Earnings |\n"
    )


def test_a_header_spanning_its_columns_heads_each_of_them(filing_root):
    # "Year Ended December 31," spans the three years; the rows naming a
    # segment stay rows, above the figures they group.
    (table,) = _tables(filing_root, "amzn_2024_segments.htm")

    assert table.startswith(
        "Information on reportable segments and reconciliation to consolidated net "
        "income (loss) is as follows (in millions):\n"
        "|  | Year Ended December 31, 2022 | Year Ended December 31, 2023 "
        "| Year Ended December 31, 2024 |\n"
        "| --- | --- | --- | --- |\n"
        "| North America |  |  |  |\n"
        "| Net sales | $315,880 | $352,828 | $387,497 |\n"
    )
    assert "| International |  |  |  |\n| Net sales | $118,007 |" in table


def test_one_header_over_two_figures_becomes_two_columns(filing_root):
    # NVIDIA prints an amount and its percentage under each year.
    tables = _tables(filing_root, "nvda_2024_income_taxes.htm")
    reconciliation = next(
        table for table in tables if "federal statutory rate" in table
    )

    assert reconciliation.startswith("(In millions, except percentages)\n")
    assert (
        "| Income tax expense (benefit) | $4,058 | 12.0% | $(187) | (4.5)% | $189 | 1.9% |"
        in reconciliation
    )


def test_a_table_without_figures_is_text(filing_markdown):
    # The cover's securities table holds no figures, so it is layout: one
    # line of text per row.
    blocks = filing_markdown("aapl_2024_front.htm").split("\n\n")

    assert (
        "Common Stock, $0.00001 par value per share AAPL The Nasdaq Stock Market LLC"
        in blocks
    )
