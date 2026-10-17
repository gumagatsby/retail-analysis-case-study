-- The analysis tables. Revenue is quantity x unit price, in pounds sterling.

-- One description per product: the one used most often, so renamed items keep one name.
create or replace table products as
select stock_code, arg_max(description, n) as description
from (
    select stock_code, description, count(*) as n
    from lines
    where category in ('sale', 'cancellation') and description is not null
    group by all
)
group by stock_code;

create or replace table sales as
select
    l.row_id, l.invoice, l.invoice_ts, cast(l.invoice_ts as date) as invoice_date,
    date_trunc('month', l.invoice_ts)::date as month,
    l.stock_code, p.description, l.quantity, l.price,
    l.quantity * l.price as revenue,
    l.customer_id, l.country
from lines l left join products p using (stock_code)
where l.category = 'sale';

create or replace table cancellations as
select
    l.row_id, l.invoice, l.invoice_ts, cast(l.invoice_ts as date) as invoice_date,
    date_trunc('month', l.invoice_ts)::date as month,
    l.stock_code, p.description, l.quantity, l.price,
    l.quantity * l.price as revenue,  -- negative
    l.customer_id, l.country
from lines l left join products p using (stock_code)
where l.category = 'cancellation';

-- Voided lines: a sale reversed in full by the same customer within 24 hours (same product,
-- quantity and price). These are corrections, such as the 80,995 paper birds keyed and
-- cancelled 12 minutes later, not purchases followed by a return. Paired one to one.
create or replace table voids as
with pairs as (
    select s.row_id as sale_row, c.row_id as cancel_row, s.invoice_ts as sale_ts, c.invoice_ts as cancel_ts
    from sales s
    join cancellations c
      on c.customer_id = s.customer_id and c.stock_code = s.stock_code
     and c.quantity = -s.quantity and c.price = s.price
     and c.invoice_ts >= s.invoice_ts and c.invoice_ts <= s.invoice_ts + interval 24 hour
),
latest_sale as (
    select * from pairs qualify row_number() over (partition by cancel_row order by sale_ts desc, sale_row desc) = 1
)
select sale_row, cancel_row from latest_sale
qualify row_number() over (partition by sale_row order by cancel_ts, cancel_row) = 1;

alter table sales add column voided boolean;
update sales set voided = row_id in (select sale_row from voids);
alter table cancellations add column voids_sale boolean;
update cancellations set voids_sale = row_id in (select cancel_row from voids);

-- Price errors: a unit price more than 20 times the product's median, on a line worth £500 or
-- more. Catches four lines: a small picnic basket keyed at £649.50 instead of £4.95 (the
-- cancellation that followed used £4.95), and a 42p car flag entered at £867.79 and £1,157.15.
alter table sales add column price_error boolean;
update sales set price_error = false;
update sales set price_error = true
where row_id in (
    select s.row_id
    from sales s
    join (select stock_code, median(price) as med, count(*) as n from sales group by 1) m using (stock_code)
    where m.n >= 5 and s.price > 20 * m.med and s.revenue >= 500
);

-- What the analysis uses: sales that were neither voided nor mispriced.
create or replace view sales_clean as
select * exclude (voided, price_error) from sales where not voided and not price_error;

-- Returns: cancellations that are not the other half of a voided line.
create or replace view product_returns as
select * exclude (voids_sale) from cancellations where not voids_sale;

create or replace table invoices as
select
    invoice, min(invoice_ts) as invoice_ts, any_value(customer_id) as customer_id,
    any_value(country) as country, count(*) as lines, sum(quantity) as units, sum(revenue) as revenue
from sales_clean
group by invoice;

-- Customers with an ID only. Their country is the one most of their orders came from.
create or replace table customers as
select
    customer_id,
    arg_max(country, n_country) as country,
    min(first_ts) as first_ts, max(last_ts) as last_ts,
    sum(orders) as orders, sum(revenue) as revenue
from (
    select customer_id, country, count(*) as n_country,
           min(invoice_ts) as first_ts, max(invoice_ts) as last_ts,
           count(*) as orders, sum(revenue) as revenue
    from invoices
    where customer_id is not null
    group by all
)
group by customer_id;

