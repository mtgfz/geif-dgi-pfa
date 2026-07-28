"""
GEIF — Générateur de l'historique fiscal synthétique
=========================================================
Ce générateur produit un jeu de données tabulaire avec une vraie dimension
temporelle : volume quotidien de déclarations/réclamations par type d'impôt
sur plusieurs années, avec saisonnalité réaliste (pics de dépôt de TVA en
fin de mois, pic de réclamations après les avis de redressement annuels)
et anomalies injectées (fraudes/pics suspects).

Sert de socle pour :
  - Le pilier Time Series (prévision de volume, détection de rupture)
  - Le pilier ML/anomalies (classification normal vs anomalie)
  - Le pilier "Big Data" (volumétrie mise à l'échelle, pensé pour un
    traitement par batch/Spark si besoin, même si généré ici en pandas)

Usage :
    python generate_fiscal_timeseries.py --years 3 --out ../processed/fiscal_timeseries.csv
"""
import argparse
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

np.random.seed(42)

TAX_TYPES = ["TVA", "IS", "IR", "TP"]
DOC_NATURES = ["declaration", "reclamation", "avis_redressement", "justificatif"]


def seasonal_factor(day, tax_type):
    """Facteur multiplicatif de saisonnalité selon le jour du mois et le type d'impôt."""
    day_of_month = day.day
    factor = 1.0

    if tax_type == "TVA":
        # Pic en fin de mois (dépôt mensuel/trimestriel de la TVA)
        if day_of_month >= 25:
            factor *= 2.8
    elif tax_type == "IS":
        # Pic en mars/avril (clôture d'exercice) et en juin/sept/déc (acomptes)
        if day.month in (3, 4):
            factor *= 3.2
        elif day.month in (6, 9, 12):
            factor *= 2.0
    elif tax_type == "IR":
        if day.month in (2, 3):
            factor *= 2.5
    elif tax_type == "TP":
        if day.month == 1 or day.month == 2:
            factor *= 2.2

    # Weekend : quasi aucun dépôt
    if day.weekday() >= 5:
        factor *= 0.05

    return factor


def generate_timeseries(n_years, base_daily_volume=25):
    start = datetime(2024, 1, 1)
    end = start + timedelta(days=365 * n_years)
    days = pd.date_range(start, end, freq="D")

    records = []
    for day in days:
        for tax_type in TAX_TYPES:
            factor = seasonal_factor(day, tax_type)
            expected_volume = base_daily_volume * factor / len(TAX_TYPES)
            volume = np.random.poisson(max(expected_volume, 0.1))

            # Répartition du volume entre nature de document
            nature_weights = [0.55, 0.25, 0.12, 0.08]  # déclaration dominante
            nature_counts = np.random.multinomial(volume, nature_weights) if volume > 0 else [0, 0, 0, 0]

            for nature, count in zip(DOC_NATURES, nature_counts):
                if count == 0:
                    continue
                # Montant moyen simulé, dépend du type d'impôt
                base_amount = {"TVA": 45000, "IS": 120000, "IR": 8000, "TP": 15000}[tax_type]
                amounts = np.random.lognormal(mean=np.log(base_amount), sigma=0.6, size=count)

                # Anomalie : ~1.5% de chance qu'un jour soit "anormal" pour ce (type, nature)
                is_anomaly_day = np.random.random() < 0.015
                if is_anomaly_day:
                    amounts *= np.random.choice([0.05, 8, 12])

                records.append({
                    "date": day.strftime("%Y-%m-%d"),
                    "tax_type": tax_type,
                    "document_nature": nature,
                    "count": int(count),
                    "total_amount": round(float(np.sum(amounts)), 2),
                    "avg_amount": round(float(np.mean(amounts)), 2),
                    "is_anomaly_day": bool(is_anomaly_day),
                })

    return pd.DataFrame(records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--years", type=int, default=3)
    parser.add_argument("--out", type=str, default="../processed/fiscal_timeseries.csv")
    parser.add_argument("--base-volume", type=int, default=25)
    args = parser.parse_args()

    df = generate_timeseries(args.years, args.base_volume)
    df.to_csv(args.out, index=False)

    print(f"✅ {len(df)} lignes générées sur {args.years} ans")
    print(f"✅ Fichier sauvegardé : {args.out}")
    print(f"   Anomalies injectées : {df['is_anomaly_day'].sum()} ({df['is_anomaly_day'].mean()*100:.2f}%)")
    print(df.head(10).to_string())
