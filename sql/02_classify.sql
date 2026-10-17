-- Every staged row gets exactly one category, tested in order. Only 'sale' and
-- 'cancellation' rows are product transactions; the rest are kept with their reason.
create or replace table lines as
select
    s.*,
    case
        -- Both sheets contain 1 to 9 December 2010, row for row. The second sheet's copy is kept.
        when source_sheet = 'Year 2009-2010' and invoice_ts >= timestamp '2010-12-01'
            then 'overlap_duplicate'
        -- Accounting entries, not orders: bad debt write-offs (invoices starting with A).
        when invoice like 'A%'
            then 'accounting_adjustment'
        -- Fees, postage, discounts, manual corrections, samples, test items and gift vouchers.
        when stock_code in ('ADJUST', 'ADJUST2', 'AMAZONFEE', 'B', 'BANK CHARGES', 'C2', 'C3', 'CRUK',
                            'D', 'DOT', 'GIFT', 'M', 'm', 'POST', 'S', 'TEST001', 'TEST002')
             or stock_code like 'gift\_0001\_%' escape '\'
            then 'non_product'
        -- Returns and cancelled orders (invoices starting with C).
        when invoice like 'C%'
            then 'cancellation'
        -- Stock written off or corrected: negative quantity on an ordinary invoice, never priced.
        when quantity < 0
            then 'stock_adjustment'
        -- Lines with no price: free items, or notes such as 'update' and 'ebay'.
        when price = 0
            then 'zero_price'
        else 'sale'
    end as category
from staging s;
