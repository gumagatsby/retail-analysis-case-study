# Decisions

How the data was cleaned and analysed, and why. Every rule here is in `sql/` or `analysis/run.py`, and every rule that removes data has a test in `tests/test_data.py`.

## Tools

| Need | Choice | Why |
|---|---|---|
| Querying a million rows on a laptop | DuckDB, plain SQL files | Fast enough to rebuild everything in seconds; the rules can be read as SQL |
| Statistics and charts | pandas, SciPy, statsmodels, matplotlib | The standard Python stack |
| The owners' report | Power BI Desktop | What most UK data analyst job adverts ask for. It runs only on Windows, so it was built on a short-lived Windows machine in AWS |
| The Windows machine | EC2 m7i-flex.large, Windows Server 2022, London | The account's Free plan refused a t3.xlarge; this type is allowed and has 8 GiB of memory, enough for Desktop with this data. $0.198 an hour, deleted as soon as the files were saved |
| Checks | pytest on the full dataset, ruff | Every cleaning rule is tested against all 1,067,371 rows |

## Cleaning

Every row in the spreadsheet is given exactly one category, tested in this order. Only `sale` and `cancellation` rows are product transactions.

| Category | Rows | Rule | Why |
|---|---|---|---|
| `overlap_duplicate` | 22,523 | Rows in the first sheet dated 1 to 9 December 2010 | Both sheets contain those nine days, row for row. Counting both would add nine days of December twice. The test proves the copies are identical |
| `accounting_adjustment` | 6 | Invoice starts with A | Bad debt write-offs, not orders |
| `non_product` | 5,807 | Postage, carriage, Amazon fees, bank charges, manual adjustments, discounts, samples, test items, gift vouchers | Not merchandise. Amazon fees alone total −£260,764 |
| `cancellation` | 17,974 | Invoice starts with C | Returns and cancelled orders |
| `stock_adjustment` | 3,391 | Negative quantity on an ordinary invoice | Stock written off or corrected. None has a price or a customer |
| `zero_price` | 2,599 | Price of zero | Free items and notes such as "update" or "ebay" |
| `sale` | 1,015,071 | Everything else | |

Stock codes are trimmed first: one code appears with a trailing space.

### Corrections that aren't real sales

Two kinds of sale line are kept in the data but left out of the analysis.

**Voided lines: 1,318 lines, £349,825.** A sale reversed in full by the same customer within 24 hours, for the same product, quantity and price. These are corrections. The largest are 80,995 paper craft birds (£168,470) cancelled 12 minutes after the order, and 74,215 ceramic storage jars (£77,184) cancelled after 16 minutes. Counting them as sales and their cancellations as returns would inflate both. Each cancellation is paired with one sale at most.

**Price errors: 4 lines, £41,644.** A unit price more than 20 times the product's median, on a line worth £500 or more. This catches a small wicker picnic basket keyed at £649.50 instead of £4.95 (60 of them, £38,970; the cancellation that followed used £4.95), and a 42p car flag entered at £867.79 and £1,157.15. A looser rule, 10 times the median, also caught "assorted" products that are sometimes sold by the box, which are real prices. So the rule stays narrow.

### What was kept

**Repeated identical lines.** 11,695 lines repeat another line on the same invoice exactly. The usual approach is to drop them as duplicates. Here they look real: the till routinely puts one product on several lines of an invoice (11,038 product-and-invoice pairs have lines with *different* quantities), so an identical repeat is most likely a second scan of the same quantity. They're kept. Dropping them would change revenue by £56,911, 0.3%, so no finding depends on this choice.

**Orders without a customer number.** 22.4% of sale lines, 13.3% of revenue. They count towards revenue, products and seasons, but can't be used for anything about customers.

## Analysis choices

### Which customers are new

The data starts on 1 December 2009, so a customer's first order *in the data* isn't necessarily their first order. In early 2010 many "new" customers are long-standing ones who simply hadn't ordered in December. Only customers first seen in December 2010 or later have a full year of history behind them, so only they are treated as new. Comparing 2010's "new customers" with 2011's would show a fall in acquisition that is mostly this effect.

### Customer segments

Each customer is scored 1 to 5 on recency (days since the last order), frequency (number of orders) and spend, by quintile, as of 10 December 2011. Five plain segments are built from recency and frequency: best customers, loyal, recent with few orders, former regulars, and lapsed.

### The significance test

*Do overseas customers place larger orders?* Orders from the same customer aren't independent, so the test compares customers, using each customer's median order value. Order values are heavily skewed, so it uses the Mann-Whitney U test rather than a t-test, and a bootstrap (5,000 resamples) for the interval on the difference in medians.

### The forecast

With only two years of months, there's one full seasonal cycle to learn from, so anything elaborate would be guesswork. Two simple methods were scored on the last six full months (June to November 2011), using only data from before June: "the same month a year earlier", and the same scaled by the recent year-on-year trend. The simpler one won.

### Products bought together

Pairs of products on the same invoice, among products on at least 200 invoices and pairs on at least 100, scored by lift: how much more often the pair appears than if the two were bought independently.
