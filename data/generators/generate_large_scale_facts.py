"""
GEIF — Génération à grande échelle : table de faits des transactions fiscales
===================================================================================
Contrairement à generate_fiscal_timeseries.py (agrégé par jour), ce script génère
UNE LIGNE PAR TRANSACTION/DOCUMENT — c'est ce qui permet d'atteindre un vrai volume
"big data" (centaines de milliers à millions de lignes), stocké en **Parquet**
(format colonnaire standard en Big Data, bien plus efficace qu'un CSV géant) et
chargé dans **DuckDB** pour interrogation analytique rapide.

Architecture en étoile (star schema) :
    - dim_contribuables (build_mock_warehouse.py)  → dimension
    - fact_transactions (ce script)                 → table de faits

Usage :
    python generate_large_scale_facts.py --n 500000 --warehouse ../data_engineering/fiscal_warehouse.duckdb --out ../processed/fact_transactions.parquet
"""
import argparse
import time

import duckdb
import numpy as np
import pandas as pd

TAX_TYPES = np.array(["TVA", "IS", "IR", "TP"])
NATURES = np.array(["declaration", "reclamation", "avis_redressement", "justificatif"])
NATURE_WEIGHTS = [0.55, 0.25, 0.12, 0.08]
BASE_AMOUNTS = {"TVA": 45000, "IS": 120000, "IR": 8000, "TP": 15000}


def generate_facts(n: int, warehouse_path: str, start_year: int = 2021, end_year: int = 2026) -> pd.DataFrame:
    rng = np.random.default_rng(42)

    # Récupère les IUF existants dans l'entrepôt pour lier la table de faits à la dimension
    con = duckdb.connect(warehouse_path, read_only=True)
    iufs = con.execute("SELECT iuf FROM contribuables").fetchdf()["iuf"].values
    con.close()

    # --- Génération vectorisée (numpy), pas de boucle Python ligne par ligne ---
    transaction_id = np.arange(1, n + 1)
    contribuable_iuf = rng.choice(iufs, size=n)

    start_ts = pd.Timestamp(start_year, 1, 1).value // 10**9
    end_ts = pd.Timestamp(end_year, 12, 31).value // 10**9
    random_ts = rng.integers(start_ts, end_ts, size=n)
    dates = pd.to_datetime(random_ts, unit="s")

    tax_type = rng.choice(TAX_TYPES, size=n, p=[0.35, 0.25, 0.20, 0.20])
    document_nature = rng.choice(NATURES, size=n, p=NATURE_WEIGHTS)

    base_amounts_arr = np.array([BASE_AMOUNTS[t] for t in tax_type])
    montant = rng.lognormal(mean=np.log(base_amounts_arr), sigma=0.6)

    # Anomalies : ~1% des transactions, montant démultiplié
    is_anomaly = rng.random(n) < 0.01
    anomaly_multiplier = rng.choice([0.05, 8, 15], size=n)
    montant = np.where(is_anomaly, montant * anomaly_multiplier, montant)

    df = pd.DataFrame({
        "transaction_id": transaction_id,
        "iuf": contribuable_iuf,
        "date": dates,
        "tax_type": tax_type,
        "document_nature": document_nature,
        "montant": np.round(montant, 2),
        "is_anomaly": is_anomaly,
    })
    return df.sort_values("date").reset_index(drop=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=500_000)
    parser.add_argument("--warehouse", default="../data_engineering/fiscal_warehouse.duckdb")
    parser.add_argument("--out", default="../processed/fact_transactions.parquet")
    args = parser.parse_args()

    t0 = time.time()
    df = generate_facts(args.n, args.warehouse)
    t1 = time.time()
    print(f"✅ {len(df):,} transactions générées en {t1-t0:.1f}s")

    df.to_parquet(args.out, index=False, compression="snappy")
    t2 = time.time()
    print(f"✅ Fichier Parquet sauvegardé : {args.out} en {t2-t1:.1f}s")

    import os
    size_mb = os.path.getsize(args.out) / (1024 * 1024)
    print(f"   Taille sur disque : {size_mb:.1f} MB (Parquet, compressé)")
    print(f"   Anomalies : {df['is_anomaly'].sum():,} ({df['is_anomaly'].mean()*100:.2f}%)")
