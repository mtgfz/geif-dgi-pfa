"""
GEIF — Entrepôt de données simulé (DuckDB)
================================================
Simule ce que Cognos/SIT fournirait en interrogation : une table de
contribuables avec leurs informations d'assiette (IF, raison sociale,
adresse sociale, activité, historique de siège...).

Objectif pédagogique : remplacer la recherche manuelle "coller un IUF dans
Cognos, lire l'adresse, copier dans Excel" par une vraie requête
automatisée sur un entrepôt de données — DuckDB joue ici le rôle du
data warehouse local (aucune donnée réelle de contribuable utilisée).

Usage :
    python build_mock_warehouse.py --n 500 --out ./fiscal_warehouse.duckdb
"""
import argparse
import random

import duckdb
import numpy as np
import pandas as pd

random.seed(7)
np.random.seed(7)

VILLES = ["Rabat", "Casablanca", "Fès", "Marrakech", "Tanger", "Salé", "Kénitra"]
RUES = ["Avenue Hassan II", "Rue Al Massira", "Boulevard Zerktouni", "Avenue Mohammed V",
        "Rue Ibn Sina", "Angle Rue Abdelmoumen", "Kissariat Al Mamoune"]
ACTIVITES = ["Conseil de gestion", "Commerce général", "BTP", "Services informatiques",
             "Import-export", "Restauration", "Immobilier", "Textile"]
FORMES = ["SARL", "SA", "SARL AU", "SNC"]


def random_address():
    return f"{random.randint(1, 200)} {random.choice(RUES)}, {random.choice(VILLES)}"


def generate_warehouse(n: int) -> pd.DataFrame:
    rows = []
    for i in range(n):
        iuf = str(random.randint(10000000, 99999999))
        raison_sociale = f"SOCIETE {random.choice(['ATLAS','MEDINA','OCEANE','SAHARA','RIF','NORD'])} {random.choice(['TRADE','SERVICES','CONSEIL','INDUSTRIE'])} {random.choice(FORMES)}"
        rows.append({
            "iuf": iuf,
            "raison_sociale": raison_sociale,
            "adresse_sociale": random_address(),
            "activite": random.choice(ACTIVITES),
            "ville": random.choice(VILLES),
            "date_creation": pd.Timestamp(2015, 1, 1) + pd.Timedelta(days=random.randint(0, 3800)),
            "statut": random.choices(["Actif", "Radié"], weights=[0.9, 0.1])[0],
            "valeur_locative": round(np.random.lognormal(mean=np.log(80000), sigma=0.7), 2),
        })
    return pd.DataFrame(rows)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=500)
    parser.add_argument("--out", type=str, default="./fiscal_warehouse.duckdb")
    args = parser.parse_args()

    df = generate_warehouse(args.n)

    con = duckdb.connect(args.out)
    con.execute("DROP TABLE IF EXISTS contribuables")
    con.execute("CREATE TABLE contribuables AS SELECT * FROM df")
    con.execute("CREATE INDEX idx_iuf ON contribuables(iuf)")
    con.close()

    print(f"✅ Entrepôt DuckDB créé : {args.out} ({len(df)} contribuables)")
    print(df.head(5).to_string())
