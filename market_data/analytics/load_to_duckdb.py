"""
Loads parsed_financials.csv into the existing GEIF DuckDB warehouse
(analytics.duckdb) as a new table: market_financials.

This is the SAME database file Superset is already connected to
(duckdb:////app/geif_warehouse/analytics.duckdb) — once this runs, the
table appears automatically as a new dataset option in Superset, no new
connection needed.

IMPORTANT: run this with Docker stopped (docker compose down first), since
DuckDB doesn't handle a second process writing to the file while Superset's
container has it open. Restart Docker after this finishes.

Requires: pip install duckdb pandas
"""

import duckdb
import pandas as pd
from pathlib import Path

# Adjust this if your analytics.duckdb lives somewhere else
DUCKDB_PATH = Path("../../data_engineering/analytics.duckdb")
CSV_PATH = Path("parsed_financials.csv")  # run from market_data/scraper/

# Bank/year rows known to be false positives despite passing the automated
# balance_check (caught by manual review) — excluded from the "validated"
# flag so Superset charts don't accidentally include bad data.
KNOWN_FALSE_POSITIVES = {
    ("ATTIJARIWAFA_BANK_2023.pdf"),
    ("BMCI_2023.pdf"),
    ("CDG_capital_2022.pdf"),  # scale inconsistent with 2020/2021
}


def clean_bank_name(filename):
    """Extract a readable bank name from the filename."""
    name = filename.replace(".pdf", "")
    # strip trailing _YYYY year suffix
    parts = name.rsplit("_", 1)
    base = parts[0] if len(parts) == 2 and parts[1].isdigit() else name
    return base.replace("_", " ").title()


def extract_year(filename):
    name = filename.replace(".pdf", "")
    parts = name.rsplit("_", 1)
    if len(parts) == 2 and parts[1].isdigit():
        return int(parts[1])
    return None


def main():
    if not CSV_PATH.exists():
        print(f"ERROR: {CSV_PATH} not found. Run this from market_data/scraper/.")
        return
    if not DUCKDB_PATH.exists():
        print(f"ERROR: {DUCKDB_PATH} not found. Check the path or build it first "
              f"with build_analytics_duckdb.py.")
        return

    df = pd.read_csv(CSV_PATH)

    df["bank"] = df["file"].apply(clean_bank_name)
    df["year"] = df["file"].apply(extract_year)

    df["validated"] = (
        (df["balance_check"] == "OK")
        & (~df["file"].isin(KNOWN_FALSE_POSITIVES))
    )

    # keep only the columns Superset actually needs for charting
    out = df[[
        "bank", "year", "file", "validated", "balance_check", "scale_note",
        "total_actif_current", "total_actif_previous",
        "total_passif_current", "total_passif_previous",
        "produit_net_bancaire_current", "produit_net_bancaire_previous",
        "resultat_net_current", "resultat_net_previous",
    ]].copy()

    con = duckdb.connect(str(DUCKDB_PATH))
    con.execute("CREATE OR REPLACE TABLE market_financials AS SELECT * FROM out")
    row_count = con.execute("SELECT COUNT(*) FROM market_financials").fetchone()[0]
    validated_count = con.execute(
        "SELECT COUNT(*) FROM market_financials WHERE validated = true"
    ).fetchone()[0]
    con.close()

    print(f"Loaded {row_count} rows into market_financials ({validated_count} validated).")
    print(f"Table is now in: {DUCKDB_PATH}")
    print("Restart Docker (docker compose up -d), then add 'market_financials' "
          "as a new dataset in Superset.")


if __name__ == "__main__":
    main()
