"""
Espace de discussion contribuable ↔ gestionnaire, ouvert une fois la
décision finale rendue. Le contribuable s'authentifie avec la clé de
vérification (envoyée par e-mail) plutôt qu'un vrai compte — cohérent avec
le reste du portail SIT, qui reste sans connexion pour les contribuables.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException

from ..database import col_reclamations, col_messages
from ..models import MessageCreate
from ..security import get_current_user, get_current_user_optional

router = APIRouter(prefix="/reclamations", tags=["messages"])


def _verifier_cle(rec_id: str, cle: str | None) -> dict:
    d = col_reclamations.find_one({"_id": rec_id})
    if not d:
        raise HTTPException(404, "Réclamation introuvable.")
    if d["status"] not in ("validee_finale", "rejetee"):
        raise HTTPException(409, "L'espace de discussion s'ouvre une fois la décision finale rendue.")
    if not cle or cle != d.get("cle_verification"):
        raise HTTPException(403, "Clé de vérification incorrecte.")
    return d


@router.post("/{rec_id}/messages/contribuable")
def envoyer_message_contribuable(rec_id: str, body: MessageCreate, cle: str):
    d = _verifier_cle(rec_id, cle)

    # Premier message : fixe le gestionnaire choisi pour tout le fil, si fourni.
    if not d.get("gestionnaire_choisi") and body.gestionnaire_destinataire:
        col_reclamations.update_one({"_id": rec_id}, {"$set": {"gestionnaire_choisi": body.gestionnaire_destinataire}})

    msg = {
        "reclamation_id": rec_id, "auteur": "contribuable", "auteur_label": d["contrib"],
        "body": body.body, "created_at": datetime.now().isoformat(),
    }
    col_messages.insert_one(msg)
    return {"envoye": True}


@router.post("/{rec_id}/messages/interne")
def envoyer_message_interne(rec_id: str, body: MessageCreate, user: dict = Depends(get_current_user)):
    d = col_reclamations.find_one({"_id": rec_id})
    if not d:
        raise HTTPException(404, "Réclamation introuvable.")
    if d["status"] not in ("validee_finale", "rejetee"):
        raise HTTPException(409, "L'espace de discussion s'ouvre une fois la décision finale rendue.")

    msg = {
        "reclamation_id": rec_id, "auteur": "interne", "auteur_label": user["username"],
        "body": body.body, "created_at": datetime.now().isoformat(),
    }
    col_messages.insert_one(msg)
    return {"envoye": True}


@router.get("/{rec_id}/messages")
def lire_messages(rec_id: str, cle: str | None = None, user: dict | None = Depends(get_current_user_optional)):
    """Accessible soit avec la clé de vérification (contribuable), soit
    authentifié (personnel interne) — l'un ou l'autre suffit."""
    d = col_reclamations.find_one({"_id": rec_id})
    if not d:
        raise HTTPException(404, "Réclamation introuvable.")
    autorise_contribuable = cle is not None and cle == d.get("cle_verification")
    if not autorise_contribuable and not user:
        raise HTTPException(403, "Accès refusé.")

    rows = col_messages.find({"reclamation_id": rec_id}).sort("created_at", 1)
    return [{"auteur": m["auteur"], "auteur_label": m["auteur_label"], "body": m["body"], "created_at": m["created_at"]} for m in rows]
