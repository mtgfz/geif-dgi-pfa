"""Données AMMC / banques : consultation filtrée et rapprochement avec la raison sociale d'un contribuable."""
from fastapi import APIRouter, Depends, Query

from .. import marche
from ..security import get_current_user

router = APIRouter(prefix="/marche-ammc", tags=["marche-ammc"])


@router.get("")
def lister(
    banque: str | None = None,
    annee: int | None = Query(None, ge=1990, le=2100),
    statut: str | None = Query(None, pattern="^(valide|partiel|non_extrait|erreur)$"),
    q: str | None = Query(None, max_length=100),
    _user: dict = Depends(get_current_user),
):
    return marche.rechercher(banque, annee, statut, q)


@router.get("/rapprochement")
def rapprochement(nom: str = Query(..., min_length=2, max_length=200), _user: dict = Depends(get_current_user)):
    """Le contribuable est-il (probablement) un émetteur du référentiel ? Correspondance par raison sociale."""
    return marche.rapprochement(nom)
