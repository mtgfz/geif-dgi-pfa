import statistics
from datetime import datetime

from fastapi import APIRouter, Depends

from ..config import settings
from ..constants import DECISION_ENVOYEE, NOUVELLE, STATUT_LABELS, STATUTS, TYPES_DECISION
from ..database import col_corrections, col_documents, col_feedback_log, col_reclamations, col_rules
from ..security import get_current_user

router = APIRouter(tags=["statistiques"])


def _delai_jours(r: dict) -> float | None:
    if not r.get("closed_at"):
        return None
    try:
        delta = datetime.fromisoformat(r["closed_at"]) - datetime.fromisoformat(r["created_at"])
    except (ValueError, KeyError):
        return None
    return max(delta.total_seconds() / 86400, 0.0)


@router.get("/statistiques")
def statistiques(_user: dict = Depends(get_current_user)):
    """Statistiques réelles calculées à partir de MongoDB — aucune valeur simulée."""
    toutes = list(col_reclamations.find())
    total = len(toutes)
    traitees = sum(1 for r in toutes if r["status"] != NOUVELLE)
    terminees = [r for r in toutes if r["status"] == DECISION_ENVOYEE]

    par_statut = {s: 0 for s in STATUTS}
    for r in toutes:
        par_statut[r["status"]] = par_statut.get(r["status"], 0) + 1

    par_impot_agg = {}
    for r in toutes:
        e = par_impot_agg.setdefault(r["tax"], {"tax": r["tax"], "nombre": 0, "montant_emis": 0.0, "montant_degreve": 0.0, "delais": []})
        e["nombre"] += 1
        e["montant_emis"] += r.get("montant") or 0
        e["montant_degreve"] += r.get("montant_degreve") or 0
        dj = _delai_jours(r)
        if dj is not None:
            e["delais"].append(dj)
    par_impot = []
    for e in par_impot_agg.values():
        delais = e.pop("delais")
        e["delai_moyen_jours"] = round(sum(delais) / len(delais), 1) if delais else None
        par_impot.append(e)

    par_motif_agg = {}
    for r in toutes:
        key = (r["motif"], r["tax"])
        par_motif_agg[key] = par_motif_agg.get(key, 0) + 1
    par_motif = [{"motif": k[0], "tax": k[1], "nombre": v} for k, v in
                 sorted(par_motif_agg.items(), key=lambda x: -x[1])]

    par_mois = {}
    for r in toutes:
        mois = r["created_at"][:7]
        par_mois[mois] = par_mois.get(mois, 0) + 1

    # Répartition des décisions (dossiers dont la décision a été envoyée)
    repartition = {t: 0 for t in TYPES_DECISION}
    for r in terminees:
        if r.get("type_decision") in repartition:
            repartition[r["type_decision"]] += 1

    delais = [d for d in (_delai_jours(r) for r in terminees) if d is not None]
    delai_moyen = round(sum(delais) / len(delais), 1) if delais else None

    # Qualité de la proposition IA : décisions du gestionnaire (accept / modify / reject)
    fb = {"accept": 0, "modify": 0, "reject": 0}
    for f in col_feedback_log.find({}, {"outcome": 1}):
        if f.get("outcome") in fb:
            fb[f["outcome"]] += 1
    total_fb = sum(fb.values())
    taux_acceptation = round(fb["accept"] / total_fb, 4) if total_fb else None

    faibles = sum(1 for r in toutes if r.get("retrieval_score") is not None and r["retrieval_score"] < settings.SEUIL_CONFIANCE_RETRIEVAL)
    montant_emis_total = sum(r.get("montant") or 0 for r in toutes if r["status"] != NOUVELLE)
    montant_degreve_total = sum(r.get("montant_degreve") or 0 for r in terminees)
    montant_conteste_termine = sum(r.get("montant") or 0 for r in terminees)  # base cohérente du taux de dégrèvement

    compteur_articles = {}
    for r in toutes:
        if r.get("article"):
            compteur_articles[r["article"]] = compteur_articles.get(r["article"], 0) + 1
    articles_mobilises = [{"article": a, "nombre": n} for a, n in sorted(compteur_articles.items(), key=lambda x: -x[1])[:8]]

    regles_stats = []
    for r in col_rules.find():
        nb_corr = col_corrections.count_documents({"rule_id": r["_id"]})
        regles_stats.append({
            "id": r["_id"], "tax": r["tax"], "motif": r["motif"],
            "confiance": round(r["alpha"] / (r["alpha"] + r["beta"]), 4),
            "observations": round(r["alpha"] + r["beta"] - 1, 1),
            "corrections": nb_corr,
        })

    return {
        "total_reclamations": total, "traitees": traitees, "terminees": len(terminees),
        "par_statut": par_statut, "statut_labels": STATUT_LABELS,
        "par_impot": par_impot, "par_motif": par_motif, "par_mois": dict(sorted(par_mois.items())),
        "repartition_decisions": repartition, "delai_moyen_traitement_jours": delai_moyen,
        "retournees_en_cours": par_statut.get("retournee", 0),
        "feedback_gestionnaire": fb, "taux_acceptation_sans_modification": taux_acceptation,
        "dossiers_retrieval_faible": faibles,
        "montant_total_emis": montant_emis_total, "montant_total_degreve": montant_degreve_total,
        "montant_conteste_termine": montant_conteste_termine,
        "nombre_corrections_enregistrees": col_corrections.count_documents({}),
        "regles": regles_stats, "articles_mobilises": articles_mobilises,
    }


ANOMALIES = {
    "delai_depasse": "Délai de réclamation dépassé",
    "montant_atypique": "Montant atypique pour cet impôt",
    "if_different": "IF du document différent de l'IF déclaré",
    "ocr_echec": "Pièce illisible (lecture automatique échouée)",
    "sans_piece": "Aucune pièce déposée",
    "retrieval_faible": "Base légale peu certaine (CGI)",
    "attente_longue": "En attente depuis trop longtemps",
}


@router.get("/statistiques/anomalies")
def anomalies(_user: dict = Depends(get_current_user)):
    """Dossiers présentant un signal à vérifier. Les règles sont simples, explicites et calculées sur les données
    réelles (aucune valeur simulée) ; chaque signal indique pourquoi il est levé."""
    dossiers = list(col_reclamations.find())
    docs_par_dossier = {}
    for d in col_documents.find({}, {"reclamation_id": 1, "ocr_ok": 1, "texte_ocr": 1, "champs_ocr": 1}):
        docs_par_dossier.setdefault(d["reclamation_id"], []).append(d)

    montants_par_impot = {}
    for r in dossiers:
        montants_par_impot.setdefault(r["tax"], []).append(r.get("montant") or 0)
    stats_impot = {t: (statistics.mean(v), statistics.pstdev(v)) for t, v in montants_par_impot.items() if len(v) >= 5}

    maintenant = datetime.now()
    items = []
    for r in dossiers:
        signaux = []
        try:
            delai = (datetime.fromisoformat(r["date_reclam"]) - datetime.fromisoformat(r["date_mer"])).days
            if delai > settings.DELAI_RECLAMATION_JOURS:
                signaux.append(("delai_depasse", f"{delai} jours entre la mise en recouvrement et la réclamation (seuil {settings.DELAI_RECLAMATION_JOURS})"))
        except (KeyError, ValueError):
            pass
        if r["tax"] in stats_impot:
            moyenne, ecart = stats_impot[r["tax"]]
            z = (r.get("montant", 0) - moyenne) / ecart if ecart else 0
            if z > settings.SEUIL_MONTANT_ZSCORE:
                signaux.append(("montant_atypique", f"{z:.1f} écarts-types au-dessus de la moyenne des réclamations {r['tax']}"))
        docs = docs_par_dossier.get(r["_id"], [])
        if not docs and r["status"] != "nouvelle":
            signaux.append(("sans_piece", "Le dossier est traité sans aucune pièce justificative"))
        elif not docs:
            signaux.append(("sans_piece", "Le contribuable n'a joint aucune pièce"))
        if any(not d.get("ocr_ok", bool(d.get("texte_ocr"))) for d in docs):
            signaux.append(("ocr_echec", "Au moins une pièce n'a pas pu être lue automatiquement"))
        ifs = {str(d["champs_ocr"]["identifiant_fiscal"]).replace(" ", "") for d in docs if (d.get("champs_ocr") or {}).get("identifiant_fiscal")}
        if ifs and str(r["ifn"]).replace(" ", "") not in ifs:
            signaux.append(("if_different", f"Document : {', '.join(sorted(ifs))} — déclaré : {r['ifn']}"))
        if r.get("rule_id") and (r.get("retrieval_score") or 0) < settings.SEUIL_CONFIANCE_RETRIEVAL:
            signaux.append(("retrieval_faible", "Aucun article du CGI ne correspond clairement au motif"))
        if r["status"] != "decision_envoyee":
            age = (maintenant - datetime.fromisoformat(r["created_at"])).days
            if age > settings.SEUIL_ATTENTE_JOURS:
                signaux.append(("attente_longue", f"{age} jours depuis le dépôt (seuil {settings.SEUIL_ATTENTE_JOURS})"))
        if signaux:
            items.append({
                "id": r["_id"], "contrib": r["contrib"], "tax": r["tax"], "status": r["status"], "montant": r.get("montant"),
                "created_at": r["created_at"], "signaux": [{"code": c, "libelle": ANOMALIES[c], "detail": d} for c, d in signaux],
            })
    items.sort(key=lambda i: (-len(i["signaux"]), i["created_at"]))
    resume = {c: sum(1 for i in items for s_ in i["signaux"] if s_["code"] == c) for c in ANOMALIES}
    return {
        "total": len(items), "dossiers_analyses": len(dossiers), "resume": resume, "libelles": ANOMALIES,
        "seuils": {"delai_jours": settings.DELAI_RECLAMATION_JOURS, "attente_jours": settings.SEUIL_ATTENTE_JOURS,
                   "montant_zscore": settings.SEUIL_MONTANT_ZSCORE, "dossiers_min_zscore": 5},
        "items": items[:100],
    }
