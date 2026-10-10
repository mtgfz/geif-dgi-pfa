"""Conseiller IA du portail SIT — chat public d'aide au dépôt, propulsé par
Groq. Ne rend aucune décision, ne remplace jamais le gestionnaire."""
from fastapi import APIRouter, Depends

from ..llm import assistant_sit_repondre
from ..models import AssistantSitRequest
from ..ratelimit import limite

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/sit", dependencies=[Depends(limite("assistant", 30, 600))])
def assistant_sit(body: AssistantSitRequest):
    reponse = assistant_sit_repondre(body.question, [m.model_dump() for m in (body.historique or [])])
    return {"reponse": reponse}
