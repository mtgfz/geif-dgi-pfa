"""Schémas Pydantic — validation d'entrée et forme des réponses."""
from typing import Optional
from pydantic import BaseModel, Field

from .config import settings


class SignupRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6)
    role: str = "gestionnaire"
    registration_code: str | None = None

    def role_valide(self) -> bool:
        return self.role in settings.ROLES

    def code_valide(self) -> bool:
        code_attendu = settings.ROLE_REGISTRATION_CODES.get(self.role)
        if code_attendu is None:
            return True  # ce rôle ne demande pas de code (ex: gestionnaire)
        return self.registration_code == code_attendu


class LoginRequest(BaseModel):
    username: str
    password: str


class NouvelleReclamation(BaseModel):
    contrib: str
    ifn: str
    tax: str  # IS | IR | TVA
    motif: str
    montant: float
    date_mer: str      # ISO — date de mise en recouvrement
    date_reclam: str    # ISO — date de la réclamation
    email: str | None = None  # requis pour recevoir la décision finale par e-mail


class DecisionGestionnaire(BaseModel):
    outcome: str  # accept | reject
    decision_finale: Optional[str] = None
    rapport_finale: Optional[str] = None


class AssistantMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class AssistantSitRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    historique: Optional[list[AssistantMessage]] = None


class ReformulationRequest(BaseModel):
    instruction: str = Field(min_length=1, max_length=300)


class MessageCreate(BaseModel):
    body: str = Field(min_length=1, max_length=2000)
    gestionnaire_destinataire: str | None = None  # rempli par le contribuable au premier message


class PredictionVolumeRequest(BaseModel):
    tax: Optional[str] = None       # None = toutes taxes confondues
    horizon_jours: int = Field(default=7, ge=1, le=90)


class PredictionOutcomeRequest(BaseModel):
    tax: str
    motif: str
    montant: float
    date_mer: str
    date_reclam: str
