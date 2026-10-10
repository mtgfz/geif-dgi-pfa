"""
Migration idempotente des anciennes données (exécutée au démarrage).
  - rôle chef_secteur            -> chef_service
  - anciens statuts              -> nouveaux statuts (voir constants.MIGRATION_STATUTS)
  - réclamations sans historique -> un événement initial est créé
Relancer cette fonction ne change rien une fois les données migrées.
"""
from .constants import MIGRATION_ROLES, MIGRATION_STATUTS
from .database import col_reclamations, col_users
from .workflow import evenement


def migrer() -> dict:
    bilan = {"roles": 0, "statuts": 0, "historiques": 0}

    for ancien, nouveau in MIGRATION_ROLES.items():
        bilan["roles"] += col_users.update_many({"role": ancien}, {"$set": {"role": nouveau}}).modified_count

    for ancien, nouveau in MIGRATION_STATUTS.items():
        bilan["statuts"] += col_reclamations.update_many({"status": ancien}, {"$set": {"status": nouveau}}).modified_count

    for d in col_reclamations.find({"historique": {"$exists": False}}):
        ev = evenement(None, d["status"], "migration", "systeme", "Historique reconstitué lors de la migration.")
        ev["date"] = d.get("created_at", ev["date"])
        update = {"historique": [ev]}
        if d["status"] == "decision_envoyee" and not d.get("closed_at"):
            update["closed_at"] = d.get("created_at")
        col_reclamations.update_one({"_id": d["_id"]}, {"$set": update})
        bilan["historiques"] += 1
    return bilan
