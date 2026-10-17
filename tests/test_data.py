"""Every rule in sql/ checked against the full dataset."""

RAW_ROWS = 1_067_371  # as published by UCI


def one(con, sql):
    return con.sql(sql).fetchone()[0]


def test_every_raw_row_has_exactly_one_category(con):
    assert one(con, "select count(*) from read_parquet('data/raw/online_retail_ii.parquet')") == RAW_ROWS
    assert one(con, "select count(*) from lines") == RAW_ROWS
    assert one(con, "select count(*) from lines where category is null") == 0


def test_overlap_rows_are_exact_copies_of_the_second_sheet(con):
    copies = one(con, """
        select count(*) from (
            select invoice, stock_code, description, quantity, invoice_ts, price, customer_id, country
            from lines where category = 'overlap_duplicate'
            except all
            select invoice, stock_code, description, quantity, invoice_ts, price, customer_id, country
            from lines where source_sheet = 'Year 2010-2011')""")
    assert copies == 0
    assert one(con, "select count(*) from lines where category = 'overlap_duplicate'") == 22_523


def test_sales_are_positive_product_lines(con):
    assert one(con, "select count(*) from sales where quantity <= 0 or price <= 0") == 0
    assert one(con, "select count(*) from sales where invoice like 'C%' or invoice like 'A%'") == 0
    assert one(con, "select count(*) from sales where stock_code in ('POST','DOT','M','AMAZONFEE','BANK CHARGES')") == 0


def test_cancellations_are_negative(con):
    assert one(con, "select count(*) from cancellations where quantity >= 0 or invoice not like 'C%'") == 0


def test_each_product_has_one_description(con):
    assert one(con, "select count(*) - count(distinct stock_code) from products") == 0


def test_voids_pair_one_sale_with_one_cancellation(con):
    assert one(con, "select count(*) - count(distinct sale_row) from voids") == 0
    assert one(con, "select count(*) - count(distinct cancel_row) from voids") == 0
    net = one(con, """
        select sum(s.revenue) + sum(c.revenue)
        from voids v join sales s on s.row_id = v.sale_row join cancellations c on c.row_id = v.cancel_row""")
    assert net == 0


def test_known_keying_errors_are_excluded(con):
    # 80,995 paper birds and 74,215 ceramic jars, each cancelled within 20 minutes.
    assert one(con, "select bool_and(voided) from sales where (invoice, stock_code) in (('581483','23843'), ('541431','23166'))")
    # A picnic basket keyed at £649.50; its cancellation used £4.95.
    assert one(con, "select bool_and(price_error) from sales where stock_code = '22502' and price = 649.50")
    assert one(con, "select count(*) from sales where price_error") == 4


def test_customer_and_invoice_totals_match_clean_sales(con):
    clean = one(con, "select sum(revenue) from sales_clean")
    assert one(con, "select sum(revenue) from invoices") == clean
    with_id = one(con, "select sum(revenue) from sales_clean where customer_id is not null")
    assert one(con, "select sum(revenue) from customers") == with_id
