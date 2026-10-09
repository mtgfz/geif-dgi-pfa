"""
Module de prédiction.

Deux prédictions distinctes, honnêtes sur ce qu'elles sont réellement :

1) PRÉVISION DE VOLUME (série temporelle) :
   à partir de l'historique réel des réclamations dans MongoDB, on agrège le
   nombre de dossiers reçus par jour et on extrapole une tendance linéaire
   (régression simple) pour les prochains jours. Utile pour que le chef de
   secteur anticipe la charge de travail.

2) PRÉDICTION D'ISSUE (avant traitement) :
   pour un dossier donné, avant même de le traiter, on renvoie la probabilité
   d'acceptation apprise par le moteur de règles bayésien (confiance de la
   règle applicable = alpha/(alpha+beta)). C'est directement la sortie de
   l'apprentissage en ligne (rules_engine.appliquer_feedback) — donc chaque
   correction du gestionnaire améliore aussi cette prédiction.

Aucune des deux ne prétend faire du deep learning : ce sont des méthodes
statistiques simples, expliquables et défendables devant un jury, branchées
sur de vraies données.
"""
from collections import defaultdict
from datetime import datetime, timedelta

from .database import col_reclamations, col_rules, col_predictions_log
from .rules_engine import choisir_regle_id, jours_entre


def predict_volume(tax: str | None, horizon_jours: int) -> dict:
    query = {"tax": tax} if tax else {}
    rows = list(col_reclamations.find(query, {"created_at": 1}))

    if len(rows) < 3:
        return {
            "disponible": False,
            "message": "Historique insuffisant (moins de 3 dossiers) pour produire une prévision fiable.",
            "historique_points": len(rows),
        }

    # Agrégation par jour
    par_jour = defaultdict(int)
    for r in rows:
        d = datetime.fromisoformat(r["created_at"]).date()
        par_jour[d] += 1

    jours_tries = sorted(par_jour.keys())
    jour0 = jours_tries[0]
    xs = [(j - jour0).days for j in jours_tries]
    ys = [par_jour[j] for j in jours_tries]

    # Régression linéaire simple (moindres carrés, sans dépendance externe)
    n = len(xs)
    moy_x = sum(xs) / n
    moy_y = sum(ys) / n
    cov = sum((x - moy_x) * (y - moy_y) for x, y in zip(xs, ys))
    var_x = sum((x - moy_x) ** 2 for x in xs)
    pente = cov / var_x if var_x > 0 else 0.0
    ordonnee = moy_y - pente * moy_x

    dernier_x = xs[-1]
    previsions = []
    for i in range(1, horizon_jours + 1):
        x = dernier_x + i
        valeur = max(0.0, ordonnee + pente * x)
        jour = jour0 + timedelta(days=x)
        previsions.append({"date": jour.isoformat(), "volume_prevu": round(valeur, 1)})

    tendance = "hausse" if pente > 0.05 else ("baisse" if pente < -0.05 else "stable")

    return {
        "disponible": True,
        "tax": tax or "toutes",
        "methode": "régression linéaire sur historique quotidien",
        "historique_points": n,
        "tendance": tendance,
        "pente_par_jour": round(pente, 3),
        "previsions": previsions,
    }


def predict_outcome(tax: str, motif: str, montant: float, date_mer: str, date_reclam: str) -> dict:
    delai = jours_entre(date_mer, date_reclam)
    rule_id = choisir_regle_id(tax, motif, delai)
    if not rule_id:
        return {"disponible": False, "message": "Aucune règle applicable trouvée pour ce type d'impôt."}

    regle = col_rules.find_one({"_id": rule_id})
    if not regle:
        return {"disponible": False, "message": "Règle introuvable."}

    alpha, beta = regle["alpha"], regle["beta"]
    proba_acceptation = alpha / (alpha + beta)
    # incertitude approximative de la Beta (écart-type) — utile pour afficher
    # une fourchette plutôt qu'un faux chiffre unique trop précis
    variance = (alpha * beta) / (((alpha + beta) ** 2) * (alpha + beta + 1))
    ecart_type = variance ** 0.5

    montant_degreve_attendu = round(montant * regle["taux"], 2)
    observations = round(alpha + beta - 1, 1)

    log_entry = {
        "predicted_at": datetime.now().isoformat(),
        "rule_id": rule_id,
        "tax": tax,
        "motif": motif,
        "proba_acceptation_predite": round(proba_acceptation, 4),
        "montant_degreve_attendu": montant_degreve_attendu,
    }
    col_predictions_log.insert_one(log_entry)

    return {
        "disponible": True,
        "rule_id": rule_id,
        "delai_jours": delai,
        "proba_acceptation": round(proba_acceptation, 4),
        "incertitude": round(ecart_type, 4),
        "observations_historiques": observations,
        "montant_degreve_attendu": montant_degreve_attendu,
        "confiance_qualitative": (
            "élevée" if observations >= 20 else "moyenne" if observations >= 5 else "faible (peu d'historique)"
        ),
    }
