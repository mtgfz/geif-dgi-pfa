"""
GEIF — Entraînement ML supervisé sur données réelles (IRS SOI)
====================================================================
Complète la détection d'anomalies non-supervisée (Isolation Forest, voir
data/generators/load_irs_data.py) par un vrai modèle SUPERVISÉ : on utilise
les anomalies détectées par Isolation Forest comme pseudo-labels, puis on
entraîne un classifieur (Random Forest) à les prédire — ce qui permet
d'évaluer avec de vraies métriques supervisées (precision/recall/F1),
impossible avec de l'Isolation Forest seule (non supervisé, pas de "vérité
terrain" à comparer).

Intérêt pédagogique : montre la différence entre apprentissage non-supervisé
(détection d'anomalies, pas de labels) et supervisé (classification, labels
disponibles ou construits), sur le MÊME jeu de données réel.

Usage :
    python train_supervised_on_irs.py --duckdb ../data/processed/irs_warehouse.duckdb
"""
import argparse

import duckdb
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, confusion_matrix


def load_and_engineer_features(duckdb_path: str) -> pd.DataFrame:
    con = duckdb.connect(duckdb_path, read_only=True)
    df = con.execute("""
        SELECT
            zipcode, STATE,
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

    df["agi_par_declaration"] = df["total_agi"] / df["n_declarations"]
    df["ratio_dons_agi"] = df["total_dons"] / df["total_agi"].replace(0, np.nan)
    df["ratio_interets_agi"] = df["total_interets"] / df["total_agi"].replace(0, np.nan)
    df["ratio_salaires_agi"] = df["total_salaires"] / df["total_agi"].replace(0, np.nan)
    return df.fillna(0)


def create_pseudo_labels(df: pd.DataFrame, feature_cols: list, contamination=0.02) -> pd.DataFrame:
    """Isolation Forest sert ici à CONSTRUIRE des labels (0=normal, 1=anomalie)
    à partir de données non labellisées à l'origine — technique légitime
    quand on n'a pas de vraie vérité terrain, à condition de le documenter
    clairement (ce n'est pas une vérité absolue, juste un proxy)."""
    iso = IsolationForest(contamination=contamination, random_state=42, n_estimators=200)
    df["label_anomalie"] = (iso.fit_predict(df[feature_cols]) == -1).astype(int)
    return df


def train_supervised_classifier(df: pd.DataFrame, feature_cols: list):
    X = df[feature_cols]
    y = df["label_anomalie"]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y
    )

    clf = RandomForestClassifier(n_estimators=200, max_depth=8, random_state=42, class_weight="balanced")
    clf.fit(X_train, y_train)
    y_pred = clf.predict(X_test)

    print("=== Rapport de classification (Random Forest) ===")
    print(classification_report(y_test, y_pred, target_names=["Normal", "Anomalie"]))

    print("=== Matrice de confusion ===")
    print(confusion_matrix(y_test, y_pred))

    print("\n=== Importance des variables ===")
    importances = pd.Series(clf.feature_importances_, index=feature_cols).sort_values(ascending=False)
    print(importances.to_string())

    return clf


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--duckdb", default="../data/processed/irs_warehouse.duckdb")
    args = parser.parse_args()

    print("Chargement et feature engineering...")
    df = load_and_engineer_features(args.duckdb)
    print(f"{len(df):,} ZIP codes chargés\n")

    feature_cols = ["agi_par_declaration", "ratio_dons_agi", "ratio_interets_agi", "ratio_salaires_agi"]

    print("Construction des pseudo-labels (Isolation Forest)...")
    df = create_pseudo_labels(df, feature_cols)
    print(f"{df['label_anomalie'].sum()} ZIP codes labellisés 'anomalie' ({df['label_anomalie'].mean()*100:.1f}%)\n")

    print("Entraînement du classifieur supervisé (Random Forest)...\n")
    train_supervised_classifier(df, feature_cols)
