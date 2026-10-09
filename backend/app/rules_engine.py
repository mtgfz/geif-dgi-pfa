"""
Moteur de règles + apprentissage en ligne.

Chaque règle a une confiance modélisée par une distribution Beta(alpha, beta) :
c'est un bandit bayésien (une forme légère et honnête de "RL" — le système
ajuste ses paramètres à chaque décision du gestionnaire, sans jamais prétendre
faire du deep RL qu'on ne pourrait pas défendre à l'oral). Concrètement :
  - "accept"  -> alpha += 1  (la règle avait raison)
  - "reject"  -> beta  += 1  (la règle avait tort)
  - "modify"  -> alpha += 0.5, beta += 0.5 (partiellement raison)

confiance = alpha / (alpha + beta) est utilisée à la fois pour :
  1) le texte "Base légale identifiée" envoyé au LLM,
  2) la probabilité prédictive exposée par /predictions/outcome.
"""
from datetime import date

from .database import col_feedback_log, col_rules

RULES: dict[str, dict] = {
    "IS-CALC":   {"tax": "IS",  "motif": "Erreur de calcul de la base imposable",
                  "article": "Art. 232 CGI",
                  "resume_legal": "l'administration peut réparer, dans le délai de prescription, les erreurs et omissions constatées dans la liquidation ou l'émission de l'impôt.",
                  "taux": 0.9, "alpha": 6.0, "beta": 2.0},
    "IS-CHARGE": {"tax": "IS",  "motif": "Charge déductible rejetée à tort",
                  "article": "Art. 10 CGI",
                  "resume_legal": "les charges d'exploitation, financières et non courantes remplissant les conditions de fond et de forme sont déductibles du résultat fiscal.",
                  "taux": 0.7, "alpha": 5.0, "beta": 2.5},
    "IS-DOUBLE": {"tax": "IS",  "motif": "Double imposition",
                  "article": "Art. 235 CGI",
                  "resume_legal": "le contribuable peut contester tout ou partie du montant mis à sa charge par voie de réclamation auprès de l'administration.",
                  "taux": 1.0, "alpha": 4.5, "beta": 2.0},
    "IS-DELAI":  {"tax": "IS",  "motif": "Délai de réclamation dépassé",
                  "article": "Art. 235 CGI",
                  "resume_legal": "la réclamation doit être introduite dans les six mois suivant la mise en recouvrement ; passé ce délai, elle est irrecevable.",
                  "taux": 0.0, "alpha": 9.0, "beta": 1.0},

    "TVA-DEDUC": {"tax": "TVA", "motif": "TVA déductible non prise en compte",
                  "article": "Art. 101 à 106 CGI",
                  "resume_legal": "la TVA ayant grevé les éléments du prix d'une opération imposable est déductible, sous réserve des conditions de fond et de forme prévues (facture conforme, lien avec l'activité imposable).",
                  "taux": 0.85, "alpha": 5.0, "beta": 2.0},
    "TVA-EXO":   {"tax": "TVA", "motif": "Opération exonérée taxée à tort",
                  "article": "Art. 91-92 CGI",
                  "resume_legal": "certaines opérations sont exonérées de TVA, avec ou sans droit à déduction selon leur nature ; une opération relevant de ces exonérations ne doit pas être taxée.",
                  "taux": 1.0, "alpha": 4.0, "beta": 2.0},
    "TVA-TAUX":  {"tax": "TVA", "motif": "Erreur sur le taux appliqué",
                  "article": "CGI — barème des taux de TVA",
                  "resume_legal": "chaque opération imposable relève d'un taux déterminé par le CGI selon sa nature ; l'application d'un taux erroné donne lieu à régularisation.",
                  "taux": 0.6, "alpha": 5.0, "beta": 2.5},
    "TVA-DELAI": {"tax": "TVA", "motif": "Délai de réclamation dépassé",
                  "article": "Art. 235 CGI",
                  "resume_legal": "la réclamation doit être introduite dans les six mois suivant la mise en recouvrement ; passé ce délai, elle est irrecevable.",
                  "taux": 0.0, "alpha": 9.0, "beta": 1.0},

    "IR-BAREME": {"tax": "IR",  "motif": "Erreur sur le barème appliqué",
                  "article": "CGI — barème de l'IR", "resume_legal": "à vérifier par retrieval.",
                  "taux": 0.8, "alpha": 5.0, "beta": 2.0},
    "IR-DEDUC":  {"tax": "IR",  "motif": "Déduction non prise en compte (charges, frais professionnels)",
                  "article": "CGI — déductions IR", "resume_legal": "à vérifier par retrieval.",
                  "taux": 0.75, "alpha": 5.0, "beta": 2.0},
    "IR-DOUBLE": {"tax": "IR",  "motif": "Double imposition",
                  "article": "Art. 235 CGI", "resume_legal": "à vérifier par retrieval.",
                  "taux": 1.0, "alpha": 4.5, "beta": 2.0},
    "IR-DELAI":  {"tax": "IR",  "motif": "Délai de réclamation dépassé",
                  "article": "Art. 235 CGI", "resume_legal": "à vérifier par retrieval.",
                  "taux": 0.0, "alpha": 9.0, "beta": 1.0},
}


def init_rules():
    if col_rules.count_documents({}) == 0:
        for rid, r in RULES.items():
            doc = dict(r)
            doc["_id"] = rid
            col_rules.insert_one(doc)


def jours_entre(d1: str, d2: str) -> int:
    return (date.fromisoformat(d2) - date.fromisoformat(d1)).days


def confiance(regle: dict) -> float:
    return regle["alpha"] / (regle["alpha"] + regle["beta"])


def choisir_regle_id(tax: str, motif: str, delai_jours: int) -> str:
    """Sélectionne l'identifiant de règle applicable, sans le retrieval RAG
    (utilisé aussi bien par le traitement réel que par la prédiction, qui ne
    doit pas dépendre du RAG pour rester rapide)."""
    if delai_jours > 180:
        return f"{tax}-DELAI"
    trouve = col_rules.find_one({"tax": tax, "motif": motif})
    if trouve is None:
        trouve = col_rules.find_one({"tax": tax})
    return trouve["_id"] if trouve else None


def compute_learning_curve(rule_id: str) -> list[dict]:
    """Reconstruit la trajectoire de confiance d'une règle, correction par
    correction, à partir de son état initial (RULES) et de l'historique
    chronologique dans col_corrections. Sert à montrer concrètement que le
    système apprend — un point de départ, une courbe qui bouge, pas juste un
    chiffre final."""
    if rule_id not in RULES:
        return []
    alpha, beta = RULES[rule_id]["alpha"], RULES[rule_id]["beta"]
    courbe = [{"etape": 0, "outcome": "initial", "confiance": round(alpha / (alpha + beta), 4)}]

    historique = col_feedback_log.find({"rule_id": rule_id}).sort("created_at", 1)
    for i, corr in enumerate(historique, start=1):
        outcome = corr["outcome"]
        if outcome == "accept":
            alpha += 1.0
        elif outcome == "reject":
            beta += 1.0
        elif outcome == "modify":
            alpha += 0.5
            beta += 0.5
        courbe.append({
            "etape": i,
            "outcome": outcome,
            "confiance": round(alpha / (alpha + beta), 4),
            "date": corr.get("created_at"),
        })
    return courbe


def appliquer_feedback(rule_id: str, outcome: str):
    """Mise à jour bayésienne (le "RL") après la décision du gestionnaire.
    Journalise systématiquement dans col_feedback_log — c'est cette trace
    complète (accept compris) qui permet de reconstruire la vraie courbe
    d'apprentissage ensuite, sans rien perdre."""
    from datetime import datetime
    from .database import col_feedback_log

    regle = col_rules.find_one({"_id": rule_id})
    if not regle:
        return None
    alpha, beta = regle["alpha"], regle["beta"]
    if outcome == "accept":
        alpha += 1.0
    elif outcome == "reject":
        beta += 1.0
    elif outcome == "modify":
        alpha += 0.5
        beta += 0.5
    col_rules.update_one({"_id": rule_id}, {"$set": {"alpha": alpha, "beta": beta}})
    col_feedback_log.insert_one({
        "rule_id": rule_id, "outcome": outcome,
        "confiance_apres": round(alpha / (alpha + beta), 4),
        "created_at": datetime.now().isoformat(),
    })
    return round(alpha / (alpha + beta), 4)
