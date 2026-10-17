"""Write the Power BI project (PBIP) for the owners' report.

The project is plain text: the semantic model in TMDL and the report in PBIR JSON, so it can be
reviewed in git. Power BI Desktop opens RetailSales.pbip and loads the files that
analysis/run.py exports to data/powerbi/. Every report file is checked against Microsoft's
published JSON schemas by powerbi/validate.py.
"""
import json
import shutil
from pathlib import Path

HERE = Path(__file__).resolve().parent
NAME = "RetailSales"
MODEL = HERE / f"{NAME}.SemanticModel"
REPORT = HERE / f"{NAME}.Report"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item"

# Where the exported files sit on the Windows machine that opens the project.
DATA_FOLDER = "C:\\retail\\powerbi\\"

T = "\t"


# ----------------------------------------------------------------------------- semantic model
def col(name, source, dtype, fmt=None, summarize="none", sort_by=None):
    lines = [f"{T}column {q(name)}", f"{T}{T}dataType: {dtype}"]
    if fmt:
        lines.append(f"{T}{T}formatString: {fmt}")
    lines += [f"{T}{T}summarizeBy: {summarize}", f"{T}{T}sourceColumn: {source}"]
    if sort_by:
        lines.append(f"{T}{T}sortByColumn: {q(sort_by)}")
    return "\n".join(lines) + "\n"


def measure(name, dax, fmt):
    return f"{T}measure {q(name)} = {dax}\n{T}{T}formatString: {fmt}\n"


def partition(table, m_lines):
    body = "\n".join(f"{T}{T}{T}{T}{line}" for line in m_lines)
    return f"{T}partition {q(table)} = m\n{T}{T}mode: import\n{T}{T}source =\n{body}\n"


def q(name):
    return f"'{name}'" if any(c in name for c in " .=:'") else name


def csv_source(file, types):
    t = ", ".join(f'{{"{c}", {ty}}}' for c, ty in types)
    return [
        "let",
        f'    Source = Csv.Document(File.Contents(DataFolder & "{file}"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
        "    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
        f'    Typed = Table.TransformColumnTypes(Headers, {{{t}}}, "en-US")',
        "in",
        "    Typed",
    ]


def write_model():
    d = MODEL / "definition"
    (d / "tables").mkdir(parents=True)
    (MODEL / "definition.pbism").write_text(json.dumps(
        {"$schema": f"{SCHEMA}/semanticModel/definitionProperties/1.0.0/schema.json", "version": "4.2", "settings": {}},
        indent=2))
    (d / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1600\n")
    tables = ["Sales", "Customers", "Cohorts", "Returns by product", "Product pairs"]
    (d / "model.tmdl").write_text(
        "model Model\n\tculture: en-GB\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\tsourceQueryCulture: en-GB\n"
        "\tdataAccessOptions\n\t\tlegacyRedirects\n\t\treturnErrorValuesAsNull\n\n"
        + "".join(f"ref table {q(t)}\n" for t in tables))
    (d / "expressions.tmdl").write_text(
        f'expression DataFolder = "{DATA_FOLDER.replace(chr(92), chr(92))}" '
        'meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]\n')
    (d / "relationships.tmdl").write_text(
        "relationship sales_to_customers\n\tfromColumn: Sales.'Customer ID'\n\ttoColumn: Customers.'Customer ID'\n")

    sales = (
        "table Sales\n\n"
        + measure("Revenue", "SUM(Sales[Line revenue])", "£#,0")
        + "\n" + measure("Orders", "DISTINCTCOUNT(Sales[Invoice])", "#,0")
        + "\n" + measure("Customers with an account", "DISTINCTCOUNTNOBLANK(Sales[Customer ID])", "#,0")
        + "\n" + measure("Average order", "DIVIDE([Revenue], [Orders])", "£#,0.00")
        + "\n" + col("Invoice", "invoice", "string")
        + "\n" + col("Date", "invoice_date", "dateTime", fmt="dd mmm yyyy")
        + "\n" + col("Month", "month", "dateTime", fmt="mmm yyyy")
        + "\n" + col("Stock code", "stock_code", "string")
        + "\n" + col("Product", "description", "string")
        + "\n" + col("Quantity", "quantity", "int64", fmt="#,0", summarize="sum")
        + "\n" + col("Unit price", "price", "decimal", fmt="£#,0.00")
        + "\n" + col("Line revenue", "revenue", "decimal", fmt="£#,0.00", summarize="sum")
        + "\n" + col("Customer ID", "customer_id", "int64", fmt="0")
        + "\n" + col("Country", "country", "string")
        + "\n" + partition("Sales", [
            "let",
            '    Source = Parquet.Document(File.Contents(DataFolder & "sales.parquet")),',
            ('    Typed = Table.TransformColumnTypes(Source, {{"invoice_date", type date}, {"month", type date}, '
            '{"quantity", Int64.Type}, {"price", Currency.Type}, {"revenue", Currency.Type}, {"customer_id", Int64.Type}})'),
            "in",
            "    Typed",
        ])
    )
    customers = (
        "table Customers\n\n"
        + measure("Customer count", "COUNTROWS(Customers)", "#,0")
        + "\n" + measure("Customer revenue", "SUM(Customers[Two-year revenue])", "£#,0")
        + "\n" + measure("Share of customer revenue",
                         "DIVIDE([Customer revenue], CALCULATE([Customer revenue], ALL(Customers)))", "0.0%")
        + "\n" + col("Customer ID", "customer_id", "int64", fmt="0")
        + "\n" + col("Main country", "country", "string")
        + "\n" + col("Orders", "orders", "int64", fmt="#,0", summarize="sum")
        + "\n" + col("Two-year revenue", "revenue", "decimal", fmt="£#,0", summarize="sum")
        + "\n" + col("Days since last order", "recency_days", "int64", fmt="#,0", summarize="average")
        + "\n" + col("Segment", "segment", "string")
        + "\n" + col("First order", "first_order", "dateTime", fmt="dd mmm yyyy")
        + "\n" + col("Last order", "last_order", "dateTime", fmt="dd mmm yyyy")
        + "\n" + partition("Customers", csv_source("customers.csv", [
            ("customer_id", "Int64.Type"), ("country", "type text"), ("orders", "Int64.Type"),
            ("revenue", "Currency.Type"), ("recency_days", "Int64.Type"), ("r", "Int64.Type"), ("f", "Int64.Type"),
            ("m", "Int64.Type"), ("segment", "type text"), ("first_order", "type date"), ("last_order", "type date")]))
    )
    # Only customers with a year of history behind them, and only complete months (December 2011 stops on the 9th).
    cohort_m = [
        "let",
        '    Source = Csv.Document(File.Contents(DataFolder & "cohorts.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
        "    Headers = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
        '    Typed = Table.TransformColumnTypes(Headers, {{"cohort", type date}, {"months_after", Int64.Type}, {"share_ordering", type number}}, "en-US"),',
        "    Reliable = Table.SelectRows(Typed, each [cohort] >= #date(2010, 12, 1) and [months_after] >= 1",
        "        and Date.AddMonths([cohort], [months_after]) < #date(2011, 12, 1))",
        "in",
        "    Reliable",
    ]
    cohorts = (
        "table Cohorts\n\n"
        + measure("Share ordering again", "AVERAGE(Cohorts[Share ordering])", "0%")
        + "\n" + col("First order month", "cohort", "dateTime", fmt="mmm yyyy")
        + "\n" + col("Months after first order", "months_after", "int64", fmt="0")
        + "\n" + col("Share ordering", "share_ordering", "double", fmt="0%", summarize="average")
        + "\n" + partition("Cohorts", cohort_m)
    )
    returns_m = csv_source("returns_by_product.csv", [
        ("stock_code", "type text"), ("description", "type text"), ("returned", "Currency.Type"),
        ("sold", "Currency.Type"), ("orders", "Int64.Type"), ("rate", "type number")])
    returns = (
        "table 'Returns by product'\n\n"
        + measure("Returned", "SUM('Returns by product'[Value returned])", "£#,0")
        + "\n" + measure("Share returned",
                         "DIVIDE([Returned], SUM('Returns by product'[Value sold]))", "0.0%")
        + "\n" + col("Stock code", "stock_code", "string")
        + "\n" + col("Product", "description", "string")
        + "\n" + col("Value returned", "returned", "decimal", fmt="£#,0", summarize="sum")
        + "\n" + col("Value sold", "sold", "decimal", fmt="£#,0", summarize="sum")
        + "\n" + col("Orders", "orders", "int64", fmt="#,0", summarize="sum")
        + "\n" + col("Return rate", "rate", "double", fmt="0.0%", summarize="none")
        + "\n" + partition("Returns by product", returns_m)
    )
    pairs = (
        "table 'Product pairs'\n\n"
        + col("Product A", "product_a", "string")
        + "\n" + col("Product B", "product_b", "string")
        + "\n" + col("Orders with both", "together", "int64", fmt="#,0", summarize="sum")
        + "\n" + col("Share of A's orders with B", "share_of_a_orders", "double", fmt="0%", summarize="none")
        + "\n" + col("Lift", "lift", "double", fmt="0", summarize="none")
        + "\n" + col("Same range", "same_range", "boolean")
        + "\n" + partition("Product pairs", csv_source("product_pairs.csv", [
            ("product_a", "type text"), ("product_b", "type text"), ("together", "Int64.Type"),
            ("share_of_a_orders", "type number"), ("share_of_b_orders", "type number"), ("lift", "type number"),
            ("same_range", "type logical")]))
    )
    for name, text in [("Sales", sales), ("Customers", customers), ("Cohorts", cohorts),
                       ("Returns by product", returns), ("Product pairs", pairs)]:
        (d / "tables" / f"{name}.tmdl").write_text(text)


# ----------------------------------------------------------------------------- report
def lit(value):
    return {"expr": {"Literal": {"Value": value}}}


def column(entity, prop, active=False):
    p = {"field": {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}},
         "queryRef": f"{entity}.{prop}", "nativeQueryRef": prop}
    if active:
        p["active"] = True
    return p


def meas(entity, prop):
    return {"field": {"Measure": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}},
            "queryRef": f"{entity}.{prop}", "nativeQueryRef": prop}


def visual(name, vtype, x, y, w, h, z, roles, title=None, sort=None):
    v = {
        "$schema": f"{SCHEMA}/report/definition/visualContainer/2.6.0/schema.json",
        "name": name,
        "position": {"x": x, "y": y, "z": z, "height": h, "width": w, "tabOrder": z},
        "visual": {"visualType": vtype, "query": {"queryState": {r: {"projections": p} for r, p in roles.items()}},
                   "drillFilterOtherVisuals": True},
    }
    if sort:
        field, direction = sort
        v["visual"]["query"]["sortDefinition"] = {"sort": [{"field": field["field"], "direction": direction}],
                                                  "isDefaultSort": True}
    if title:
        v["visual"]["visualContainerObjects"] = {
            "title": [{"properties": {"show": lit("true"), "text": lit(f"'{title}'")}}]}
    return v


def pages():
    S, C, CO, R, P = "Sales", "Customers", "Cohorts", "Returns by product", "Product pairs"
    overview = [
        visual("overview_revenue", "card", 20, 20, 300, 110, 1, {"Values": [meas(S, "Revenue")]}),
        visual("overview_orders", "card", 335, 20, 300, 110, 2, {"Values": [meas(S, "Orders")]}),
        visual("overview_customers", "card", 650, 20, 300, 110, 3, {"Values": [meas(S, "Customers with an account")]}),
        visual("overview_average_order", "card", 965, 20, 295, 110, 4, {"Values": [meas(S, "Average order")]}),
        visual("overview_by_month", "lineChart", 20, 150, 830, 550, 5,
               {"Category": [column(S, "Month", active=True)], "Y": [meas(S, "Revenue")]},
               title="Revenue by month: September to November carries over a third of the year"),
        visual("overview_by_country", "clusteredBarChart", 870, 150, 390, 460, 6,
               {"Category": [column(S, "Country", active=True)], "Y": [meas(S, "Revenue")]},
               title="Revenue by country", sort=(meas(S, "Revenue"), "Descending")),
        visual("overview_country_slicer", "slicer", 870, 625, 390, 75, 7, {"Values": [column(S, "Country")]}),
    ]
    customers = [
        visual("customers_segments", "clusteredBarChart", 20, 20, 610, 330, 1,
               {"Category": [column(C, "Segment", active=True)], "Y": [meas(C, "Share of customer revenue")]},
               title="Share of revenue by customer segment", sort=(meas(C, "Share of customer revenue"), "Descending")),
        visual("customers_segment_table", "tableEx", 650, 20, 610, 330, 2,
               {"Values": [column(C, "Segment"), meas(C, "Customer count"), meas(C, "Customer revenue"),
                           meas(C, "Share of customer revenue")]},
               title="Segments", sort=(meas(C, "Customer revenue"), "Descending")),
        visual("customers_cohorts", "pivotTable", 20, 370, 1240, 330, 3,
               {"Rows": [column(CO, "First order month")], "Columns": [column(CO, "Months after first order")],
                "Values": [meas(CO, "Share ordering again")]},
               title="New customers ordering again, by month of first order (complete months only)"),
    ]
    products = [
        visual("products_returns", "tableEx", 20, 20, 760, 680, 1,
               {"Values": [column(R, "Product"), column(R, "Value sold"), column(R, "Value returned"),
                           column(R, "Return rate")]},
               title="Returns by product", sort=(column(R, "Value returned"), "Descending")),
        visual("products_pairs", "tableEx", 800, 20, 460, 680, 2,
               {"Values": [column(P, "Product A"), column(P, "Product B"), column(P, "Orders with both"),
                           column(P, "Lift")]},
               title="Products bought together", sort=(column(P, "Lift"), "Descending")),
    ]
    return [("overview", "Overview", overview), ("customers", "Customers", customers),
            ("products", "Products and returns", products)]


def write_report():
    d = REPORT / "definition"
    d.mkdir(parents=True)
    (REPORT / "definition.pbir").write_text(json.dumps({
        "$schema": f"{SCHEMA}/report/definitionProperties/2.0.0/schema.json", "version": "4.0",
        "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}}, indent=2))
    (d / "version.json").write_text(json.dumps({
        "$schema": f"{SCHEMA}/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"}, indent=2))
    theme = "CY26SU02"
    (d / "report.json").write_text(json.dumps({
        "$schema": f"{SCHEMA}/report/definition/report/3.1.0/schema.json",
        "themeCollection": {"baseTheme": {"name": theme, "reportVersionAtImport": {
            "visual": "2.6.0", "report": "3.1.0", "page": "2.3.0"}, "type": "SharedResources"}},
        "resourcePackages": [{"name": "SharedResources", "type": "SharedResources",
                              "items": [{"name": theme, "path": f"BaseThemes/{theme}.json", "type": "BaseTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized",
                     "defaultDrillFilterOtherVisuals": True, "allowChangeFilterTypes": True,
                     "useEnhancedTooltips": True, "useDefaultAggregateDisplayName": True},
    }, indent=2))
    themes = REPORT / "StaticResources" / "SharedResources" / "BaseThemes"
    themes.mkdir(parents=True)
    shutil.copy(HERE / "base-theme" / f"{theme}.json", themes / f"{theme}.json")

    order = []
    for name, display, visuals in pages():
        pd_ = d / "pages" / name
        (pd_ / "visuals").mkdir(parents=True)
        (pd_ / "page.json").write_text(json.dumps({
            "$schema": f"{SCHEMA}/report/definition/page/2.0.0/schema.json", "name": name,
            "displayName": display, "displayOption": "FitToPage", "height": 720, "width": 1280}, indent=2))
        for v in visuals:
            (pd_ / "visuals" / v["name"]).mkdir()
            (pd_ / "visuals" / v["name"] / "visual.json").write_text(json.dumps(v, indent=2))
        order.append(name)
    (d / "pages" / "pages.json").write_text(json.dumps({
        "$schema": f"{SCHEMA}/report/definition/pagesMetadata/1.0.0/schema.json",
        "pageOrder": order, "activePageName": order[0]}, indent=2))


def main():
    for p in (MODEL, REPORT):
        if p.exists():
            shutil.rmtree(p)
    write_model()
    write_report()
    (HERE / f"{NAME}.pbip").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json", "version": "1.0",
        "artifacts": [{"report": {"path": f"{NAME}.Report"}}], "settings": {"enableAutoRecovery": True}}, indent=2))
    print(f"wrote powerbi/{NAME}.pbip")


if __name__ == "__main__":
    main()
