"""
Workflow des réclamations : changements de statut atomiques + journal (historique).

Chaque réclamation porte une liste `historique` d'événements :
  {de, vers, par, role, commentaire, date}
La frise de suivi du contribuable et l'audit interne en sont déduits.
Un changement de statut n'est appliqué que si le statut actuel est bien un
des statuts attendus (filtre atomique côté MongoDB) : deux clics simultanés
ne peuvent pas faire avancer un dossier deux fois.
"""
from datetime import datetime

from fastapi import HTTPException

from .constants import (
    ACCUEIL_PAR_ROLE, ETAPES_SUIVI, DECISION_ENVOYEE, EN_TRAITEMENT, RETOURNEE,
    STATUT_LABELS, STATUT_LABELS_PUBLIC,
)
from .database import col_reclamations


def evenement(de: str | None, vers: str, par: str, role: str, commentaire: str | None = None) -> dict:
    return {
        "de": de, "vers": vers, "par": par, "role": role,
        "commentaire": commentaire, "date": datetime.now().isoformat(),
    }


def changer_statut(
    rec_id: str, attendus: tuple, vers: str, par: str, role: str,
    commentaire: str | None = None, extra: dict | None = None,
) -> dict:
    """Passe la réclamation de l'un des statuts `attendus` à `vers`.
    Lève 409 si le statut actuel n'est pas attendu. Retourne le document à jour."""
    d = col_reclamations.find_one({"_id": rec_id})
    if not d:
        raise HTTPException(404, "Réclamation introuvable.")
    if d["status"] not in attendus:
        raise HTTPException(
            409, f"Action impossible : le dossier est au statut « {STATUT_LABELS.get(d['status'], d['status'])} ».",
        )
    ev = evenement(d["status"], vers, par, role, commentaire)
    res = col_reclamations.update_one(
        {"_id": rec_id, "status": d["status"]},
        {"$set": {"status": vers, **(extra or {})}, "$push": {"historique": ev}},
    )
    if res.matched_count == 0:
        raise HTTPException(409, "Le dossier vient d'être modifié par un autre utilisateur. Rechargez la page.")
    return col_reclamations.find_one({"_id": rec_id})


def timeline_publique(d: dict) -> dict:
    """Frise de suivi destinée au contribuable : aucune donnée interne (agents, commentaires)."""
    historique = d.get("historique") or []
    premiere_date = {}
    for ev in historique:
        premiere_date.setdefault(ev["vers"], ev["date"])

    statut = d["status"]
    # « Retournée » = le dossier est revenu à l'instruction
    courant = ETAPES_SUIVI.index(EN_TRAITEMENT if statut == RETOURNEE else statut)
    termine = statut == DECISION_ENVOYEE

    etapes = []
    for i, s in enumerate(ETAPES_SUIVI):
        if termine or i < courant:
            etat = "fait"
        elif i == courant:
            etat = "en_cours"
        else:
            etat = "a_venir"
        etapes.append({
            "statut": s, "libelle": STATUT_LABELS_PUBLIC[s], "etat": etat,
            "date": premiere_date.get(s) if etat != "a_venir" else None,
        })

    evenements = [
        {"statut": ev["vers"], "libelle": STATUT_LABELS_PUBLIC[ev["vers"]], "date": ev["date"]}
        for ev in historique
    ]
    return {"etapes": etapes, "evenements": evenements}


def statuts_accueil(role: str) -> tuple:
    return ACCUEIL_PAR_ROLE.get(role, ())


def cles_egales(fournie: str | None, attendue: str | None) -> bool:
    """Comparaison en temps constant de la clé de vérification (tolère les accents/Unicode)."""
    import secrets
    if not fournie or not attendue:
        return False
    return secrets.compare_digest(fournie.strip().upper().encode(), attendue.strip().upper().encode())
