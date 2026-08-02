"""
GEIF — Entrepôt analytique consolidé pour Apache Superset
================================================================
Regroupe toutes les données du projet dans UN SEUL fichier DuckDB avec de
vraies tables (pas juste des fichiers Parquet bruts), pour que Superset
puisse s'y connecter simplement et proposer des graphiques dessus.

Tables créées :
    - fact_transactions   : les transactions fiscales synthétiques (1M+ lignes)
    - dim_contribuables    : les contribuables synthétiques (dimension)
    - irs_zip_income       : les données réelles IRS SOI (166k lignes)
    - fiscal_timeseries    : l'historique agrégé jour/type d'impôt

Usage :
    python build_analytics_duckdb.py --out ./analytics.duckdb
"""
import argparse
from pathlib import Path

import duckdb


def build_analytics_db(out_path: str, base_dir: str = ".."):
    base = Path(base_dir)
    con = duckdb.connect(out_path)

    fact_path = base / "data" / "processed" / "fact_transactions.parquet"
    if fact_path.exists():
        con.execute(f"CREATE OR REPLACE TABLE fact_transactions AS SELECT * FROM read_parquet('{fact_path}')")
        print(f"✅ fact_transactions chargée depuis {fact_path}")
    else:
        print(f"⚠️ {fact_path} introuvable — lance d'abord generate_large_scale_facts.py")

    warehouse_path = base / "data_engineering" / "fiscal_warehouse.duckdb"
    if warehouse_path.exists():
        con.execute(f"ATTACH '{warehouse_path}' AS wh (READ_ONLY)")
        con.execute("CREATE OR REPLACE TABLE dim_contribuables AS SELECT * FROM wh.contribuables")
        con.execute("DETACH wh")
        print(f"✅ dim_contribuables chargée depuis {warehouse_path}")
    else:
        print(f"⚠️ {warehouse_path} introuvable — lance d'abord build_mock_warehouse.py")

    irs_path = base / "data" / "processed" / "irs_warehouse.duckdb"
    if irs_path.exists():
        con.execute(f"ATTACH '{irs_path}' AS irs (READ_ONLY)")
        con.execute("CREATE OR REPLACE TABLE irs_zip_income AS SELECT * FROM irs.irs_zip_income")
        con.execute("DETACH irs")
        print(f"✅ irs_zip_income chargée depuis {irs_path}")
    else:
        print(f"⚠️ {irs_path} introuvable — lance d'abord load_irs_data.py")

    ts_path = base / "data" / "processed" / "fiscal_timeseries.csv"
    if ts_path.exists():
        con.execute(f"CREATE OR REPLACE TABLE fiscal_timeseries AS SELECT * FROM read_csv_auto('{ts_path}')")
        print(f"✅ fiscal_timeseries chargée depuis {ts_path}")
    else:
        print(f"⚠️ {ts_path} introuvable — lance d'abord generate_fiscal_timeseries.py")

    tables = con.execute("SHOW TABLES").fetchdf()
    con.close()
    print(f"\n✅ Entrepôt analytique créé : {out_path}")
    print(f"Tables disponibles :\n{tables.to_string()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="./analytics.duckdb")
    parser.add_argument("--base-dir", default="..")
    args = parser.parse_args()
    build_analytics_db(args.out, args.base_dir)
