import os
from datetime import datetime

from fastapi import APIRouter, Depends

from ..config import settings
from ..constants import DECISION_ENVOYEE, NOUVELLE, STATUT_LABELS, STATUTS, TYPES_DECISION
from ..database import col_corrections, col_feedback_log, col_reclamations, col_rules
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
        "nombre_corrections_enregistrees": col_corrections.count_documents({}),
        "regles": regles_stats,
    }


@router.get("/marche-ammc")
def marche_ammc(_user: dict = Depends(get_current_user)):
    """Référentiel sectoriel (Pilier 9, DuckDB — indépendant de Mongo, ne
    nourrit pas le moteur de décision des réclamations)."""
    chemin_duckdb = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data_engineering", "analytics.duckdb")
    if not os.path.exists(chemin_duckdb):
        return {
            "disponible": False,
            "message": "Base analytics.duckdb introuvable — le Pilier 9 (AMMC) n'est pas accessible depuis ce module.",
            "chemin_attendu": os.path.abspath(chemin_duckdb),
        }
    try:
        import duckdb
    except ImportError:
        return {"disponible": False, "message": "Module duckdb non installé (pip install duckdb)."}
    try:
        con = duckdb.connect(chemin_duckdb, read_only=True)
        lignes = con.execute(
            "SELECT bank, year, total_actif_current, resultat_net_current, validated "
            "FROM market_financials ORDER BY bank, year"
        ).fetchall()
        colonnes = [c[0] for c in con.description]
        con.close()
        donnees = [dict(zip(colonnes, l)) for l in lignes]
        valides = [d for d in donnees if d.get("validated")]
        return {
            "disponible": True, "total_exercices": len(donnees), "exercices_valides": len(valides),
            "banques": sorted({d["bank"] for d in donnees}), "donnees": donnees,
        }
    except Exception as e:
        return {"disponible": False, "message": f"Erreur de lecture DuckDB : {e}"}
