"""Build data/retail.duckdb from the raw Parquet file by running the SQL files in order."""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "retail.duckdb"


def build(db_path: Path = DB) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(db_path))
    for sql in sorted((ROOT / "sql").glob("*.sql")):
        con.execute(sql.read_text())
    return con


if __name__ == "__main__":
    import os
    os.chdir(ROOT)
    con = build()
    raw = con.sql("select count(*) from read_parquet('data/raw/online_retail_ii.parquet')").fetchone()[0]
    print(f"raw rows: {raw:,}")
    for cat, n in con.sql("select category, count(*) from lines group by 1 order by 2 desc").fetchall():
        print(f"  {cat:<22}{n:>10,}")
    total = con.sql("select count(*) from lines").fetchone()[0]
    print(f"  {'total':<22}{total:>10,}  {'balanced' if total == raw else 'NOT BALANCED'}")
