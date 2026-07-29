"""
GEIF — Pipeline d'automatisation : enrichissement de contribuables par IUF
================================================================================
Remplace la tâche manuelle "coller chaque IUF dans Cognos, lire l'adresse
sociale, copier dans Excel" par un pipeline automatisé et orchestré avec
Prefect :

    1. Lire un fichier Excel/CSV contenant une colonne "iuf"
    2. Interroger l'entrepôt DuckDB pour chaque IUF (en une seule requête, pas
       un par un comme dans Cognos)
    3. Valider la qualité des données obtenues (Pandera) — signaler les IUF
       introuvables ou les incohérences
    4. Exporter un Excel enrichi, prêt à l'emploi

Usage :
    python enrich_pipeline.py --input mes_iufs.xlsx --warehouse ./fiscal_warehouse.duckdb --output enrichi.xlsx
"""
import argparse
from pathlib import Path

import duckdb
import pandas as pd
import pandera.pandas as pa
from pandera.pandas import Column, Check
from prefect import flow, task, get_run_logger


# --- Schéma de validation attendu en sortie (Pandera) ---
OUTPUT_SCHEMA = pa.DataFrameSchema({
    "iuf": Column(str, nullable=False),
    "raison_sociale": Column(str, nullable=True),
    "adresse_sociale": Column(str, nullable=True),
    "activite": Column(str, nullable=True),
    "statut": Column(str, Check.isin(["Actif", "Radié", None]), nullable=True),
    "valeur_locative": Column(float, Check.ge(0), nullable=True),
    "trouve_dans_entrepot": Column(bool, nullable=False),
})


@task(name="Lire le fichier d'entrée (Excel/CSV)")
def read_input_file(path: str) -> pd.DataFrame:
    logger = get_run_logger()
    if path.endswith(".csv"):
        df = pd.read_csv(path, dtype={"iuf": str})
    else:
        df = pd.read_excel(path, dtype={"iuf": str})

    if "iuf" not in df.columns:
        raise ValueError("Le fichier d'entrée doit contenir une colonne 'iuf'.")

    df["iuf"] = df["iuf"].astype(str).str.strip()
    logger.info(f"{len(df)} IUF chargés depuis {path}")
    return df


@task(name="Interroger l'entrepot DuckDB (batch, pas un par un)")
def query_warehouse(iufs: pd.DataFrame, warehouse_path: str) -> pd.DataFrame:
    logger = get_run_logger()
    con = duckdb.connect(warehouse_path, read_only=True)

    iuf_list = iufs["iuf"].tolist()
    placeholders = ", ".join(["?"] * len(iuf_list))
    query = f"""
        SELECT iuf, raison_sociale, adresse_sociale, activite, statut, valeur_locative
        FROM contribuables
        WHERE iuf IN ({placeholders})
    """
    result = con.execute(query, iuf_list).fetchdf()
    con.close()

    logger.info(f"{len(result)}/{len(iuf_list)} IUF trouvés dans l'entrepôt")
    return result


@task(name="Fusionner et marquer les IUF introuvables")
def merge_results(iufs: pd.DataFrame, warehouse_result: pd.DataFrame) -> pd.DataFrame:
    merged = iufs[["iuf"]].merge(warehouse_result, on="iuf", how="left")
    merged["trouve_dans_entrepot"] = merged["raison_sociale"].notna()
    return merged


@task(name="Valider la qualite des donnees (Pandera)")
def validate_output(df: pd.DataFrame) -> pd.DataFrame:
    logger = get_run_logger()
    try:
        OUTPUT_SCHEMA.validate(df, lazy=True)
        logger.info("✅ Validation Pandera réussie — schéma conforme.")
    except pa.errors.SchemaErrors as e:
        logger.warning(f"⚠️ {len(e.failure_cases)} anomalie(s) de schéma détectée(s) :")
        logger.warning(e.failure_cases.to_string())
    return df


@task(name="Exporter le fichier enrichi")
def export_output(df: pd.DataFrame, output_path: str):
    logger = get_run_logger()
    df.to_excel(output_path, index=False)
    n_missing = (~df["trouve_dans_entrepot"]).sum()
    logger.info(f"✅ Export terminé : {output_path} ({n_missing} IUF non trouvés, à vérifier manuellement)")


@flow(name="Enrichissement automatique des contribuables par IUF")
def enrich_pipeline(input_path: str, warehouse_path: str, output_path: str):
    iufs = read_input_file(input_path)
    warehouse_result = query_warehouse(iufs, warehouse_path)
    merged = merge_results(iufs, warehouse_result)
    validated = validate_output(merged)
    export_output(validated, output_path)
    return validated


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, help="Fichier Excel/CSV avec une colonne 'iuf'")
    parser.add_argument("--warehouse", default="./fiscal_warehouse.duckdb")
    parser.add_argument("--output", default="./enrichi.xlsx")
    args = parser.parse_args()

    enrich_pipeline(args.input, args.warehouse, args.output)
