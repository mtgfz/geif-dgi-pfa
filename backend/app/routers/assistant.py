"""Conseiller IA du portail SIT — chat public d'aide au dépôt, propulsé par
Groq. Ne rend aucune décision, ne remplace jamais le gestionnaire."""
from fastapi import APIRouter

from ..llm import assistant_sit_repondre
from ..models import AssistantSitRequest

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/sit")
def assistant_sit(body: AssistantSitRequest):
    reponse = assistant_sit_repondre(body.question, [m.dict() for m in (body.historique or [])])
    return {"reponse": reponse}
