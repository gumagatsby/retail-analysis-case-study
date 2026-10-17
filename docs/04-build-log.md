# Build log

Everything that went wrong or surprised me, in the order it happened, and what I did about it.

## Setting up

### pip stalled for ten minutes

Installing the libraries hung with no output and almost no CPU use. I stopped it, installed one package with a network timeout and visible progress, and it went through at once. The rest followed the same way. Every version is pinned in `requirements.txt`.

### Reading the workbook without guessing

The workbook is 45 MB of Excel with two sheets. pandas guesses each column's type as it reads, and a guessed type can quietly turn a customer number into a decimal or an invoice like `C489449` into a missing value. So everything is read as text, the two sheets are stacked with the sheet name and Excel row number kept, and types are applied in SQL where the rules can be read. The workbook's checksum is checked on every run, so a changed file can't slip through.

## Profiling

### The two sheets overlap

The first sheet runs to 9 December 2010; the second starts on 1 December 2010. All 22,523 rows from those nine days appear in both, identically. Stacking the sheets, the obvious first step, would have counted them twice. A test now proves every removed row has an identical copy in the second sheet.

### Duplicates that probably aren't

There are exact repeated lines on the same invoice, and the usual cleaning step drops them. Before doing that I checked how the till records a basket. 11,038 product-and-invoice pairs have several lines with *different* quantities (one candle, then three, then one more), so the till adds a line per scan. An identical repeat is most likely a second scan of the same quantity. I kept them and measured the effect of dropping them instead: £56,911, 0.3% of revenue.

### Keying errors worth £390,000

The two largest orders in the data, 80,995 paper birds and 74,215 storage jars, were each cancelled within 16 minutes. Treated as a sale and a return, they would inflate both. I matched every cancellation to a sale by the same customer, for the same product, quantity and price, within 24 hours, one to one: 1,318 lines, £349,825.

That rule missed a £38,970 order for 60 picnic baskets, because the cancellation used a different price. The basket had been keyed at £649.50 instead of £4.95. A general rule (10 times the product's median price) caught it but also caught products sold by the box at real prices, so I narrowed it to 20 times the median on lines over £500. It catches 4 lines, and the test names them.

### Stock codes with spaces

One product code appears as both `47503J` and `47503J `. Codes are trimmed before anything else.

## Analysis

### "New" customers who weren't new

The first cohort table showed 951 new customers in December 2009 and several hundred a month through early 2010, then about a hundred a month in 2011. That looked like acquisition collapsing. It's the start of the data: in early 2010, a customer who hadn't ordered since November 2009 shows up as new. Only customers first seen from December 2010 have a year of history behind them, so only they are counted as new.

### A partial month in the retention chart

The first heatmap's last diagonal fell sharply. Those cells were December 2011, which stops on the 9th. Partial months are now left blank.

### The better-looking forecast did worse

Scaling "same month last year" by the recent trend sounds smarter. Tested on June to November 2011, it was out by 9.7% in an average month against 5.6% for the plain version, because the first half of 2011 ran below 2010 and the autumn ran above it. The write-up uses the plain one and says why.

### Overstating the basket finding

My first draft said all 50 top product pairs were "two versions of the same product". Reading the list again, some are matching items from one range: a children's bowl and cup, paper cups and plates. The claim now says "two items from the same range".

### A forecast chart showing the wrong model

The chart first plotted the trend-scaled forecast, the one the text rejects. It now plots the method the text recommends.

### The same analysis gave a different interval

CI re-runs the analysis and fails if any figure differs from the committed one. The first time I ran that check locally, the bootstrap interval for overseas order values moved by about £1. The random seed was fixed, but DuckDB returns rows in no guaranteed order unless asked, so the resampling drew from a differently ordered list each time. Every query that feeds a figure now has an `ORDER BY`. One of them also picked an arbitrary country for customers who ordered from two; it now uses each customer's main country. Two runs now match to the last digit.
