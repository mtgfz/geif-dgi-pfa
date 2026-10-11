"""Conseiller IA du portail contribuable — chat public propulsé par Groq, appuyé par le RAG sur le CGI.
Ne rend aucune décision, ne remplace jamais le gestionnaire."""
from fastapi import APIRouter, Depends

from ..llm import assistant_sit_repondre
from ..models import AssistantSitRequest
from ..ratelimit import limite

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/sit", dependencies=[Depends(limite("assistant", 30, 600))])
def assistant_sit(body: AssistantSitRequest):
    return assistant_sit_repondre(body.question, [m.model_dump() for m in (body.historique or [])])
