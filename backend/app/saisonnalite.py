"""
Prévision saisonnière des volumes (pilier « Séries temporelles » du projet).

S'appuie sur le module time_series/forecast_volume.py (baseline saisonnier + SARIMAX) appliqué à la série
SIMULÉE de data/generators/generate_fiscal_timeseries.py : le projet ne dispose pas de l'historique réel de
la DGI. La série est générée une fois (graine fixe, donc reproductible) puis mise en cache sur disque ;
elle est arrêtée au dernier mois complet. L'interface l'indique toujours comme « série simulée ».
"""
import os
import sys
import warnings
from datetime import date, timedelta

from .config import settings

IMPOTS = ("IS", "IR", "TVA")
_resultats: dict = {}


def _importer():
    for sous_dossier in (("time_series",), ("data", "generators")):
        chemin = os.path.join(settings.ROOT_DIR, *sous_dossier)
        if chemin not in sys.path:
            sys.path.append(chemin)
    import forecast_volume as fv                        # noqa: WPS433 — module du dépôt (pilier 4)
    import generate_fiscal_timeseries as gen            # noqa: WPS433
    return fv, gen


def _serie_csv(gen) -> str:
    os.makedirs(settings.CACHE_DIR, exist_ok=True)
    chemin = os.path.join(settings.CACHE_DIR, "fiscal_timeseries.csv")
    if not os.path.exists(chemin):
        import numpy as np
        np.random.seed(42)
        gen.generate_timeseries(3).to_csv(chemin, index=False)
    return chemin


def _mois(idx) -> str:
    return idx.strftime("%Y-%m")


def previsions_saisonnieres(tax: str, horizon: int = 6) -> dict:
    if tax not in IMPOTS:
        return {"disponible": False, "message": f"Type d'impôt inconnu (attendu : {', '.join(IMPOTS)})."}
    cle = (tax, horizon, date.today().strftime("%Y-%m"))
    if cle in _resultats:
        return _resultats[cle]
    try:
        fv, gen = _importer()
        serie = fv.load_monthly_series(_serie_csv(gen), tax)
    except ImportError as e:
        return {"disponible": False, "message": f"Module de séries temporelles indisponible ({e}). Installez pandas et statsmodels."}
    dernier_mois_complet = date.today().replace(day=1) - timedelta(days=1)
    tronquee = serie[serie.index <= str(dernier_mois_complet)]
    if len(tronquee) >= 24:
        serie = tronquee

    baseline = fv.naive_seasonal_forecast(serie, horizon)

    def _sarimax(donnees, h):
        """Retourne (moyenne, intervalle, a_convergé). Un avertissement de non-convergence = résultat peu fiable."""
        with warnings.catch_warnings(record=True) as avis:
            warnings.simplefilter("always")
            moyenne, ic = fv.sarimax_forecast(donnees, h)
        return moyenne, ic, not any("converge" in str(a.message).lower() for a in avis)

    sarimax, sarimax_converge = None, None
    try:
        moyenne, ic, sarimax_converge = _sarimax(serie, horizon)
        sarimax = [{"mois": _mois(d), "volume": round(float(v), 1), "bas": round(float(ic.iloc[i, 0]), 1), "haut": round(float(ic.iloc[i, 1]), 1)}
                   for i, (d, v) in enumerate(moyenne.items())]
    except Exception as e:  # noqa: BLE001 — SARIMAX peut ne pas converger : la baseline reste affichée
        print(f"[PRÉVISION] SARIMAX indisponible ({e})")

    backtest = None
    try:
        import numpy as np
        test, entrainement = serie[-6:], serie[:-6]
        mae_base = float(np.mean(np.abs(test.values - fv.naive_seasonal_forecast(entrainement, 6).values)))
        prevu, _ic, converge_bt = _sarimax(entrainement, 6)
        mae_sar = float(np.mean(np.abs(test.values - prevu.values)))
        backtest = {"mois": 6, "mae_baseline": round(mae_base, 1), "mae_sarimax": round(mae_sar, 1), "sarimax_converge": converge_bt,
                    # un modèle qui n'a pas convergé ne peut pas être déclaré « meilleur »
                    "meilleur": "SARIMAX" if (mae_sar < mae_base and converge_bt) else "Baseline saisonnier"}
    except Exception as e:  # noqa: BLE001
        print(f"[PRÉVISION] Backtest indisponible ({e})")

    resultat = {
        "disponible": True, "tax": tax, "horizon": horizon, "serie_simulee": True, "unite": "réclamations par mois",
        "historique": [{"mois": _mois(d), "volume": int(v)} for d, v in serie.items()],
        "baseline": [{"mois": _mois(d), "volume": round(float(v), 1)} for d, v in baseline.items()],
        "sarimax": sarimax, "sarimax_converge": sarimax_converge, "backtest": backtest,
    }
    _resultats[cle] = resultat
    return resultat
