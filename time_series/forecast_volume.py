"""
GEIF — Prévision du volume de documents fiscaux (Time Series)
==================================================================
Prévoit le volume quotidien/mensuel de documents par type d'impôt, pour
anticiper la charge de travail du service (planification des ressources).

Deux approches fournies :
  1. Baseline saisonnière naïve (moyenne du même jour-de-semaine/mois sur
     les périodes précédentes) — rapide, robuste, bon point de comparaison.
  2. SARIMAX (statsmodels) — capture la saisonnalité mensuelle de façon
     plus fine.

Note pour la suite : si tu veux réutiliser tes modèles BiLSTM/N-BEATS/TiDE
du projet AIOps, le même découpage train/test et la même interface
predict(horizon) s'appliquent directement — seul le modèle change.

Usage :
    python forecast_volume.py --tax-type TVA --horizon 30
"""
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from statsmodels.tsa.statespace.sarimax import SARIMAX


def load_monthly_series(csv_path: str, tax_type: str) -> pd.Series:
    df = pd.read_csv(csv_path, parse_dates=["date"])
    df = df[df["tax_type"] == tax_type]
    monthly = df.groupby(pd.Grouper(key="date", freq="ME"))["count"].sum()
    monthly.index.freq = "ME"
    return monthly


def naive_seasonal_forecast(series: pd.Series, horizon: int) -> pd.Series:
    """Baseline : prévoit chaque mois futur = moyenne du même mois calendaire
    observé dans l'historique (capture la saisonnalité sans modèle complexe)."""
    monthly_avg = series.groupby(series.index.month).mean()
    last_date = series.index[-1]
    future_dates = pd.date_range(last_date, periods=horizon + 1, freq="ME")[1:]
    forecast = [monthly_avg.get(d.month, series.mean()) for d in future_dates]
    return pd.Series(forecast, index=future_dates)


def sarimax_forecast(series: pd.Series, horizon: int):
    """SARIMAX avec composante saisonnière annuelle (order/seasonal_order
    volontairement simples — à affiner avec une vraie recherche de grille
    si tu veux pousser cette partie plus loin dans ton rapport)."""
    model = SARIMAX(
        series, order=(1, 1, 1), seasonal_order=(1, 1, 0, 12),
        enforce_stationarity=False, enforce_invertibility=False
    )
    fitted = model.fit(disp=False)
    forecast = fitted.get_forecast(steps=horizon)
    return forecast.predicted_mean, forecast.conf_int()


def evaluate(series: pd.Series, holdout: int = 6):
    """Évalue sur les derniers 'holdout' mois observés (backtest simple)."""
    train = series[:-holdout]
    test = series[-holdout:]
    baseline = naive_seasonal_forecast(train, holdout)
    mae_baseline = np.mean(np.abs(test.values - baseline.values[:len(test)]))
    return mae_baseline


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="../data/processed/fiscal_timeseries.csv")
    parser.add_argument("--tax-type", default="TVA", choices=["TVA", "IS", "IR", "TP"])
    parser.add_argument("--horizon", type=int, default=6, help="Horizon de prévision en mois")
    args = parser.parse_args()

    series = load_monthly_series(args.csv, args.tax_type)
    print(f"Historique chargé : {len(series)} mois pour {args.tax_type}")

    mae = evaluate(series)
    print(f"MAE baseline (backtest 6 derniers mois) : {mae:.1f} documents/mois")

    naive_fc = naive_seasonal_forecast(series, args.horizon)
    print(f"\n--- Prévision baseline saisonnière ({args.horizon} mois) ---")
    print(naive_fc.round(0))

    try:
        sarimax_fc, conf_int = sarimax_forecast(series, args.horizon)
        print(f"\n--- Prévision SARIMAX ({args.horizon} mois) ---")
        print(sarimax_fc.round(0))
    except Exception as e:
        print(f"\n⚠️ SARIMAX a échoué ({e}) — la baseline saisonnière reste utilisable.")
