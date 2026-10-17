# Brief: two years of a UK online retailer's sales

*The data is real. It was published by the UCI Machine Learning Repository and covers every transaction of an anonymous UK online retailer from December 2009 to December 2011. The questions are the ones its owners would ask; nobody from the business commissioned this.*

## Background

The retailer sells gift-ware online: candle holders, cake stands, bunting, Christmas decorations. It has no shops. Many of its customers are small businesses that buy to resell, so orders are larger than a typical consumer's. It sells to 43 countries from the UK.

Its records are one spreadsheet: a line per product per invoice, with quantity, price, date, customer number and country. The owners have never had it analysed.

## Dataset

| | |
|---|---|
| Source | Chen, D. (2012). Online Retail II [Dataset]. UCI Machine Learning Repository. https://doi.org/10.24432/C5CG6D |
| Licence | Creative Commons Attribution 4.0 |
| Rows | 1,067,371, in two sheets: December 2009 to December 2010, and December 2010 to December 2011 |
| Columns | Invoice, StockCode, Description, Quantity, InvoiceDate, Price, Customer ID, Country |

## Questions

| # | Question | Who asks it |
|---|---|---|
| Q1 | How much is lost to returns, and which products cause it? | Buying |
| Q2 | Do new customers come back, and how many arrive each month? | Marketing |
| Q3 | Which customers carry the business, and who is drifting away? | Owners, sales |
| Q4 | How much does the year depend on the run-up to Christmas, and can next season be forecast? | Owners, finance |
| Q5 | Which products are bought together? | Buying, web |
| Q6 | Is selling abroad worth it, and do overseas customers behave differently? | Owners |

## What a good answer looks like

1. Each question answered in plain English, with the figure behind it and how sure it is.
2. Every row of the spreadsheet accounted for: kept as a sale, or set aside with a stated reason.
3. Statistics where a claim depends on them, with the method and its assumptions written down.
4. A recommendation for each question that the owners could act on next month.
5. A Power BI report that the owners could open and explore themselves.

## Scope

**In:** cleaning, a small data model, the six questions, one significance test and one forecast where they matter, a Power BI report, and a write-up for non-technical readers.

**Out:** anything needing data the spreadsheet doesn't hold, such as costs, margins, marketing spend or web traffic. Where a recommendation would depend on one of those, the write-up says so.
