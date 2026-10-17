"""Answer the six questions in docs/01-brief.md from data/retail.duckdb.

Writes every figure the write-up quotes to out/metrics.json, the charts to docs/figures/,
and the tables the Power BI report loads to data/powerbi/. Run scripts/build.py first.
"""
import json
from pathlib import Path

import duckdb
import matplotlib
import matplotlib.dates
import numpy as np
import pandas as pd
from scipy import stats

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parent.parent
FIG = ROOT / "docs" / "figures"
OUT = ROOT / "out"
PBI = ROOT / "data" / "powerbi"
AS_OF = pd.Timestamp("2011-12-10")  # the day after the last invoice
RNG = np.random.default_rng(20111209)

INK, MUTE, ACCENT, ACCENT_2, WARN = "#1d2329", "#7a838a", "#0b6e4f", "#8fc1ad", "#b4572e"
plt.rcParams.update({
    "font.family": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 10, "axes.edgecolor": MUTE, "axes.labelcolor": INK, "xtick.color": INK, "ytick.color": INK,
    "axes.spines.top": False, "axes.spines.right": False, "axes.titlesize": 12, "axes.titleweight": "bold",
    "axes.titlelocation": "left", "figure.dpi": 150, "savefig.bbox": "tight",
})


def q(con, sql: str) -> pd.DataFrame:
    return con.sql(sql).df()


def save(fig, name: str) -> None:
    fig.savefig(FIG / f"{name}.png")
    plt.close(fig)


def pounds(ax, axis="y"):
    fmt = matplotlib.ticker.FuncFormatter(lambda v, _: f"£{v / 1e6:.1f}m" if abs(v) >= 1e6 else f"£{v / 1e3:.0f}k")
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(fmt)


# ---------------------------------------------------------------------------------------
def data_quality(con) -> dict:
    cats = q(con, "select category, count(*) as n from lines group by 1 order by 2 desc")
    m = {"raw_rows": int(cats.n.sum()), "categories": dict(zip(cats.category, cats.n.astype(int)))}
    v = con.sql("select count(*), sum(revenue) from sales where voided").fetchone()
    p = con.sql("select count(*), sum(revenue) from sales where price_error").fetchone()
    m["voided_lines"], m["voided_revenue"] = int(v[0]), float(v[1])
    m["price_error_lines"], m["price_error_revenue"] = int(p[0]), float(p[1])
    # Repeated identical lines inside one sheet are kept (the till adds a line per scan).
    # How much they carry, in case a reader would rather drop them:
    rep = con.sql("""
        select count(*), sum(revenue) from (
            select revenue, row_number() over (partition by invoice, stock_code, quantity, price, invoice_ts
                                               order by row_id) as k
            from sales_clean) where k > 1""").fetchone()
    m["repeated_lines"], m["repeated_revenue"] = int(rep[0]), float(rep[1])
    s = con.sql("""select count(*), sum(revenue), count(distinct invoice), count(distinct customer_id),
                          count(*) filter (where customer_id is null),
                          sum(revenue) filter (where customer_id is null)
                   from sales_clean""").fetchone()
    m.update(clean_lines=int(s[0]), gross_revenue=float(s[1]), invoices=int(s[2]), customers=int(s[3]),
             no_customer_lines=int(s[4]), no_customer_revenue=float(s[5]))
    m["repeated_share_of_revenue"] = m["repeated_revenue"] / m["gross_revenue"]
    return m


# ---------------------------------------------------------------------------------------
def returns(con, gross: float) -> dict:
    r = con.sql("select -sum(revenue), count(distinct invoice), count(distinct customer_id) from product_returns").fetchone()
    by_product = q(con, """
        with s as (select stock_code, sum(revenue) as sold, count(distinct invoice) as orders from sales_clean group by 1),
             r as (select stock_code, -sum(revenue) as returned from product_returns group by 1)
        select stock_code, p.description, returned, sold, orders, returned / sold as rate
        from r join s using (stock_code) join products p using (stock_code)
        order by stock_code""")
    top_value = by_product.sort_values("returned", ascending=False, kind="stable").head(10)
    # High-rate products: enough sales that the rate means something.
    high_rate = by_product[(by_product.sold >= 10_000)].sort_values("rate", ascending=False, kind="stable").head(10)
    m = {"returned": float(r[0]), "rate": float(r[0]) / gross, "return_invoices": int(r[1]), "returning_customers": int(r[2]),
         "top_by_value": top_value.round(4).to_dict("records"), "top_by_rate": high_rate.round(4).to_dict("records")}

    fig, ax = plt.subplots(figsize=(8, 4.2))
    d = high_rate.iloc[::-1]
    ax.barh(d.description.str.title(), d.rate * 100, color=[WARN if x > 0.2 else ACCENT_2 for x in d.rate])
    ax.axvline(m["rate"] * 100, color=INK, lw=1, ls="--")
    ax.text(m["rate"] * 100 + 0.4, len(d) - 0.45, f"all products: {m['rate']:.1%}", fontsize=9, color=INK)
    ax.set_xlabel("Share of sales value returned (%)")
    ax.set_title("A few products come back far more often than the rest")
    save(fig, "returns")
    by_product.to_csv(PBI / "returns_by_product.csv", index=False)
    return m


# ---------------------------------------------------------------------------------------
def seasonality_and_forecast(con) -> dict:
    monthly = q(con, """select month, sum(revenue) as revenue, count(distinct invoice) as orders,
                               count(distinct customer_id) as customers
                        from sales_clean group by 1 order by 1""")
    monthly["month"] = pd.to_datetime(monthly.month)
    full = monthly[monthly.month < "2011-12-01"].copy()  # December 2011 stops on the 9th
    full["year"] = np.where(full.month < "2010-12-01", "Dec 2009 to Nov 2010", "Dec 2010 to Nov 2011")
    yr = full.groupby("year").agg(revenue=("revenue", "sum"), orders=("orders", "sum")).reset_index()
    yr["aov"] = yr.revenue / yr.orders
    q4 = full[full.month.dt.month.isin([9, 10, 11])].groupby("year").revenue.sum() / full.groupby("year").revenue.sum()

    # Forecast June to November 2011 from the months before it, scored against what happened.
    train = full[full.month < "2011-06-01"].set_index("month").revenue
    test = full[full.month >= "2011-06-01"].set_index("month").revenue
    naive = full.set_index("month").revenue.shift(12, freq="MS").reindex(test.index)
    growth = train["2010-12-01":].sum() / train["2009-12-01":"2010-05-01"].sum()  # trailing 6 months on a year earlier
    grown = naive * growth
    mape = lambda f: float((abs(f - test) / test).mean())
    fc = {"holdout": [str(d.date()) for d in test.index], "actual": test.round(0).tolist(),
          "seasonal_naive": naive.round(0).tolist(), "seasonal_naive_growth": grown.round(0).tolist(),
          "growth_factor": float(growth), "mape_seasonal_naive": mape(naive), "mape_seasonal_naive_growth": mape(grown),
          "total_error_naive": float(naive.sum() / test.sum() - 1), "total_error_grown": float(grown.sum() / test.sum() - 1)}

    m = {"years": yr.round(2).to_dict("records"), "sep_nov_share": {k: float(v) for k, v in q4.items()},
         "busiest_month": str(full.loc[full.revenue.idxmax(), "month"].date()),
         "busiest_month_revenue": float(full.revenue.max()), "quietest_month": str(full.loc[full.revenue.idxmin(), "month"].date()),
         "quietest_month_revenue": float(full.revenue.min()), "forecast": fc}

    fig, ax = plt.subplots(figsize=(8.5, 3.8))
    ax.plot(full.month, full.revenue, color=ACCENT, lw=2, marker="o", ms=3)
    ax.plot(test.index, naive, color=WARN, lw=1.5, ls="--", label="Forecast for Jun to Nov 2011: same month a year earlier")
    for y in ("2010", "2011"):
        ax.axvspan(pd.Timestamp(f"{y}-09-01"), pd.Timestamp(f"{y}-11-30"), color=ACCENT_2, alpha=0.18, lw=0)
    pounds(ax)
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%b %Y"))
    ax.set_title("September to November carries more than a third of the year")
    ax.legend(frameon=False, loc="upper left")
    save(fig, "monthly_revenue")
    monthly.to_csv(PBI / "monthly.csv", index=False)
    return m


# ---------------------------------------------------------------------------------------
def customers(con) -> dict:
    cust = q(con, "select * from customers order by revenue desc, customer_id")
    n, tot = len(cust), cust.revenue.sum()
    share = lambda p: float(cust.revenue.head(round(n * p)).sum() / tot)
    m = {"customers": n, "top1_share": share(0.01), "top10_share": share(0.10), "top20_share": share(0.20),
         "one_order_share": float((cust.orders == 1).mean()), "median_orders": float(cust.orders.median()),
         "median_revenue": float(cust.revenue.median())}

    # RFM, scored 1 to 5 by quintile, as of the day after the last invoice.
    cust["recency_days"] = (AS_OF - pd.to_datetime(cust.last_ts)).dt.days
    cust["r"] = pd.qcut(cust.recency_days.rank(method="first"), 5, labels=[5, 4, 3, 2, 1]).astype(int)
    cust["f"] = pd.qcut(cust.orders.rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)
    cust["m"] = pd.qcut(cust.revenue.rank(method="first"), 5, labels=[1, 2, 3, 4, 5]).astype(int)

    def segment(row):
        if row.r >= 4 and row.f >= 4:
            return "Best customers"
        if row.r >= 3 and row.f >= 3:
            return "Loyal"
        if row.r >= 4 and row.f <= 2:
            return "Recent, few orders"
        if row.r <= 2 and row.f >= 3:
            return "Former regulars"
        return "Lapsed"
    cust["segment"] = cust.apply(segment, axis=1)
    seg = cust.groupby("segment").agg(customers=("customer_id", "count"), revenue=("revenue", "sum"),
                                      median_recency_days=("recency_days", "median")).reset_index()
    seg["revenue_share"] = seg.revenue / tot
    seg["customer_share"] = seg.customers / n
    m["segments"] = seg.sort_values("revenue", ascending=False).round(4).to_dict("records")
    slipping = cust[cust.segment == "Former regulars"]
    m["slipping_revenue_two_years"] = float(slipping.revenue.sum())

    fig, ax = plt.subplots(figsize=(6.5, 4))
    x = np.arange(1, n + 1) / n * 100
    ax.plot(x, cust.revenue.cumsum() / tot * 100, color=ACCENT, lw=2)
    ax.plot([0, 100], [0, 100], color=MUTE, lw=1, ls=":")
    for p, s in ((10, m["top10_share"]), (20, m["top20_share"])):
        ax.plot([p], [s * 100], "o", color=INK, ms=4)
        ax.annotate(f"top {p}%: {s:.0%} of revenue", (p, s * 100), xytext=(p + 6, s * 100 - 8), fontsize=9)
    ax.set_xlabel("Customers, largest first (%)")
    ax.set_ylabel("Share of revenue (%)")
    ax.set_title("A small group of customers carries most of the revenue")
    save(fig, "concentration")
    cust.drop(columns=["first_ts", "last_ts"]).assign(
        first_order=pd.to_datetime(cust.first_ts).dt.date, last_order=pd.to_datetime(cust.last_ts).dt.date
    ).to_csv(PBI / "customers.csv", index=False)
    return m


# ---------------------------------------------------------------------------------------
def cohorts(con) -> dict:
    act = q(con, "select distinct customer_id, month from sales_clean where customer_id is not null order by 1, 2")
    act["month"] = pd.to_datetime(act.month)
    first = act.groupby("customer_id").month.min().rename("cohort")
    act = act.join(first, on="customer_id")
    act["k"] = (act.month.dt.year - act.cohort.dt.year) * 12 + (act.month.dt.month - act.cohort.dt.month)
    size = first.value_counts().sort_index()
    table = act.groupby(["cohort", "k"]).customer_id.nunique().unstack(fill_value=0)
    rate = table.div(size, axis=0)

    # Customers first seen in December 2010 or later have at least a year of history behind them,
    # so they really are new. Earlier "new" customers include existing ones who hadn't ordered yet.
    reliable = size[size.index >= "2010-12-01"]
    reliable = reliable[reliable.index <= "2011-11-01"]
    any3 = act[(act.k >= 1) & (act.k <= 3)].groupby("cohort").customer_id.nunique().reindex(size.index, fill_value=0) / size
    eligible = any3[(any3.index >= "2010-12-01") & (any3.index <= "2011-08-01")]
    m = {"new_customers_per_month_from_dec_2010": {str(k.date()): int(v) for k, v in reliable.items()},
         "median_new_per_month_jan_to_nov_2011": float(reliable["2011-01-01":].median()),
         "retained_within_3_months": {str(k.date()): round(float(v), 4) for k, v in eligible.items()},
         "dec_2009_cohort_size": int(size.iloc[0])}
    newc = first[first >= "2010-12-01"].index
    new3 = act[act.customer_id.isin(newc) & (act.k >= 1) & (act.k <= 3) & (act.cohort <= "2011-08-01")].customer_id.nunique()
    base = int((first[(first >= "2010-12-01") & (first <= "2011-08-01")]).size)
    m["new_customers_dec10_aug11"], m["came_back_within_3_months"] = base, int(new3)
    lo, hi = stats.binomtest(new3, base).proportion_ci(0.95, method="wilson")
    m["came_back_rate"], m["came_back_ci95"] = new3 / base, [float(lo), float(hi)]

    fig, ax = plt.subplots(figsize=(8.5, 4.6))
    shown = rate.loc["2010-12-01":"2011-11-01", 1:11] * 100
    # Only complete months: December 2011 stops on the 9th, so later cells are left blank.
    for i, d in enumerate(shown.index):
        for j, k in enumerate(shown.columns):
            if d + pd.DateOffset(months=int(k)) >= pd.Timestamp("2011-12-01"):
                shown.iloc[i, j] = np.nan
    cmap = matplotlib.colormaps["Greens"].copy()
    cmap.set_bad("white")
    im = ax.imshow(np.ma.masked_invalid(shown.values), cmap=cmap, vmin=0, vmax=50, aspect="auto")
    ax.set_yticks(range(len(shown)), [d.strftime("%b %Y") + f"  ({size[d]})" for d in shown.index])
    ax.set_xticks(range(shown.shape[1]), [str(c) for c in shown.columns])
    for (i, j), v in np.ndenumerate(shown.values):
        if not np.isnan(v):
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=7, color=INK if v < 35 else "white")
    ax.set_xlabel("Months after the first order (complete months only)")
    ax.set_title("Share of new customers ordering again, by month of first order (%)")
    fig.colorbar(im, ax=ax, shrink=0.7)
    save(fig, "cohorts")
    rate.reset_index().melt(id_vars="cohort", var_name="months_after", value_name="share_ordering").to_csv(
        PBI / "cohorts.csv", index=False)
    return m


# ---------------------------------------------------------------------------------------
def baskets(con) -> dict:
    con.execute("create or replace temp table ip as select distinct invoice, stock_code from sales_clean")
    con.execute("create or replace temp table pc as select stock_code, count(*) as n from ip group by 1")
    n = con.sql("select count(distinct invoice) from ip").fetchone()[0]
    pairs = q(con, f"""
        with p as (
            select a.stock_code as a, b.stock_code as b, count(*) as together
            from ip a join ip b on a.invoice = b.invoice and a.stock_code < b.stock_code
            where a.stock_code in (select stock_code from pc where n >= 200)
              and b.stock_code in (select stock_code from pc where n >= 200)
            group by 1, 2 having count(*) >= 100)
        select pa.description as product_a, pb.description as product_b, together,
               together / ca.n as share_of_a_orders, together / cb.n as share_of_b_orders,
               together * {n}::double / (ca.n * cb.n) as lift,
               split_part(pa.description, ' ', 1) = split_part(pb.description, ' ', 1)
                 or split_part(pa.description, ' ', 2) = split_part(pb.description, ' ', 2)
                 or left(a, 4) = left(b, 4) as same_range
        from p join pc ca on ca.stock_code = a join pc cb on cb.stock_code = b
               join products pa on pa.stock_code = a join products pb on pb.stock_code = b
        order by lift desc, product_a, product_b""")
    m = {"invoices": int(n), "pairs_considered": len(pairs),
         "same_range_share_of_top50": float(pairs.head(50).same_range.mean()),
         "top_same_range": pairs[pairs.same_range].head(8).round(3).to_dict("records"),
         "top_cross_range": pairs[~pairs.same_range].head(8).round(3).to_dict("records")}
    pairs.to_csv(PBI / "product_pairs.csv", index=False)
    return m


# ---------------------------------------------------------------------------------------
def markets(con) -> dict:
    countries = q(con, """select country, sum(revenue) as revenue, count(distinct customer_id) as customers,
                                 count(distinct invoice) as orders
                          from sales_clean group by 1 order by 2 desc, 1""")
    tot = countries.revenue.sum()
    uk = countries[countries.country == "United Kingdom"].iloc[0]
    intl = countries[countries.country != "United Kingdom"]
    m = {"uk_revenue_share": float(uk.revenue / tot), "international_revenue": float(intl.revenue.sum()),
         "countries": len(countries), "top_international": intl.head(6).round(2).to_dict("records")}

    # Is a typical international order bigger than a typical UK one? Orders from one customer are
    # not independent, so the test compares customers: each customer's median order value.
    per_cust = q(con, """select i.customer_id, c.country, median(i.revenue) as median_order
                         from invoices i join customers c using (customer_id)
                         group by 1, 2 order by 1""")
    per_cust["intl"] = per_cust.country != "United Kingdom"
    a, b = per_cust[per_cust.intl].median_order.values, per_cust[~per_cust.intl].median_order.values
    u = stats.mannwhitneyu(a, b, alternative="two-sided")
    boot = [np.median(RNG.choice(a, a.size)) - np.median(RNG.choice(b, b.size)) for _ in range(5000)]
    m["order_value_test"] = {
        "international_customers": int(a.size), "uk_customers": int(b.size),
        "median_international": float(np.median(a)), "median_uk": float(np.median(b)),
        "difference": float(np.median(a) - np.median(b)), "ci95": [float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))],
        "mann_whitney_u": float(u.statistic), "p_value": float(u.pvalue),
        "prob_international_larger": float(u.statistic / (a.size * b.size)),
    }

    fig, ax = plt.subplots(figsize=(6.5, 3.6))
    bins = np.logspace(1, 4.3, 40)
    ax.hist(b, bins=bins, color=ACCENT_2, label=f"UK customers ({b.size:,})", density=True)
    ax.hist(a, bins=bins, color=ACCENT, alpha=0.75, label=f"International customers ({a.size:,})", density=True)
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"£{v:,.0f}"))
    ax.set_yticks([])
    ax.set_xlabel("Each customer's typical (median) order value")
    ax.set_title("International customers place larger orders")
    ax.legend(frameon=False)
    save(fig, "order_value")
    countries.to_csv(PBI / "countries.csv", index=False)
    return m


def main() -> None:
    for d in (FIG, OUT, PBI):
        d.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(ROOT / "data" / "retail.duckdb"), read_only=True)
    metrics = {"data_quality": data_quality(con)}
    gross = metrics["data_quality"]["gross_revenue"]
    metrics["returns"] = returns(con, gross)
    metrics["seasonality"] = seasonality_and_forecast(con)
    metrics["customers"] = customers(con)
    metrics["cohorts"] = cohorts(con)
    metrics["baskets"] = baskets(con)
    metrics["markets"] = markets(con)
    q(con, """select invoice, invoice_date, month, stock_code, description, quantity, price, revenue, customer_id, country
              from sales_clean order by row_id""").to_parquet(PBI / "sales.parquet", index=False)
    (OUT / "metrics.json").write_text(json.dumps(metrics, indent=2, default=str))
    print(f"wrote out/metrics.json, {len(list(FIG.glob('*.png')))} figures, {len(list(PBI.glob('*')))} Power BI tables")


if __name__ == "__main__":
    main()
