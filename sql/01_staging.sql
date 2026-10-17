-- Typed copy of the workbook, one row per row in Excel. Nothing is removed here.
-- Stock codes are trimmed (one code, 47503J, appears with a trailing space).
create or replace table staging as
select
    row_number() over (order by source_sheet, source_row)   as row_id,
    source_sheet,
    source_row,
    trim(Invoice)                                            as invoice,
    trim(StockCode)                                          as stock_code,
    nullif(trim(Description), '')                            as description,
    cast(Quantity as integer)                                as quantity,
    cast(InvoiceDate as timestamp)                           as invoice_ts,
    cast(Price as decimal(12, 2))                            as price,
    cast(cast("Customer ID" as double) as integer)           as customer_id,
    trim(Country)                                            as country
from read_parquet('data/raw/online_retail_ii.parquet');
