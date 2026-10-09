import os

from fastapi import APIRouter

from ..config import settings
from ..database import col_corrections, col_reclamations, col_rules

router = APIRouter(tags=["statistiques"])


@router.get("/statistiques")
def statistiques():
    """Statistiques réelles calculées à partir de MongoDB — aucune valeur simulée."""
    toutes = list(col_reclamations.find())
    total = len(toutes)
    traitees = sum(1 for r in toutes if r["status"] != "nouvelle")

    par_statut = {}
    for r in toutes:
        par_statut[r["status"]] = par_statut.get(r["status"], 0) + 1

    par_impot_agg = {}
    for r in toutes:
        e = par_impot_agg.setdefault(r["tax"], {"tax": r["tax"], "nombre": 0, "montant_emis": 0.0, "montant_degreve": 0.0})
        e["nombre"] += 1
        e["montant_emis"] += r.get("montant") or 0
        e["montant_degreve"] += r.get("montant_degreve") or 0
    par_impot = list(par_impot_agg.values())

    par_motif_agg = {}
    for r in toutes:
        key = (r["motif"], r["tax"])
        par_motif_agg[key] = par_motif_agg.get(key, 0) + 1
    par_motif = [{"motif": k[0], "tax": k[1], "nombre": v} for k, v in
                 sorted(par_motif_agg.items(), key=lambda x: -x[1])]

    valid_auto = sum(1 for r in toutes if r["status"] == "validee")
    modifiees = sum(1 for r in toutes if r["status"] == "modifiee")
    rejetees = sum(1 for r in toutes if r["status"] == "rejetee")
    closes = valid_auto + modifiees + rejetees
    taux_acceptation = round(valid_auto / closes, 4) if closes else None

    faibles = sum(1 for r in toutes if r.get("retrieval_score") is not None and r["retrieval_score"] < settings.SEUIL_CONFIANCE_RETRIEVAL)

    montant_emis_total = sum(r.get("montant") or 0 for r in toutes if r["status"] != "nouvelle")
    montant_degreve_total = sum(r.get("montant_degreve") or 0 for r in toutes if r["status"] != "nouvelle")

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
        "total_reclamations": total, "traitees": traitees, "par_statut": par_statut,
        "par_impot": par_impot, "par_motif": par_motif,
        "taux_acceptation_sans_modification": taux_acceptation,
        "dossiers_retrieval_faible": faibles,
        "montant_total_emis": montant_emis_total, "montant_total_degreve": montant_degreve_total,
        "nombre_corrections_enregistrees": col_corrections.count_documents({}),
        "regles": regles_stats,
    }


@router.get("/marche-ammc")
def marche_ammc():
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
