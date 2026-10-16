"""Base de connaissances (RAG sur le Code Général des Impôts) : état de l'index et recherche exploratoire."""
from fastapi import APIRouter, Depends, Query

from .. import rag
from ..config import settings
from ..security import get_current_user

router = APIRouter(prefix="/connaissances", tags=["connaissances"])


@router.get("/etat")
def etat(_user: dict = Depends(get_current_user)):
    """Passages indexés, articles détectés, pages couvertes, modèle de recherche."""
    return rag.etat_rag()


@router.get("/recherche")
def recherche(
    q: str = Query(..., min_length=3, max_length=300, description="Question libre ou « Article 235 »"),
    k: int = Query(5, ge=1, le=10),
    _user: dict = Depends(get_current_user),
):
    """Recherche dans le CGI. Un numéro d'article (« Article 235 ») ouvre directement l'article ;
    sinon recherche sémantique. `pertinent` indique si le résultat dépasse le seuil de confiance utilisé
    pour le traitement des dossiers."""
    try:
        r = rag.rechercher_cgi(q.strip(), k)
    except Exception as e:  # noqa: BLE001
        return {"disponible": False, "message": f"Base du CGI indisponible : {e}", "resultats": []}
    for x in r["resultats"]:
        x["extrait"] = x.pop("texte")[:1200].strip()
        x["pertinent"] = bool(x["exact"]) or (x["score"] or 0) >= settings.SEUIL_CONFIANCE_RETRIEVAL
    return {"disponible": True, "seuil": settings.SEUIL_CONFIANCE_RETRIEVAL, **r}
