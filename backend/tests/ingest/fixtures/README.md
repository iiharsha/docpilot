# Ingestion fixtures

Whole printed pages from the corpus's 10-K filings, cut out byte for byte. Tests
written against hand-made HTML would test our assumptions about EDGAR's markup,
not the markup. SEC EDGAR filings are public domain.

Each file keeps the source's `<?xml>` prolog, `<html>` tag (with its namespace
declarations) and `<head>`, then the listed pages cut at their page-break
`<hr>`s. `aapl_2024_front.htm` also keeps the hidden `ix:header`, reduced to its
`ix:hidden` facts, which is where `dei:DocumentFiscalYearFocus` lives.

| Fixture | Filing | Printed pages | Exercises |
|---|---|---|---|
| `aapl_2024_front.htm` | Apple FY2024, [0000320193-24-000123](https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/aapl-20240928.htm) | cover, contents, 1 | cover-page metadata, unlabeled pages, a contents page that lists every Item |
| `aapl_2024_net_sales.htm` | Apple FY2024, same | 22–23 | Workiva tables: `$` and `%` in cells of their own; "net sales by category" (brief question 1) |
| `amzn_2024_segments.htm` | Amazon FY2024, [0001018724-25-000004](https://www.sec.gov/Archives/edgar/data/1018724/000101872425000004/amzn-20241231.htm) | 66 | group labels in a table; segment operating income (brief question 2) |
| `googl_2024_risk_factors.htm` | Alphabet FY2024, [0001652044-25-000014](https://www.sec.gov/Archives/edgar/data/1652044/000165204425000014/goog-20241231.htm) | 10–11 | "10." footers, a running header laid out as a table, a sentence cut by a page break, "ITEM 1A.RISK FACTORS" |
| `msft_2024_item_7a.htm` | Microsoft FY2024, [0000950170-24-087843](https://www.sec.gov/Archives/edgar/data/789019/000095017024087843/msft-20240630.htm) | 54–55 | "PART II / Item 7A" running headers, DFIN's `(9,605` \| `)` cells |
| `msft_2024_part_iii.htm` | Microsoft FY2024, same | 101 | the "PART II, III / Item 9B, 9C, 10" running header over three real headings |
| `nvda_2024_income_taxes.htm` | NVIDIA FY2024, [0001045810-24-000029](https://www.sec.gov/Archives/edgar/data/1045810/000104581024000029/nvda-20240128.htm) | 75 | the "(Continued)" statement header, units rows, one header over an amount and its percentage |
