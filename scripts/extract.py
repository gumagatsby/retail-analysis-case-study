"""Download Online Retail II from the UCI repository and convert both sheets to one Parquet file.

The workbook is left exactly as published. Every column is read as text, so nothing is
converted silently here; types are applied in sql/01_staging.sql, where the rules can be read.
"""
import hashlib
import sys
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

URL = "https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip"
XLSX_SHA256 = "bcbe73b35f5b7babf197fb0cb983a11f5d9ff929078d4aa53d171b1f2df2e980"
RAW = Path(__file__).resolve().parent.parent / "data" / "raw"


def main() -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    xlsx = RAW / "online_retail_II.xlsx"
    if not xlsx.exists():
        archive = RAW / "online_retail_ii.zip"
        urllib.request.urlretrieve(URL, archive)
        with zipfile.ZipFile(archive) as z:
            z.extract("online_retail_II.xlsx", RAW)
    digest = hashlib.sha256(xlsx.read_bytes()).hexdigest()
    if digest != XLSX_SHA256:
        sys.exit(f"Unexpected workbook checksum {digest}; the published file has changed.")

    frames = []
    for sheet, df in pd.read_excel(xlsx, sheet_name=None, dtype=str).items():
        df.insert(0, "source_sheet", sheet)
        df.insert(1, "source_row", range(2, len(df) + 2))  # the row number as seen in Excel
        frames.append(df)
        print(f"{sheet}: {len(df):,} rows")
    out = pd.concat(frames, ignore_index=True)
    out.to_parquet(RAW / "online_retail_ii.parquet", index=False)
    print(f"total: {len(out):,} rows -> data/raw/online_retail_ii.parquet")


if __name__ == "__main__":
    main()
