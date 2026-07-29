"""
GEIF — Intégration de données fiscales réelles (IRS SOI, ZIP code data)
============================================================================
Charge le fichier public IRS SOI (Statistics of Income, données de revenu par
ZIP code, USA) dans DuckDB, et entraîne un détecteur d'anomalies (Isolation
Forest) sur des ZIP codes agrégés — pour valider notre méthodologie de
détection d'anomalies fiscales sur de la VRAIE donnée publique, à grande
échelle (166k lignes), en complément de la simulation marocaine.

Colonnes clés du fichier (dictionnaire IRS officiel) :
    STATEFIPS, STATE, zipcode : localisation
    agi_stub                  : tranche de revenu brut ajusté (1=faible ... 6=élevé)
    N1                         : nombre de déclarations
    A00100                     : revenu brut ajusté total (en milliers de $)
    N02650, A02650             : revenu total
    A00200                     : salaires et traitements (montant)
    A19700                     : dons caritatifs déductibles (montant)

Usage :
    python load_irs_data.py --csv ../raw/irs_soi/22zpallagi.csv --duckdb ../processed/irs_warehouse.duckdb
"""
import argparse

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest


def load_csv_to_duckdb(csv_path: str, duckdb_path: str):
    con = duckdb.connect(duckdb_path)
    con.execute(f"""
        CREATE OR REPLACE TABLE irs_zip_income AS
        SELECT * FROM read_csv_auto('{csv_path}', header=True)
    """)
    n_rows = con.execute("SELECT COUNT(*) FROM irs_zip_income").fetchone()[0]
    con.close()
    print(f"✅ {n_rows:,} lignes chargées dans DuckDB ({duckdb_path})")
    return n_rows


def build_zip_features(duckdb_path: str) -> pd.DataFrame:
    """Agrège par ZIP code des ratios financiers pertinents pour détecter des
    profils statistiquement atypiques (proxy simplifié d'un ciblage de contrôle)."""
    con = duckdb.connect(duckdb_path, read_only=True)
    df = con.execute("""
        SELECT
            zipcode,
            STATE,
            SUM(N1)      AS n_declarations,
            SUM(A00100)  AS total_agi,
            SUM(A00200)  AS total_salaires,
            SUM(A19700)  AS total_dons,
            SUM(A00300)  AS total_interets
        FROM irs_zip_income
        WHERE zipcode != '00000'
        GROUP BY zipcode, STATE
        HAVING SUM(N1) > 50
    """).fetchdf()
    con.close()

    # Ratios (plus parlants que les montants bruts pour détecter des anomalies)
    df["agi_par_declaration"] = df["total_agi"] / df["n_declarations"]
    df["ratio_dons_agi"] = df["total_dons"] / df["total_agi"].replace(0, np.nan)
    df["ratio_interets_agi"] = df["total_interets"] / df["total_agi"].replace(0, np.nan)
    df = df.fillna(0)
    return df


def detect_anomalous_zips(df: pd.DataFrame, contamination=0.02) -> pd.DataFrame:
    features = ["agi_par_declaration", "ratio_dons_agi", "ratio_interets_agi"]
    model = IsolationForest(contamination=contamination, random_state=42, n_estimators=200)
    df["anomaly_score"] = model.fit_predict(df[features])
    df["is_anomalous"] = df["anomaly_score"] == -1
    return df.sort_values("ratio_dons_agi", ascending=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="../raw/irs_soi/22zpallagi.csv")
    parser.add_argument("--duckdb", default="../processed/irs_warehouse.duckdb")
    args = parser.parse_args()

    load_csv_to_duckdb(args.csv, args.duckdb)

    print("\nConstruction des features par ZIP code...")
    zip_df = build_zip_features(args.duckdb)
    print(f"{len(zip_df):,} ZIP codes analysés (avec >50 déclarations)")

    print("\nEntraînement Isolation Forest (détection d'anomalies, données réelles)...")
    result = detect_anomalous_zips(zip_df)

    n_anom = result["is_anomalous"].sum()
    print(f"\n✅ {n_anom} ZIP codes signalés comme statistiquement atypiques ({n_anom/len(result)*100:.1f}%)")
    print("\nTop 10 ZIP codes les plus atypiques (ratio dons/AGI le plus élevé) :")
    print(result[result["is_anomalous"]][["zipcode", "STATE", "n_declarations", "agi_par_declaration", "ratio_dons_agi"]].head(10).to_string())
